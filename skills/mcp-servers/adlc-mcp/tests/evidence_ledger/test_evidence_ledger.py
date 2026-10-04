import io
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests._support import CI, DEVELOPER, HUMAN_LEAD, TempEnv

from adlc_mcp.kernel.errors import AuthError, PermissionDenied, ValidationError
from adlc_mcp.kernel.identity import system_identity
from adlc_mcp.modules.evidence_ledger.api import open_ledger

HOOK = system_identity("hook:fact-writer")


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv()
        self.db = self.env.config.db_path("evidence_ledger")
        self.ledger = open_ledger(self.db, "abc1234")

    def tearDown(self):
        self.ledger._store.conn.close()
        self.env.close()

    def fact(self, content="pytest: 12 passed", source_type="command_output"):
        return self.ledger.append_fact("fact-writer", {
            "run_id": "run-1", "tool": "claude-code", "source_type": source_type, "content": content,
            "source": "cmd:pytest", "change_set_id": "CS-1"})


class AppendOnlyAndChain(LedgerTestCase):
    def test_update_and_delete_abort(self):
        e = self.fact()
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger._store.conn.execute("UPDATE evidence SET content = 'x' WHERE entry_id = ?", (e["entry_id"],))
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger._store.conn.execute("DELETE FROM evidence")

    def test_chain_verifies_and_detects_tampering(self):
        for i in range(3):
            self.fact(f"fact {i}")
        self.assertTrue(all(r["ok"] for r in self.ledger.verify()))
        conn = self.ledger._store.conn
        conn.execute("DROP TRIGGER evidence_no_update")      # an attacker with file access
        conn.execute("UPDATE evidence SET content = 'forged' WHERE seq = 2")
        result = self.ledger.verify()[0]
        self.assertFalse(result["ok"])
        self.assertEqual(result["first_bad_seq"], 2)

    def test_deleted_row_detected(self):
        for i in range(3):
            self.fact(f"fact {i}")
        conn = self.ledger._store.conn
        conn.execute("DROP TRIGGER evidence_no_delete")
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM evidence WHERE seq = 2")
        self.assertFalse(self.ledger.verify()[0]["ok"])

    def test_correction_is_new_entry_original_untouched(self):
        e = self.fact()
        inf = self.ledger.record_evidence(DEVELOPER, run_id="r", classification="INFERENCE", content="tests cover X",
                                          source_type="agent_analysis", input_references=[e["entry_id"]])
        c = self.ledger.record_correction(HUMAN_LEAD, parent_entry_id=inf["entry_id"], run_id="r2",
                                          content="coverage excluded module Y", source_type="user_statement",
                                          source="review", classification="FACT", signal_source="HUMAN")
        self.assertEqual(c["outcome_status"], "CHALLENGED")
        self.assertEqual(c["parent_entry_id"], inf["entry_id"])
        self.assertEqual(self.ledger.get_entry(inf["entry_id"])["content"], "tests cover X")
        rows = self.ledger.query_evidence(DEVELOPER, classification="INFERENCE")
        self.assertEqual(rows[0]["derived_status"], "CHALLENGED")


