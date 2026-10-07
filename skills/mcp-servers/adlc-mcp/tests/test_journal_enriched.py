"""Tests for enriched journal events used by the reasoning/logging observer.

Verifies coord.message, evidence.inference, evidence.decision events
carry proper payloads for the Stage Reasoning UI.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(src))

from tests._support import CI, DEVELOPER, CODE_REVIEWER, TempEnv
from adlc_mcp.app import build_modules
from adlc_mcp.kernel.errors import ValidationError


class EnrichedJournalCase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv("event_journal")
        self.registry = build_modules(self.env.config)
        self.api = self.registry.get("event_journal").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def add(self, event_type, payload=None, **kw):
        defaults = dict(run_id="run-1")
        defaults.update(kw)
        return self.api.append_journal(DEVELOPER, event_type=event_type, payload=payload, **defaults)


class TestCoordMessage(EnrichedJournalCase):
    def test_coord_message_recorded(self):
        e = self.add("coord.message", {
            "from_role": "developer",
            "to_role": "architect",
            "message": "Can we use gRPC instead of REST?",
            "message_type": "question",
        }, change_set_id="CS-1")
        self.assertEqual(e["event_type"], "coord.message")
        self.assertEqual(e["change_set_id"], "CS-1")

    def test_coord_message_queryable_by_type(self):
        self.add("coord.message", {"message": "Hello"}, change_set_id="CS-1")
        self.add("task.start", {"task_id": "T1"})
        results = self.api.query_journal(event_type="coord.message")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["event_type"], "coord.message")

    def test_multiple_coord_messages_ordered(self):
        self.add("coord.message", {"message": "First", "seq": 1})
        self.add("coord.message", {"message": "Second", "seq": 2})
        self.add("coord.message", {"message": "Third", "seq": 3})
        results = self.api.query_journal(event_type="coord.message")
        self.assertEqual(len(results), 3)
        messages = [r["payload"]["message"] for r in results]
        self.assertEqual(messages, ["First", "Second", "Third"])


class TestEvidenceJournalEvents(EnrichedJournalCase):
    def test_evidence_inference_event(self):
        e = self.add("evidence.inference", {
            "reasoning_chain": "Based on benchmarks, SQLite handles our workload",
            "inputs_considered": ["benchmark.md", "requirements.md"],
            "confidence": 0.85,
        })
        self.assertEqual(e["event_type"], "evidence.inference")

    def test_evidence_decision_with_alternatives(self):
        e = self.add("evidence.decision", {
            "chosen": "SQLite",
            "alternatives": ["PostgreSQL", "MySQL", "DynamoDB"],
            "rationale": "Simplicity for single-user CLI tool",
        })
        self.assertEqual(e["payload"]["chosen"], "SQLite")
        self.assertEqual(len(e["payload"]["alternatives"]), 3)


class TestStageEvents(EnrichedJournalCase):
    def test_stage_enter_with_objectives(self):
        e = self.add("stage.enter", {
            "stage": "IMPLEMENT",
            "lead_role": "developer",
            "model_id": "claude-haiku-4-5-20251001",
            "objectives": ["Build CLI commands", "Write unit tests"],
        })
        self.assertEqual(e["payload"]["stage"], "IMPLEMENT")
        self.assertEqual(e["payload"]["lead_role"], "developer")

    def test_stage_exit_with_summary(self):
        e = self.add("stage.exit", {
            "stage": "IMPLEMENT",
            "artifacts_produced": ["src/cli.py", "tests/test_cli.py"],
            "duration_seconds": 120,
        })
        self.assertEqual(len(e["payload"]["artifacts_produced"]), 2)

    def test_stage_gate_pass(self):
        e = self.add("stage.gate_pass", {
            "stage": "IMPLEMENT",
            "gate": "completion",
            "criteria_met": ["all ACs verified", "tests pass"],
        })
        self.assertEqual(e["event_type"], "stage.gate_pass")

    def test_stage_gate_fail(self):
        e = self.add("stage.gate_fail", {
            "stage": "IMPLEMENT",
            "gate": "completion",
            "failures": ["AC-3 not implemented"],
        })
        self.assertEqual(e["event_type"], "stage.gate_fail")


class TestTaskCheckpoint(EnrichedJournalCase):
    def test_checkpoint_with_progress(self):
        e = self.add("task.checkpoint", {
            "task_id": "T1",
            "progress_pct": 60,
            "artifacts_produced": ["src/models.py"],
            "blockers": [],
        })
        self.assertEqual(e["payload"]["progress_pct"], 60)


class TestFoldStateWithEnrichedEvents(EnrichedJournalCase):
    def test_fold_captures_decisions_from_evidence_events(self):
        self.add("session.join")
        self.add("evidence.decision", {"summary": "Use REST API"})
        self.add("evidence.decision", {"summary": "Use JSON storage"})
        state = self.api.fold_state("run-1")
        self.assertEqual(len(state["decisions"]), 2)
        summaries = [d["summary"] for d in state["decisions"]]
        self.assertIn("Use REST API", summaries)
        self.assertIn("Use JSON storage", summaries)

    def test_fold_tracks_current_stage(self):
        self.add("stage.enter", {"stage": "ARCHITECTURE"})
        self.add("stage.exit", {"stage": "ARCHITECTURE"})
        self.add("stage.enter", {"stage": "IMPLEMENT"})
        state = self.api.fold_state("run-1")
        self.assertEqual(state["current_stage"], "IMPLEMENT")
        self.assertGreaterEqual(len(state["stage_history"]), 1)


class TestVisibility(EnrichedJournalCase):
    def test_internal_visibility(self):
        e = self.add("coord.message", {"message": "internal note"},
                     visibility="internal")
        results = self.api.query_journal(run_id="run-1")
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
