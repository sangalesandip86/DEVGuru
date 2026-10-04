"""Layer C+: MCP integration test — exercises real MCP tools against a sample requirement.

Simulates what happens when a developer uses the ADLC pipeline:
  1. Create a Change Set
  2. Record evidence (DECISION, INFERENCE, ASSUMPTION, QUESTION)
  3. Query evidence back
  4. Record corrections and handoffs
  5. Verify security boundaries (agent cannot write FACT, cannot set APPROVED)
  6. Contract registry register + drift detection

No LLM calls — exercises the MCP API objects directly through Python,
same codepath as when Claude calls mcp__adlc__* tools.

    python -m unittest skills/testing/pipeline-tests/test_mcp_integration.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MCP_SRC = Path(__file__).resolve().parents[2] / "mcp-servers" / "adlc-mcp" / "src"
MCP_TESTS = Path(__file__).resolve().parents[2] / "mcp-servers" / "adlc-mcp" / "tests"
sys.path.insert(0, str(MCP_SRC))
sys.path.insert(0, str(MCP_TESTS))

from _support import DEVELOPER, CODE_REVIEWER, HUMAN_LEAD, CI, TempEnv  # noqa: E402
from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError  # noqa: E402

ALL_MODULES = "evidence_ledger,change_management,work_planning,contract_registry"
RUN_ID = "run-mcp-integration-001"


class TestMCPIntegrationPipeline(unittest.TestCase):

    def setUp(self):
        self.env = TempEnv(ALL_MODULES)
        self.registry = build_modules(self.env.config)
        self.ledger = self.registry.get("evidence_ledger").api
        self.cm = self.registry.get("change_management").api
        self.cr = self.registry.get("contract_registry").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def _create_cs(self, title="Add user authentication"):
        cs = self.cm.create_change_set(
            DEVELOPER, title=title, requirements=["REQ-1"],
            repositories=["payments-svc"],
        )
        self.assertIn("id", cs)
        self.assertEqual(cs["status"], "DRAFT")
        return cs["id"]

    def _append_fact(self, content="test output", cs_id=None):
        return self.ledger.append_fact("test-hook", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output", "content": content,
            "source": "cmd:test", "change_set_id": cs_id,
        })

    def test_01_create_change_set(self):
        cs = self.cm.create_change_set(
            DEVELOPER, title="Add user authentication",
            requirements=["REQ-1"], repositories=["payments-svc"],
        )
        self.assertIn("id", cs)
        self.assertEqual(cs["status"], "DRAFT")
        self.assertEqual(cs["title"], "Add user authentication")

    def test_02_evidence_recording_and_query(self):
        cs_id = self._create_cs()
        fact = self._append_fact("existing user model found", cs_id)

        decision = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="Use JWT tokens for authentication with RS256 signing",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[fact["entry_id"]],
            lifecycle_state="PROPOSED",
        )
        self.assertIn("entry_id", decision)

        inference = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Existing user model supports adding auth fields",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[fact["entry_id"]],
        )
        self.assertIn("entry_id", inference)

        assumption = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="ASSUMPTION",
            content="OAuth2 provider supports PKCE flow",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"impact": "MEDIUM", "expires_at": "2027-01-01T00:00:00Z"},
        )
        self.assertIn("entry_id", assumption)

        question = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="QUESTION",
            content="Should session tokens expire after 24h or 7d?",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"blocking": True},
        )
        self.assertIn("entry_id", question)

        entries = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        classifications = {e["classification"] for e in entries}
        self.assertTrue({"FACT", "DECISION", "INFERENCE", "ASSUMPTION", "QUESTION"}.issubset(classifications))

    def test_03_evidence_chain_integrity(self):
        cs_id = self._create_cs("Chain test")
        for i in range(5):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="QUESTION",
                content=f"Chain question {i}", source_type="TOOL",
                change_set_id=cs_id, metadata={"blocking": False},
            )
        results = self.ledger.verify()
        broken = [r for r in results if not r.get("ok", True)]
        self.assertEqual(len(broken), 0)

    def test_04_correction_record(self):
        cs_id = self._create_cs("Correction test")
        fact = self._append_fact("grep md5: found in auth.py", cs_id)
        entry = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Auth uses MD5 hashing", source_type="TOOL",
            change_set_id=cs_id, input_references=[fact["entry_id"]],
        )
        correction = self.ledger.record_correction(
            CODE_REVIEWER, parent_entry_id=entry["entry_id"],
            run_id=RUN_ID, content="Incorrect — codebase uses bcrypt, not MD5",
            source_type="TOOL",
        )
        self.assertIn("entry_id", correction)
        entries = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        orig = [e for e in entries if e["entry_id"] == entry["entry_id"]]
        self.assertEqual(orig[0]["derived_status"], "CHALLENGED")

    def test_05_handoff_recording(self):
        cs_id = self._create_cs()
        handoff = self.cm.record_handoff(
            DEVELOPER, change_set_id=cs_id, to_role="code-reviewer",
            payload={
                "summary": "JWT auth implemented, 15 unit tests passing",
                "inputs": [{"artifact_ref": "payments-svc@abc1234:src/auth/jwt.ts",
                            "content_hash": "sha256:" + "aa" * 32}],
                "outputs": [{"artifact_kind": "implementation",
                             "content_hash": "sha256:" + "bb" * 32}],
                "classifications": [{"classification": "INFERENCE",
                                     "content": "Implementation complete"}],
            },
            verdict="ACCEPT",
        )
        self.assertIn("id", handoff)
        self.assertEqual(handoff["to_role"], "code-reviewer")

    def test_06_agent_cannot_write_fact(self):
        with self.assertRaises(PermissionDenied):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="FACT",
                content="This should fail — agents cannot write FACT",
                source_type="command_output",
            )

    def test_07_blocking_items_and_answers(self):
        cs_id = self._create_cs("Blocking test")
        q = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="QUESTION",
            content="What auth provider to use?", source_type="TOOL",
            change_set_id=cs_id, metadata={"blocking": True},
        )
        blockers = self.ledger.blocking_items(cs_id)
        self.assertGreater(len(blockers), 0)

        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="PO confirmed: use Auth0", source_type="TOOL",
            change_set_id=cs_id, answers_entry_id=q["entry_id"],
            input_references=[q["entry_id"]],
        )
        blockers_after = self.ledger.blocking_items(cs_id)
        q_blockers = [b for b in blockers_after if q["entry_id"] in b]
        self.assertEqual(len(q_blockers), 0)

    def test_08_contract_registry_register_and_drift(self):
        spec = {"fields": {"id": {"type": "string", "required": True},
                           "amount": {"type": "integer", "required": True}}}
        self.cr.register_contract(
            DEVELOPER, contract_id="orders", provider="order-svc",
            version="1", spec=spec, type="http", consumers=["billing"],
        )
        r = self.cr.detect_drift(DEVELOPER, contract_id="orders", observed_spec=spec)
        self.assertFalse(r["drift"])

        drift_spec = {"fields": {"id": {"type": "integer"}, "extra": {"type": "string"}}}
        r = self.cr.detect_drift(DEVELOPER, contract_id="orders", observed_spec=drift_spec)
        self.assertTrue(r["drift"])

    def test_09_contract_compatibility_check(self):
        spec = {"fields": {"id": {"type": "string", "required": True},
                           "amount": {"type": "integer", "required": True}}}
        self.cr.register_contract(
            DEVELOPER, contract_id="pay", provider="pay-svc",
            version="1", spec=spec, type="http", consumers=["billing"],
        )
        self.cr.register_contract(
            DEVELOPER, contract_id="pay", provider="pay-svc",
            version="1", spec=spec, type="http", party="billing",
        )
        self.cr.record_deployment(
            CI, app="billing", version="5", environment="prod",
            contract_versions={"pay": "1"},
        )
        v2_spec = {"fields": {**spec["fields"], "note": {"type": "string", "required": False}}}
        self.cr.register_contract(
            DEVELOPER, contract_id="pay", provider="pay-svc",
            version="2", spec=v2_spec, type="http",
        )
        r = self.cr.check_compatibility(
            DEVELOPER, contract_id="pay", candidate_version="2",
            party="pay-svc", environment="prod",
        )
        self.assertEqual(r["result"], "COMPATIBLE")

    def test_10_cross_module_flow(self):
        cs_id = self._create_cs("Cross-module flow")
        fact = self._append_fact("npm test: 42 passed", cs_id)

        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="All tests pass", source_type="TOOL",
            change_set_id=cs_id, input_references=[fact["entry_id"]],
        )
        self.cm.record_handoff(
            DEVELOPER, change_set_id=cs_id, to_role="code-reviewer",
            payload={
                "summary": "Implementation complete",
                "inputs": [{"artifact_ref": "payments-svc@abc1234:src/auth.ts",
                            "content_hash": "sha256:" + "cc" * 32}],
                "outputs": [{"artifact_kind": "implementation",
                             "content_hash": "sha256:" + "dd" * 32}],
                "classifications": [],
            },
            verdict="ACCEPT",
        )
        full = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertGreater(len(full.get("handoffs", [])), 0)

    def test_11_inference_requires_input_references(self):
        cs_id = self._create_cs("Ref test")
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="Unsourced inference", source_type="TOOL",
                change_set_id=cs_id,
            )

    def test_12_assumption_requires_impact_and_expiry(self):
        cs_id = self._create_cs("Assumption test")
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="ASSUMPTION",
                content="Some assumption", source_type="TOOL",
                change_set_id=cs_id,
                metadata={"impact": "LOW"},
            )


if __name__ == "__main__":
    unittest.main()