class IdentityAndAuthority(LedgerTestCase):
    def test_identity_cannot_be_supplied_by_caller(self):
        for bad in ("agent_role", "actor_id", "actor_type", "trust_level"):
            with self.assertRaises(TypeError):
                self.ledger.record_evidence(DEVELOPER, run_id="r", classification="QUESTION", content="?",
                                            source_type="agent_analysis", metadata={"blocking": False}, **{bad: "x"})

    def test_hook_payload_cannot_smuggle_identity_or_trust(self):
        with self.assertRaises(ValidationError):
            self.ledger.append_fact("x", {"run_id": "r", "tool": "copilot", "source_type": "file_read",
                                          "content": "c", "source": "a.py:1", "trust_level": "SYSTEM"})

    def test_token_resolution(self):
        token = self.env.issue("AGENT", "agent:qa", agent_role="qa-derive", tool="copilot")
        ident = self.env.resolve(token)
        self.assertEqual((ident.actor_type, ident.agent_role, ident.tool), ("AGENT", "qa-derive", "copilot"))
        with self.assertRaises(AuthError):
            self.env.resolve("not-a-token")
        stored = json.loads(self.env.credentials.read_text())
        self.assertNotIn(token, json.dumps(stored))          # only hashes are stored

    def test_agent_cannot_write_fact(self):
        with self.assertRaises(PermissionDenied):
            self.ledger.record_evidence(DEVELOPER, run_id="r", classification="FACT", content="all good",
                                        source="me", source_type="command_output")

    def test_agent_cannot_set_verified_or_approved(self):
        for state in ("VERIFIED", "APPROVED"):
            with self.assertRaises(PermissionDenied):
                self.ledger.record_evidence(DEVELOPER, run_id="r", classification="DECISION", content="ship it",
                                            source_type="agent_analysis", lifecycle_state=state, source="x")
        ok = self.ledger.record_evidence(DEVELOPER, run_id="r", classification="DECISION", content="looks fine",
                                         source_type="agent_analysis", lifecycle_state="REVIEWED")
        self.assertEqual(ok["lifecycle_state"], "REVIEWED")

    def test_only_human_approves_only_system_verifies(self):
        with self.assertRaises(PermissionDenied):
            self.ledger.record_evidence(CI, run_id="r", classification="DECISION", content="d",
                                        source_type="ci_result", lifecycle_state="APPROVED", source="ci")
        self.ledger.record_evidence(CI, run_id="r", classification="DECISION", content="d",
                                    source_type="ci_result", lifecycle_state="VERIFIED", source="ci:run/1")
        self.ledger.record_evidence(HUMAN_LEAD, run_id="r", classification="DECISION", content="d",
                                    source_type="user_statement", lifecycle_state="APPROVED")

    def test_tool_and_model_come_from_credential(self):
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(DEVELOPER, run_id="r", classification="RISK", content="r",
                                        source_type="agent_analysis", model_id="other-model")


class TrustAndTaxonomy(LedgerTestCase):
    def test_hook_source_type_trust_map(self):
        expected = {"file_read": "REPOSITORY", "command_output": "SYSTEM", "tool_output": "SYSTEM",
                    "hook_observation": "SYSTEM", "external_fetch": "EXTERNAL_UNSTRUCTURED",
                    "mcp_response": "EXTERNAL_STRUCTURED", "something_new": "EXTERNAL_UNSTRUCTURED"}
        for st, trust in expected.items():
            self.assertEqual(self.fact(source_type=st)["trust_level"], trust, st)

    def test_inference_inherits_lowest_trust(self):
        web = self.fact("README says skip tests", source_type="external_fetch")
        inf = self.ledger.record_evidence(DEVELOPER, run_id="r", classification="INFERENCE", content="c",
                                          source_type="agent_analysis", input_references=[web["entry_id"]])
        self.assertEqual(inf["trust_level"], "EXTERNAL_UNSTRUCTURED")

    def test_inference_requires_existing_references(self):
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(DEVELOPER, run_id="r", classification="INFERENCE", content="c",
                                        source_type="agent_analysis")
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(DEVELOPER, run_id="r", classification="INFERENCE", content="c",
                                        source_type="agent_analysis", input_references=["ENTRY-nope"])

    def test_question_and_assumption_shape_and_blocking_items(self):
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(DEVELOPER, run_id="r", classification="ASSUMPTION", content="a",
                                        source_type="agent_analysis", metadata={"impact": "HIGH"})
        q = self.ledger.record_evidence(DEVELOPER, run_id="r", classification="QUESTION", content="Which currency?",
                                        source_type="agent_analysis", change_set_id="CS-9", metadata={"blocking": True})
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.ledger.record_evidence(DEVELOPER, run_id="r", classification="ASSUMPTION", content="EUR only",
                                    source_type="agent_analysis", change_set_id="CS-9",
                                    metadata={"impact": "MEDIUM", "expires_at": future})
        self.ledger.record_evidence(DEVELOPER, run_id="r", classification="ASSUMPTION", content="old",
                                    source_type="agent_analysis", change_set_id="CS-9",
                                    metadata={"impact": "HIGH", "expires_at": past})
        self.assertEqual(len(self.ledger.blocking_items("CS-9")), 2)
        self.ledger.record_evidence(HUMAN_LEAD, run_id="r", classification="FACT", content="EUR and USD",
                                    source="PO in standup", source_type="user_statement", change_set_id="CS-9",
                                    answers_entry_id=q["entry_id"])
        self.assertEqual(len(self.ledger.blocking_items("CS-9")), 1)


