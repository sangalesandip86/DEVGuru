"""Tests for all evidence classifications and answer-linking.

Verifies QUESTION, INFERENCE, ASSUMPTION entries work correctly,
answers_entry_id links answers to questions, and derived status
(OPEN/ANSWERED/EXPIRED/CHALLENGED) is computed properly.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

src = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(src))

from tests._support import CI, DEVELOPER, HUMAN_LEAD, TempEnv
from adlc_mcp.app import build_modules
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError


class ClassificationTestCase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv("evidence_ledger")
        self.registry = build_modules(self.env.config)
        self.ledger = self.registry.get("evidence_ledger").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def record(self, classification, content="test", **kw):
        defaults = dict(run_id="run-1", source_type="agent-output")
        defaults.update(kw)
        return self.ledger.record_evidence(DEVELOPER, classification=classification, content=content, **defaults)


class TestDecision(ClassificationTestCase):
    def test_decision_recorded(self):
        e = self.record("DECISION", "Use PostgreSQL")
        self.assertEqual(e["classification"], "DECISION")
        self.assertIn("ENTRY-", e["entry_id"])

    def test_decision_queryable(self):
        self.record("DECISION", "Use Redis", change_set_id="CS-1")
        results = self.ledger.query_evidence(DEVELOPER, classification="DECISION", change_set_id="CS-1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "Use Redis")


class TestInference(ClassificationTestCase):
    def test_inference_requires_input_references(self):
        with self.assertRaises(ValidationError):
            self.record("INFERENCE", "Some conclusion without references")

    def test_inference_with_valid_references(self):
        fact = self.record("DECISION", "Baseline decision")
        e = self.record("INFERENCE", "Performance looks acceptable based on decision",
                        input_references=[fact["entry_id"]],
                        metadata={"confidence": 0.9})
        self.assertEqual(e["classification"], "INFERENCE")

    def test_inference_queryable_by_classification(self):
        d = self.record("DECISION", "Something")
        self.record("INFERENCE", "Derived from above", input_references=[d["entry_id"]])
        results = self.ledger.query_evidence(DEVELOPER, classification="INFERENCE")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["classification"], "INFERENCE")


class TestQuestion(ClassificationTestCase):
    def test_question_needs_blocking_metadata(self):
        with self.assertRaises(ValidationError):
            self.record("QUESTION", "What about caching?")

    def test_blocking_question(self):
        e = self.record("QUESTION", "What auth provider to use?",
                        metadata={"blocking": True})
        self.assertEqual(e["classification"], "QUESTION")

    def test_non_blocking_question(self):
        e = self.record("QUESTION", "Should we add metrics?",
                        metadata={"blocking": False})
        self.assertEqual(e["classification"], "QUESTION")

    def test_question_derived_status_open(self):
        self.record("QUESTION", "Open question?",
                    metadata={"blocking": False}, change_set_id="CS-Q")
        results = self.ledger.query_evidence(DEVELOPER, classification="QUESTION", change_set_id="CS-Q")
        self.assertEqual(results[0]["derived_status"], "OPEN")


class TestAssumption(ClassificationTestCase):
    def test_assumption_needs_impact_and_expiry(self):
        with self.assertRaises(ValidationError):
            self.record("ASSUMPTION", "Users will be < 1000")
        with self.assertRaises(ValidationError):
            self.record("ASSUMPTION", "Users will be < 1000",
                        metadata={"impact": "LOW"})

    def test_valid_assumption(self):
        e = self.record("ASSUMPTION", "Single-region deployment sufficient",
                        metadata={"impact": "MEDIUM", "expires_at": "2027-06-01T00:00:00Z"})
        self.assertEqual(e["classification"], "ASSUMPTION")

    def test_assumption_queryable(self):
        self.record("ASSUMPTION", "Max 10k records",
                    metadata={"impact": "LOW", "expires_at": "2027-01-01T00:00:00Z"},
                    change_set_id="CS-A")
        results = self.ledger.query_evidence(DEVELOPER, classification="ASSUMPTION", change_set_id="CS-A")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["metadata"]["impact"], "LOW")

    def test_assumption_derived_status_open(self):
        self.record("ASSUMPTION", "Capacity assumption",
                    metadata={"impact": "HIGH", "expires_at": "2027-06-01T00:00:00Z"},
                    change_set_id="CS-AS")
        results = self.ledger.query_evidence(DEVELOPER, classification="ASSUMPTION", change_set_id="CS-AS")
        self.assertEqual(results[0]["derived_status"], "OPEN")


class TestAnswerLinking(ClassificationTestCase):
    def test_answer_links_to_question(self):
        q = self.record("QUESTION", "Which DB engine?",
                        metadata={"blocking": True}, change_set_id="CS-1")
        a = self.record("DECISION", "Use SQLite for simplicity",
                        answers_entry_id=q["entry_id"], change_set_id="CS-1")
        self.assertIsNotNone(a["entry_id"])

    def test_answered_question_status(self):
        q = self.record("QUESTION", "Which DB engine?",
                        metadata={"blocking": True}, change_set_id="CS-ANS")
        self.record("DECISION", "Use SQLite",
                    answers_entry_id=q["entry_id"], change_set_id="CS-ANS")
        results = self.ledger.query_evidence(DEVELOPER, classification="QUESTION", change_set_id="CS-ANS")
        self.assertEqual(results[0]["derived_status"], "ANSWERED")

    def test_answer_links_to_assumption(self):
        assumption = self.record("ASSUMPTION", "Max 100 concurrent users",
                                 metadata={"impact": "HIGH", "expires_at": "2027-01-01T00:00:00Z"},
                                 change_set_id="CS-1")
        answer = self.record("DECISION", "Validated: load test shows 200 concurrent OK",
                             answers_entry_id=assumption["entry_id"], change_set_id="CS-1")
        self.assertIsNotNone(answer["entry_id"])

    def test_answer_to_non_question_rejected(self):
        d = self.record("DECISION", "Use REST")
        with self.assertRaises(ValidationError):
            self.record("DECISION", "Actually use GraphQL", answers_entry_id=d["entry_id"])

    def test_answer_to_nonexistent_rejected(self):
        with self.assertRaises(Exception):
            self.record("DECISION", "Answer", answers_entry_id="ENTRY-nonexistent")


class TestAgentCannotWriteFact(ClassificationTestCase):
    def test_agent_cannot_record_fact(self):
        with self.assertRaises((PermissionDenied, ValidationError)):
            self.record("FACT", "Test result: 100% pass rate")


class TestCorrection(ClassificationTestCase):
    def test_correction_challenges_entry(self):
        original = self.record("DECISION", "Use MySQL")
        correction = self.ledger.record_correction(
            DEVELOPER, parent_entry_id=original["entry_id"], run_id="run-1",
            content="MySQL too heavy, switching to SQLite",
            source_type="agent-output",
        )
        self.assertIsNotNone(correction["entry_id"])

    def test_correction_sets_challenged_status(self):
        original = self.record("DECISION", "Use MySQL", change_set_id="CS-CORR")
        self.ledger.record_correction(
            DEVELOPER, parent_entry_id=original["entry_id"], run_id="run-1",
            content="Switching to SQLite",
            source_type="agent-output",
        )
        results = self.ledger.query_evidence(DEVELOPER, change_set_id="CS-CORR")
        orig = [e for e in results if e["entry_id"] == original["entry_id"]]
        self.assertEqual(orig[0]["derived_status"], "CHALLENGED")


class TestModelProvenance(ClassificationTestCase):
    def test_model_id_from_credential(self):
        e = self.record("DECISION", "Approach A")
        results = self.ledger.query_evidence(DEVELOPER)
        entry = [r for r in results if r["entry_id"] == e["entry_id"]][0]
        self.assertEqual(entry["model_id"], "model-a")

    def test_model_id_mismatch_rejected(self):
        with self.assertRaises(ValidationError):
            self.record("DECISION", "Approach A", model_id="different-model")


class TestMixedClassifications(ClassificationTestCase):
    def test_query_returns_all_classifications(self):
        d = self.record("DECISION", "D1", change_set_id="CS-MIX")
        self.record("INFERENCE", "I1", change_set_id="CS-MIX",
                    input_references=[d["entry_id"]])
        self.record("QUESTION", "Q1", change_set_id="CS-MIX",
                    metadata={"blocking": False})
        self.record("ASSUMPTION", "A1", change_set_id="CS-MIX",
                    metadata={"impact": "LOW", "expires_at": "2027-01-01T00:00:00Z"})
        results = self.ledger.query_evidence(DEVELOPER, change_set_id="CS-MIX")
        classifications = {e["classification"] for e in results}
        self.assertEqual(classifications, {"DECISION", "INFERENCE", "QUESTION", "ASSUMPTION"})

    def test_all_entries_have_agent_role(self):
        self.record("DECISION", "D", change_set_id="CS-ACTOR")
        results = self.ledger.query_evidence(DEVELOPER, change_set_id="CS-ACTOR")
        for entry in results:
            self.assertIn("agent_role", entry)
            self.assertEqual(entry["agent_role"], "developer")


if __name__ == "__main__":
    unittest.main()
