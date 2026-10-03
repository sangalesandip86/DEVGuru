"""ADR 0006: signal-only incidents, sanitized lessons, local evidence retention."""
import json
import os
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests._support import CI, CODE_REVIEWER, DEVELOPER, HUMAN_LEAD, TempEnv

from adlc_mcp.kernel import db
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError
from adlc_mcp.kernel.identity import Identity
from adlc_mcp.modules.evidence_ledger import store as store_mod
from adlc_mcp.modules.evidence_ledger.api import EvidenceLedger, open_ledger

DEVELOPER_RUN2 = Identity("AGENT", "agent:developer", agent_role="developer", tool="claude-code", model_id="model-a")
QA = Identity("AGENT", "agent:qa-diagnose", agent_role="qa-diagnose", tool="copilot", model_id="model-b")


def sanitized(**over):
    return dict({"passed": True, "checker_version": "sanitize_check 1.0",
                 "checked_at": datetime.now(timezone.utc).isoformat()}, **over)


class Base(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv()
        self.class_map = self.env.dir / "failure-class-map.json"
        self.class_map.write_text(json.dumps({"negative_ac_present": "MISSING_NEGATIVE_CASE",
                                              "assertion_removed": "WEAKENED_TEST"}))
        os.environ["ADLC_FAILURE_CLASS_MAP"] = str(self.class_map)
        self.ledger = open_ledger(self.env.config.db_path("evidence_ledger"), "abc1234")
        # The developer agent's failing output, as the hooks/agent recorded it.
        fact = self.ledger.append_fact("fact-writer", {"run_id": "run-7", "tool": "claude-code",
                                                       "source_type": "file_read", "content": "AC list for ST-9",
                                                       "source": "plans/stories/ST-9.yaml"})
        self.failed = self.ledger.record_evidence(DEVELOPER, run_id="run-7", classification="PROPOSAL",
                                                  content="AC: valid card is charged", source_type="agent_analysis",
                                                  change_set_id="CS-1", input_references=[fact["entry_id"]])

    def tearDown(self):
        os.environ.pop("ADLC_FAILURE_CLASS_MAP", None)
        self.ledger._store.conn.close()
        self.env.close()

    def incident(self, who=CODE_REVIEWER, **over):
        fields = dict(skill="product-planning/story-writer", step="Procedure 4 — write acceptance criteria",
                      failure_class="MISSING_NEGATIVE_CASE", signal_type="negative", signal_source="REVIEWER",
                      pattern_eligible=True, evidence_refs=[self.failed["entry_id"]])
        fields.update(over)
        return self.ledger.record_incident(who, **fields)

    def lesson_fields(self, incident_ids, **over):
        return dict({
            "skill": "product-planning/story-writer", "step": "Procedure 4 — write acceptance criteria",
            "failure_class": "MISSING_NEGATIVE_CASE", "occurrences": {"incidents": 2, "change_sets": 1, "projects": 1},
            "what_failed": "AC for input-validation stories covered only valid input",
            "advice": "When a story changes input handling, require at least one negative AC per validated field",
            "check": "touches.input_validation -> count(ac.kind == negative) >= 1", "remedy_kind": "GATE",
            "incident_refs": incident_ids, "sanitization_result": sanitized()}, **over)


class IncidentShape(Base):
    def test_accepts_signal_shape(self):
        inc = self.incident(note="Story-writer omitted negative AC for a validated field")
        self.assertEqual(inc["evidence_refs"], [self.failed["entry_id"]])
        self.assertEqual(inc["note_author_type"], "AGENT")

    def test_rejects_free_text_use_case_fields(self):
        for bad in ({"prompt": "Refund flow for ACME"}, {"files": ["repo@abc1234:a.py"]},
                    {"context": {"x": 1}}, {"hypothesis": "h"}, {"trigger": "t"}, {"description": "d"}):
            with self.assertRaises(ValidationError, msg=str(bad)):
                self.incident(**bad)

    def test_evidence_refs_must_exist_and_be_non_empty(self):
        with self.assertRaises(ValidationError):
            self.incident(evidence_refs=[])
        with self.assertRaises(ValidationError):
            self.incident(evidence_refs=["ENTRY-nope"])

    def test_failure_class_from_taxonomy(self):
        with self.assertRaises(ValidationError):
            self.incident(failure_class="SOMETHING_ELSE")
        with self.assertRaises(ValidationError):
            self.incident(failure_class="lowercase")
        with self.assertRaises(ValidationError):
            self.incident(failure_class=None)                 # required for negative
        self.incident(failure_class="WEAKENED_TEST")

    def test_note_rules(self):
        with self.assertRaises(ValidationError):
            self.incident(note="x" * 281)
        with self.assertRaises(ValidationError):
            self.incident(note="two\nlines")
        with self.assertRaises(ValidationError):              # notes come from the reviewer/human
            self.incident(who=CODE_REVIEWER, signal_source="AGENT", note="n")

    def test_failing_role_cannot_author_note(self):
        with self.assertRaises(PermissionDenied):
            self.incident(who=DEVELOPER_RUN2, signal_source="REVIEWER", note="I should have added negatives")
        other_session = Identity("AGENT", "agent:developer", agent_role="code-reviewer", tool="copilot", model_id="m")
        with self.assertRaises(PermissionDenied):             # same session (actor_id) under another role
            self.incident(who=other_session, note="n")
        self.incident(who=HUMAN_LEAD, signal_source="HUMAN", note="Negative AC missing")
        self.incident(who=DEVELOPER_RUN2, signal_source="AGENT")  # a deterministic signal without a note is fine

    def test_positive_signal_quality_gate(self):
        with self.assertRaises(ValidationError):
            self.incident(signal_type="positive", failure_class=None)
        with self.assertRaises(ValidationError):
            self.incident(signal_type="positive", failure_class=None,
                          verification_strength={"acceptance_criteria_exercised": False, "changed_code_coverage": 0.9})
        self.incident(signal_type="positive", failure_class=None,
                      verification_strength={"acceptance_criteria_exercised": True, "changed_code_coverage": 0.8})
        with self.assertRaises(ValidationError):
            self.incident(signal_type="unverified-positive", failure_class=None, pattern_eligible=True)
        self.incident(signal_type="unverified-positive", failure_class=None, pattern_eligible=False)

    def test_query_incidents_returns_pointers_not_content(self):
        self.incident()
        self.incident(signal_type="unverified-positive", failure_class=None, pattern_eligible=False)
        rows = self.ledger.query_incidents(QA)
        self.assertEqual(len(rows), 1)                        # pattern-eligible only by default
        self.assertEqual(len(self.ledger.query_incidents(QA, pattern_eligible_only=False)), 2)
        blob = json.dumps(rows)
        self.assertNotIn("valid card is charged", blob)
        self.assertNotIn("AC list for ST-9", blob)
        self.assertNotIn("content", rows[0])
        self.assertEqual(rows[0]["evidence_refs"], [self.failed["entry_id"]])

    def test_clusters(self):
        self.incident(); self.incident(); self.incident(failure_class="WEAKENED_TEST")
        clusters = self.ledger.incident_clusters(QA, min_incidents=2)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["occurrences"], {"incidents": 2, "change_sets": 1, "projects": 1})