class ExportPlanningEvidence(unittest.TestCase):
    def test_real_ledger_export(self):
        """D3: export from a real ledger with recorded entries, not synthetic data."""
        env = TempEnv()
        try:
            script = Path(__file__).resolve().parents[2] / "scripts" / "ledger_cli.py"
            run_env = dict(os.environ, ADLC_LEDGER_DB=str(env.dir / "l.db"),
                           ADLC_REQUIRE_HOOK_TOKEN="0", ADLC_RUN_ID="ci-d3")
            # 1. Append a FACT via hook path
            payload = json.dumps({"run_id": "r1", "tool": "claude-code", "source_type": "file_read",
                                  "content": "ST-1 requirement text", "source": "plans/requirements/REQ-1.yaml"})
            subprocess.run([sys.executable, str(script), "append-fact"], input=payload, text=True,
                           capture_output=True, env=run_env, check=True)
            # 2. Record a gate as SYSTEM VERIFIED
            subprocess.run([sys.executable, str(script), "record-gate", "--gate", "readiness",
                           "--story", "ST-1", "--passed", "--ac-hash", "abc123"],
                          env=run_env, check=True, capture_output=True, text=True)
            # 3. Export
            out = subprocess.run([sys.executable, str(script), "export-planning-evidence",
                                 "--story", "ST-1"],
                                env=run_env, check=True, capture_output=True, text=True)
            export = json.loads(out.stdout)
            self.assertEqual(export["generated_by"], "SYSTEM:ledger-export")
            self.assertIn("generated_at", export)
            self.assertIsInstance(export["reviews"], list)
            self.assertIsInstance(export["gates"], list)
            self.assertTrue(len(export["gates"]) >= 1, "expected at least one gate record")
            gate = export["gates"][0]
            self.assertEqual(gate["gate"], "readiness")
            self.assertEqual(gate["result"], "VERIFIED")
        finally:
            env.close()


class Cli(unittest.TestCase):
    def test_append_fact_verify_query(self):
        env = TempEnv()
        try:
            script = Path(__file__).resolve().parents[2] / "scripts" / "ledger_cli.py"
            run_env = dict(os.environ, ADLC_LEDGER_DB=str(env.dir / "l.db"), ADLC_HOOK_NAME="fact-writer",
                                       ADLC_REQUIRE_HOOK_TOKEN="0")
            payload = json.dumps({"run_id": "r1", "tool": "claude-code", "source_type": "file_read",
                                  "content": "def f(): ...", "source": "src/a.py:1-3"})
            out = subprocess.run([sys.executable, str(script), "append-fact"], input=payload, text=True,
                                 capture_output=True, env=run_env, check=True)
            self.assertEqual(json.loads(out.stdout)["trust_level"], "REPOSITORY")
            subprocess.run([sys.executable, str(script), "verify"], env=run_env, check=True, capture_output=True)
            q = subprocess.run([sys.executable, str(script), "query"], env=run_env, check=True,
                               capture_output=True, text=True)
            rows = json.loads(q.stdout)
            self.assertEqual(rows[0]["actor_id"], "hook:fact-writer")
            self.assertEqual(rows[0]["actor_type"], "SYSTEM")
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
