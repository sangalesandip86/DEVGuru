"""Tests for serve.py API endpoints with real module data.

Exercises the full stack: modules -> API -> JSON response for evidence,
journal, handoffs, tasks, status-history, risk-history, overview, and trace.
Also tests the Stage Reasoning data flow end-to-end.
"""
from __future__ import annotations

import json
import sys
import unittest
from http.client import HTTPConnection
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(src))

from tests._support import CI, CODE_REVIEWER, DEVELOPER, HUMAN_LEAD, SECURITY, TempEnv
from adlc_mcp.app import build_modules
from adlc_mcp.serve import start_hub, stop_hub

ALL_MODULES = "evidence_ledger,change_management,event_journal,stage_engine"


def _get(port, path):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


def _json(port, path):
    resp, body = _get(port, path)
    return resp, json.loads(body)


class TestServeWithData(unittest.TestCase):
    """Boots a real server with all modules, seeds data, then tests endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.env = TempEnv(ALL_MODULES)
        cls.registry = build_modules(cls.env.config)
        cls.cm = cls.registry.get("change_management").api
        cls.ledger = cls.registry.get("evidence_ledger").api
        cls.journal = cls.registry.get("event_journal").api
        cls.server, cls.port, _ = start_hub(cls.registry, port=0)
        cls._seed_data()

    @classmethod
    def tearDownClass(cls):
        stop_hub(cls.server)
        cls.registry.close()
        cls.env.close()

    @classmethod
    def _seed_data(cls):
        cs = cls.cm.create_change_set(
            DEVELOPER, title="Test CS", requirements=["REQ-1"],
            repositories=["repo-a"], story_refs=["ST-1"],
        )
        cls.cs_id = cs["id"]

        cls.cm.update_status(DEVELOPER, change_set_id=cls.cs_id, status="SCOPED", reason="scoped")
        cls.cm.compute_risk_tier(DEVELOPER, change_set_id=cls.cs_id, paths=["README.md"])
        cls.cm.update_status(DEVELOPER, change_set_id=cls.cs_id, status="PLANNED", reason="planned")

        cls.cm.record_task(DEVELOPER, change_set_id=cls.cs_id, task_id="T1", owner_role="developer")

        cls.cm.record_handoff(
            DEVELOPER, change_set_id=cls.cs_id, to_role="code-reviewer",
            payload={"summary": "Implementation done", "open_questions": ["Perf OK?"]},
        )

        cls.decision = cls.ledger.record_evidence(
            DEVELOPER, run_id="run-1", classification="DECISION",
            content="Use SQLite for storage",
            source_type="agent-output", change_set_id=cls.cs_id,
        )

        cls.inference = cls.ledger.record_evidence(
            DEVELOPER, run_id="run-1", classification="INFERENCE",
            content="SQLite handles concurrent reads well enough for this workload",
            source_type="agent-output", change_set_id=cls.cs_id,
            input_references=[cls.decision["entry_id"]],
            metadata={"confidence": 0.85},
        )

        cls.question = cls.ledger.record_evidence(
            DEVELOPER, run_id="run-1", classification="QUESTION",
            content="Should we add an index on created_at?",
            source_type="agent-output", change_set_id=cls.cs_id,
            metadata={"blocking": False},
        )

        cls.assumption = cls.ledger.record_evidence(
            DEVELOPER, run_id="run-1", classification="ASSUMPTION",
            content="Max 10k tasks per user",
            source_type="agent-output", change_set_id=cls.cs_id,
            metadata={"impact": "LOW", "expires_at": "2027-01-01T00:00:00Z"},
        )

        cls.journal.append_journal(
            DEVELOPER, run_id="run-1", event_type="stage.enter",
            payload={"stage": "IMPLEMENT"}, change_set_id=cls.cs_id,
        )
        cls.journal.append_journal(
            DEVELOPER, run_id="run-1", event_type="evidence.decision",
            payload={"summary": "Use SQLite"}, change_set_id=cls.cs_id,
        )
        cls.journal.append_journal(
            DEVELOPER, run_id="run-1", event_type="coord.message",
            payload={"from_role": "developer", "to_role": "architect",
                     "message": "Confirmed SQLite approach"},
            change_set_id=cls.cs_id,
        )
        cls.journal.append_journal(
            DEVELOPER, run_id="run-1", event_type="stage.exit",
            payload={"stage": "IMPLEMENT"}, change_set_id=cls.cs_id,
        )

    # ---- API: overview ----

    def test_overview_counts(self):
        resp, data = _json(self.port, "/api/overview")
        self.assertEqual(resp.status, 200)
        self.assertGreaterEqual(data["change_sets"], 1)
        self.assertGreaterEqual(data["evidence"], 4)
        self.assertGreaterEqual(data["handoffs"], 1)
        self.assertGreaterEqual(data["tasks"], 1)
        self.assertGreaterEqual(data["journal_events"], 4)
        self.assertIn("developer", data["roles"])

    def test_overview_stages_seen(self):
        resp, data = _json(self.port, "/api/overview")
        self.assertEqual(resp.status, 200)
        self.assertIn("IMPLEMENT", data["stages_seen"])

    # ---- API: changesets ----

    def test_changesets_list(self):
        resp, data = _json(self.port, "/api/changesets")
        self.assertEqual(resp.status, 200)
        self.assertIsInstance(data, list)
        self.assertTrue(any(cs["id"] == self.cs_id for cs in data))

    def test_changeset_detail(self):
        resp, data = _json(self.port, f"/api/changeset/{self.cs_id}")
        self.assertEqual(resp.status, 200)
        self.assertEqual(data["id"], self.cs_id)
        self.assertEqual(data["status"], "PLANNED")
        self.assertIn("story_refs", data)

    def test_changeset_not_found(self):
        resp, data = _json(self.port, "/api/changeset/CS-nonexistent")
        self.assertEqual(resp.status, 404)

    # ---- API: evidence ----

    def test_evidence_all_classifications(self):
        resp, data = _json(self.port, "/api/evidence?change_set_id=" + self.cs_id)
        self.assertEqual(resp.status, 200)
        classifications = {e["classification"] for e in data}
        self.assertIn("DECISION", classifications)
        self.assertIn("INFERENCE", classifications)
        self.assertIn("QUESTION", classifications)
        self.assertIn("ASSUMPTION", classifications)

    def test_evidence_without_cs_id(self):
        resp, data = _json(self.port, "/api/evidence")
        self.assertEqual(resp.status, 200)
        self.assertGreaterEqual(len(data), 4)

    def test_evidence_question_has_blocking_metadata(self):
        resp, data = _json(self.port, "/api/evidence?change_set_id=" + self.cs_id)
        questions = [e for e in data if e["classification"] == "QUESTION"]
        self.assertGreater(len(questions), 0)
        self.assertIn("blocking", questions[0]["metadata"])

    def test_evidence_assumption_has_impact_and_expiry(self):
        resp, data = _json(self.port, "/api/evidence?change_set_id=" + self.cs_id)
        assumptions = [e for e in data if e["classification"] == "ASSUMPTION"]
        self.assertGreater(len(assumptions), 0)
        self.assertIn("impact", assumptions[0]["metadata"])
        self.assertIn("expires_at", assumptions[0]["metadata"])

    def test_evidence_inference_has_references(self):
        resp, data = _json(self.port, "/api/evidence?change_set_id=" + self.cs_id)
        inferences = [e for e in data if e["classification"] == "INFERENCE"]
        self.assertGreater(len(inferences), 0)
        self.assertIsNotNone(inferences[0].get("input_references"))

    # ---- API: journal ----

    def test_journal_by_cs(self):
        resp, data = _json(self.port, "/api/journal?change_set_id=" + self.cs_id)
        self.assertEqual(resp.status, 200)
        types = {e["event_type"] for e in data}
        self.assertIn("stage.enter", types)
        self.assertIn("evidence.decision", types)
        self.assertIn("coord.message", types)
        self.assertIn("stage.exit", types)

    def test_coord_message_has_role_info(self):
        resp, data = _json(self.port, "/api/journal?change_set_id=" + self.cs_id)
        messages = [e for e in data if e["event_type"] == "coord.message"]
        self.assertGreater(len(messages), 0)
        self.assertEqual(messages[0]["payload"]["from_role"], "developer")
        self.assertEqual(messages[0]["payload"]["to_role"], "architect")

    def test_stage_enter_exit_pairs(self):
        resp, data = _json(self.port, "/api/journal?change_set_id=" + self.cs_id)
        enters = [e for e in data if e["event_type"] == "stage.enter"]
        exits = [e for e in data if e["event_type"] == "stage.exit"]
        self.assertGreater(len(enters), 0)
        self.assertGreater(len(exits), 0)
        self.assertEqual(enters[0]["payload"]["stage"], "IMPLEMENT")

    # ---- API: trace ----

    def test_trace_all_events(self):
        resp, data = _json(self.port, "/api/trace?change_set_id=" + self.cs_id)
        self.assertEqual(resp.status, 200)
        self.assertGreaterEqual(len(data), 4)

    def test_trace_filtered_by_type(self):
        resp, data = _json(self.port, "/api/trace?event_type=coord.message")
        self.assertEqual(resp.status, 200)
        for e in data:
            self.assertEqual(e["event_type"], "coord.message")

    # ---- API: handoffs ----

    def test_handoffs_all(self):
        resp, data = _json(self.port, "/api/handoffs")
        self.assertEqual(resp.status, 200)
        self.assertTrue(any(h["to_role"] == "code-reviewer" for h in data))

    def test_handoffs_by_cs(self):
        resp, data = _json(self.port, "/api/handoffs?change_set_id=" + self.cs_id)
        self.assertEqual(resp.status, 200)
        self.assertGreaterEqual(len(data), 1)

    def test_handoff_payload_has_open_questions(self):
        resp, data = _json(self.port, "/api/handoffs?change_set_id=" + self.cs_id)
        with_questions = [h for h in data
                          if isinstance(h.get("payload"), dict) and h["payload"].get("open_questions")]
        self.assertGreater(len(with_questions), 0)

    # ---- API: tasks ----

    def test_tasks_all(self):
        resp, data = _json(self.port, "/api/tasks")
        self.assertEqual(resp.status, 200)
        self.assertTrue(any(t["id"] == "T1" for t in data))

    def test_tasks_by_cs(self):
        resp, data = _json(self.port, "/api/tasks?change_set_id=" + self.cs_id)
        self.assertEqual(resp.status, 200)
        self.assertGreaterEqual(len(data), 1)

    # ---- API: status-history ----

    def test_status_history(self):
        resp, data = _json(self.port, "/api/status-history")
        self.assertEqual(resp.status, 200)
        self.assertGreaterEqual(len(data), 2)

    def test_status_history_by_cs(self):
        resp, data = _json(self.port, "/api/status-history?change_set_id=" + self.cs_id)
        self.assertEqual(resp.status, 200)
        statuses = [h["to_status"] for h in data]
        self.assertIn("SCOPED", statuses)
        self.assertIn("PLANNED", statuses)

    # ---- API: risk-history ----

    def test_risk_history(self):
        resp, data = _json(self.port, "/api/risk-history")
        self.assertEqual(resp.status, 200)
        self.assertGreaterEqual(len(data), 1)

    def test_risk_history_by_cs(self):
        resp, data = _json(self.port, "/api/risk-history?change_set_id=" + self.cs_id)
        self.assertEqual(resp.status, 200)
        self.assertTrue(any(r["final_tier"] == "LOW" for r in data))


if __name__ == "__main__":
    unittest.main()
