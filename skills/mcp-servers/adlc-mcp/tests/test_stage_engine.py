"""Tests for the Stage Transition Engine module."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(src))

from adlc_mcp.modules.stage_engine.domain import TRANSITION_GRAPH, STAGES, SIDE_STATES, TransitionRequest
from adlc_mcp.modules.stage_engine.store import StageEngineStore


def _make_store() -> StageEngineStore:
    conn = sqlite3.connect(":memory:")
    store = StageEngineStore(conn)
    store.migrate()
    return store


class TestTransitionGraph(unittest.TestCase):
    def test_all_stages_in_graph(self):
        for stage in STAGES:
            self.assertIn(stage, TRANSITION_GRAPH)

    def test_allowed_next_contains_valid_stages(self):
        all_valid = set(STAGES) | set(SIDE_STATES)
        for stage, entry in TRANSITION_GRAPH.items():
            for next_stage in entry["allowed_next"]:
                self.assertIn(next_stage, all_valid,
                              f"{stage} -> {next_stage} references unknown stage")

    def test_every_stage_has_required_fields(self):
        for stage, entry in TRANSITION_GRAPH.items():
            self.assertIn("allowed_next", entry, f"{stage} missing allowed_next")
            self.assertIn("required_roles", entry, f"{stage} missing required_roles")
            self.assertIn("required_outputs", entry, f"{stage} missing required_outputs")
            self.assertIn("gate", entry, f"{stage} missing gate")

    def test_learn_is_terminal(self):
        self.assertEqual(TRANSITION_GRAPH["LEARN"]["allowed_next"], [])

    def test_release_requires_human(self):
        self.assertIn("human", TRANSITION_GRAPH["RELEASE"]["required_roles"])


class TestValidateTransition(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()

    def test_valid_transition(self):
        req = TransitionRequest(
            change_set_id="CS-1", from_stage="INTAKE", to_stage="PLAN",
            actor_role="product-owner", outputs=["requirement_id"])
        result = self.store.validate_transition(req)
        self.assertTrue(result.allowed)

    def test_invalid_transition_wrong_target(self):
        req = TransitionRequest(
            change_set_id="CS-1", from_stage="INTAKE", to_stage="IMPLEMENT",
            actor_role="product-owner", outputs=["requirement_id"])
        result = self.store.validate_transition(req)
        self.assertFalse(result.allowed)
        self.assertIn("not allowed", result.reason)

    def test_missing_outputs(self):
        req = TransitionRequest(
            change_set_id="CS-1", from_stage="INTAKE", to_stage="PLAN",
            actor_role="product-owner", outputs=[])
        result = self.store.validate_transition(req)
        self.assertFalse(result.allowed)
        self.assertIn("requirement_id", result.missing_outputs)

    def test_wrong_role(self):
        req = TransitionRequest(
            change_set_id="CS-1", from_stage="INTAKE", to_stage="PLAN",
            actor_role="developer", outputs=["requirement_id"])
        result = self.store.validate_transition(req)
        self.assertFalse(result.allowed)
        self.assertTrue(len(result.missing_roles) > 0)

    def test_side_state_always_allowed(self):
        req = TransitionRequest(
            change_set_id="CS-1", from_stage="IMPLEMENT", to_stage="BLOCKED",
            actor_role="developer", outputs=[])
        result = self.store.validate_transition(req)
        self.assertTrue(result.allowed)

    def test_unknown_from_stage(self):
        req = TransitionRequest(
            change_set_id="CS-1", from_stage="NONEXISTENT", to_stage="PLAN",
            actor_role="developer", outputs=[])
        result = self.store.validate_transition(req)
        self.assertFalse(result.allowed)
        self.assertIn("unknown", result.reason)

    def test_cannot_transition_from_side_state(self):
        req = TransitionRequest(
            change_set_id="CS-1", from_stage="BLOCKED", to_stage="IMPLEMENT",
            actor_role="developer", outputs=[])
        result = self.store.validate_transition(req)
        self.assertFalse(result.allowed)


class TestRecordTransition(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()

    def test_record_valid_transition(self):
        req = TransitionRequest(
            change_set_id="CS-1", from_stage="INTAKE", to_stage="PLAN",
            actor_role="product-owner", outputs=["requirement_id"])
        result = self.store.validate_transition(req)
        record = self.store.record_transition(
            "entry-1", req, result, "AGENT", "agent-1", "2026-01-01T00:00:00Z")
        self.assertTrue(record["allowed"])

    def test_current_stage_updated_after_transition(self):
        req = TransitionRequest(
            change_set_id="CS-1", from_stage="INTAKE", to_stage="PLAN",
            actor_role="product-owner", outputs=["requirement_id"])
        result = self.store.validate_transition(req)
        self.store.record_transition(
            "entry-1", req, result, "AGENT", "agent-1", "2026-01-01T00:00:00Z")
        state = self.store.get_current_stage("CS-1")
        self.assertEqual(state.current_stage, "PLAN")
        self.assertEqual(state.previous_stage, "INTAKE")

    def test_transitions_accumulate(self):
        req1 = TransitionRequest(
            change_set_id="CS-1", from_stage="INTAKE", to_stage="PLAN",
            actor_role="product-owner", outputs=["requirement_id"])
        r1 = self.store.validate_transition(req1)
        self.store.record_transition("e1", req1, r1, "AGENT", "a1", "2026-01-01T00:00:00Z")

        req2 = TransitionRequest(
            change_set_id="CS-1", from_stage="PLAN", to_stage="IMPLEMENT",
            actor_role="product-planner", outputs=["plan_id", "story_ids"])
        r2 = self.store.validate_transition(req2)
        self.store.record_transition("e2", req2, r2, "AGENT", "a1", "2026-01-01T01:00:00Z")

        state = self.store.get_current_stage("CS-1")
        self.assertEqual(state.current_stage, "IMPLEMENT")
        self.assertEqual(len(state.transitions), 2)


class TestGetCurrentStage(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()

    def test_default_is_intake(self):
        state = self.store.get_current_stage("CS-NEW")
        self.assertEqual(state.current_stage, "INTAKE")
        self.assertEqual(state.allowed_next, ["ARCHITECTURE", "PLAN"])

    def test_graph_returned(self):
        graph = self.store.get_transition_graph()
        self.assertIn("stages", graph)
        self.assertIn("side_states", graph)
        self.assertIn("stage_order", graph)
        self.assertEqual(len(graph["stages"]), 10)


class TestTools(unittest.TestCase):
    def test_tools_registered(self):
        from adlc_mcp.modules.stage_engine.tools import register_tools
        server = MagicMock()
        api = MagicMock()
        identity = MagicMock()
        identity.agent_role = "developer"
        tools = register_tools(server, api, identity)
        self.assertEqual(len(tools), 4)


if __name__ == "__main__":
    unittest.main()