class Lessons(Base):
    def setUp(self):
        super().setUp()
        self.ids = [self.incident()["incident_id"], self.incident()["incident_id"]]

    def test_record_and_query_lesson(self):
        les = self.ledger.record_lesson(QA, **self.lesson_fields(self.ids))
        self.assertEqual((les["scope"], les["remedy_kind"]), ("PROJECT", "GATE"))
        got = self.ledger.query_lessons(QA, skill="product-planning/story-writer")
        self.assertEqual(got[0]["lesson_id"], les["lesson_id"])
        self.assertIsNotNone(got[0]["last_fired"])

    def test_sanitization_result_required(self):
        for bad in (None, {"passed": False, "checker_version": "1", "checked_at": "2026-01-01T00:00:00+00:00"},
                    {"passed": "true", "checker_version": "1", "checked_at": "2026-01-01T00:00:00+00:00"},
                    sanitized(checker_version=""), sanitized(checked_at="yesterday"),
                    sanitized(checked_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())):
            with self.assertRaises(ValidationError, msg=str(bad)):
                self.ledger.record_lesson(QA, **self.lesson_fields(self.ids, sanitization_result=bad))

    def test_lesson_content_rules(self):
        for over in ({"remedy_kind": "VIBES"}, {"failure_class": "NOT_IN_MAP"}, {"what_failed": "x" * 281},
                     {"advice": "Fix ENTRY-1a2b in CS-9"}, {"what_failed": "broke repo@a1b2c3d:src/x.py"},
                     {"occurrences": {"incidents": 0, "change_sets": 0, "projects": 0}},
                     {"prompt": "the real task"}, {"incident_refs": ["INC-missing"]}):
            with self.assertRaises(ValidationError, msg=str(over)):
                self.ledger.record_lesson(QA, **self.lesson_fields(self.ids, **over))
        other = self.incident(failure_class="WEAKENED_TEST")["incident_id"]
        with self.assertRaises(ValidationError):                # must belong to the cluster
            self.ledger.record_lesson(QA, **self.lesson_fields([*self.ids, other]))

    def test_failing_agent_never_authors_its_lesson(self):
        with self.assertRaises(PermissionDenied):
            self.ledger.record_lesson(DEVELOPER_RUN2, **self.lesson_fields(self.ids))

    def test_agents_can_never_set_org(self):
        with self.assertRaises(PermissionDenied):
            self.ledger.record_lesson(QA, **self.lesson_fields(self.ids, scope="ORG"))

    def test_org_promotion_requires_human_approved_reference(self):
        les = self.ledger.record_lesson(QA, **self.lesson_fields(self.ids))
        promote = {"scope": "ORG", "parent_lesson_id": les["lesson_id"], "sanitization_result": sanitized()}
        unrelated = self.ledger.record_evidence(HUMAN_LEAD, run_id="r", classification="DECISION", content="ok",
                                                source_type="user_statement", lifecycle_state="APPROVED",
                                                output_references=["LES-other"])
        with self.assertRaises(PermissionDenied):                # approval does not reference the lesson
            self.ledger.record_lesson(HUMAN_LEAD, **promote, approval_entry_id=unrelated["entry_id"])
        reviewed = self.ledger.record_evidence(CODE_REVIEWER, run_id="r", classification="DECISION", content="ok",
                                               source_type="agent_analysis", lifecycle_state="REVIEWED",
                                               output_references=[les["lesson_id"]])
        with self.assertRaises(PermissionDenied):                # not HUMAN / not APPROVED
            self.ledger.record_lesson(HUMAN_LEAD, **promote, approval_entry_id=reviewed["entry_id"])
        approval = self.ledger.record_evidence(HUMAN_LEAD, run_id="r", classification="DECISION",
                                               content="Lesson approved for org sharing", source_type="user_statement",
                                               lifecycle_state="APPROVED", output_references=[les["lesson_id"]])
        with self.assertRaises(ValidationError):                 # content is copied, not resupplied
            self.ledger.record_lesson(HUMAN_LEAD, **promote, approval_entry_id=approval["entry_id"], advice="new")
        org = self.ledger.record_lesson(CI, **promote, approval_entry_id=approval["entry_id"])
        self.assertEqual((org["scope"], org["advice"], org["parent_lesson_id"]),
                         ("ORG", les["advice"], les["lesson_id"]))
        self.assertEqual(len(self.ledger.query_lessons(QA, scope="ORG")), 1)
        self.assertTrue(all(r["ok"] for r in self.ledger.verify()))


class Retention(Base):
    def age_payload(self, entry_id, days):
        """Simulate time passing (test-only: bypasses the immutability trigger)."""
        conn = self.ledger._store.conn
        conn.execute("DROP TRIGGER evidence_content_no_update")
        old = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn.execute("UPDATE evidence_content SET created_at = ? WHERE entry_id = ?", (old, entry_id))
        conn.execute("CREATE TRIGGER evidence_content_no_update BEFORE UPDATE ON evidence_content "
                     "BEGIN SELECT RAISE(ABORT, 'evidence_content is immutable'); END")

    def test_payload_is_outside_chain_and_committed(self):
        row = self.ledger._store.conn.execute("SELECT content, content_hash FROM evidence WHERE entry_id = ?",
                                              (self.failed["entry_id"],)).fetchone()
        self.assertEqual(row["content"], "")
        self.assertTrue(row["content_hash"].startswith("sha256:"))
        self.assertEqual(self.ledger.get_entry(self.failed["entry_id"])["content_status"], "PRESENT")

    def test_young_content_cannot_be_deleted(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger._store.conn.execute("DELETE FROM evidence_content")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger._store.conn.execute("UPDATE evidence_content SET content = 'x'")

    def test_expired_content_hidden_then_purged_chain_still_valid(self):
        self.age_payload(self.failed["entry_id"], 91)
        e = self.ledger.get_entry(self.failed["entry_id"])
        self.assertEqual((e["content"], e["content_status"]), (None, "EXPIRED"))   # hidden before purge
        self.assertEqual(self.ledger.purge_expired_content()["purged"], 1)
        n = self.ledger._store.conn.execute("SELECT COUNT(*) AS n FROM evidence_content WHERE entry_id = ?",
                                            (self.failed["entry_id"],)).fetchone()["n"]
        self.assertEqual(n, 0)
        self.assertTrue(all(r["ok"] for r in self.ledger.verify()), self.ledger.verify())
        self.assertEqual(self.ledger.get_entry(self.failed["entry_id"])["content_status"], "EXPIRED")

    def test_retention_is_configurable(self):
        self.age_payload(self.failed["entry_id"], 10)
        conn = self.ledger._store.conn
        short = EvidenceLedger(conn, "abc1234", retention_days=7)
        short.migrate()
        self.assertEqual(short.purge_expired_content(), {"purged": 1, "retention_days": 7})
        with self.assertRaises(ValidationError):
            EvidenceLedger(conn, "abc1234", retention_days=0)

    def test_tampered_payload_detected(self):
        conn = self.ledger._store.conn
        conn.execute("DROP TRIGGER evidence_content_no_update")
        conn.execute("UPDATE evidence_content SET content = 'forged' WHERE entry_id = ?", (self.failed["entry_id"],))
        result = {r["table"]: r for r in self.ledger.verify()}["evidence_content"]
        self.assertFalse(result["ok"])


class MigrationKeepsChain(unittest.TestCase):
    def test_upgrade_from_0001_keeps_existing_chain_valid(self):
        env = TempEnv()
        try:
            path = env.dir / "old.db"
            conn = db.connect(path)
            # Apply only 0001, write v1 rows, then upgrade.
            one_only = env.dir / "mig"
            one_only.mkdir()
            src = Path(store_mod.MIGRATIONS)
            (one_only / "0001_initial.sql").write_text((src / "0001_initial.sql").read_text(encoding="utf-8"),
                                                       encoding="utf-8")
            db.run_migrations(conn, "evidence_ledger", one_only)
            for i in range(3):
                db.append_chained(conn, "evidence", {
                    "entry_id": f"ENTRY-old{i}", "run_id": "r", "change_set_id": None, "actor_type": "SYSTEM",
                    "actor_id": "hook:x", "agent_role": None, "model_id": None, "tool": "claude-code",
                    "classification": "FACT", "trust_level": "SYSTEM", "source_type": "command_output",
                    "content": f"inline {i}", "source": "cmd", "input_references": None,
                    "output_references": None, "decision_ids": None, "lifecycle_state": None, "snapshot_id": None,
                    "parent_entry_id": None, "outcome_status": None, "platform_release_sha": "x",
                    "timestamp": "2026-10-01T00:00:00+00:00", "signal_source": None, "metadata": None})
            conn.close()
            ledger = open_ledger(path, "abc1234")
            self.assertTrue(all(r["ok"] for r in ledger.verify()), ledger.verify())
            old = ledger.get_entry("ENTRY-old1")
            self.assertEqual((old["content"], old["content_status"]), ("inline 1", "INLINE"))
            ledger.append_fact("x", {"run_id": "r", "tool": "copilot", "source_type": "file_read",
                                     "content": "new", "source": "a.py"})
            self.assertTrue(all(r["ok"] for r in ledger.verify()))
            ledger._store.conn.close()
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
