"""Tests for the Concurrency Primitives module."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(src))

from adlc_mcp.modules.concurrency.store import ConcurrencyStore
from adlc_mcp.modules.concurrency.domain import CoordMessage


def _make_store() -> ConcurrencyStore:
    conn = sqlite3.connect(":memory:")
    store = ConcurrencyStore(conn)
    store.migrate()
    return store


class TestTaskClaims(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()

    def test_claim_succeeds(self):
        ok, claim = self.store.claim_task("T-1", "agent-1")
        self.assertTrue(ok)
        self.assertEqual(claim.task_id, "T-1")
        self.assertEqual(claim.actor_id, "agent-1")

    def test_duplicate_claim_fails(self):
        self.store.claim_task("T-1", "agent-1")
        ok, claim = self.store.claim_task("T-1", "agent-2")
        self.assertFalse(ok)
        self.assertEqual(claim.actor_id, "agent-1")

    def test_same_actor_duplicate_fails(self):
        self.store.claim_task("T-1", "agent-1")
        ok, _ = self.store.claim_task("T-1", "agent-1")
        self.assertFalse(ok)

    def test_release_then_reclaim(self):
        self.store.claim_task("T-1", "agent-1")
        released = self.store.release_task("T-1", "agent-1")
        self.assertTrue(released)
        ok, claim = self.store.claim_task("T-1", "agent-2")
        self.assertTrue(ok)
        self.assertEqual(claim.actor_id, "agent-2")

    def test_release_wrong_actor(self):
        self.store.claim_task("T-1", "agent-1")
        released = self.store.release_task("T-1", "agent-2")
        self.assertFalse(released)

    def test_multiple_tasks_independent(self):
        ok1, _ = self.store.claim_task("T-1", "agent-1")
        ok2, _ = self.store.claim_task("T-2", "agent-1")
        ok3, _ = self.store.claim_task("T-3", "agent-2")
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertTrue(ok3)


class TestFileIntents(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()

    def test_declare_intent(self):
        intent = self.store.declare_file_intent(
            "i-1", "agent-1", "developer", ["src/main.py", "src/utils.py"])
        self.assertEqual(intent.intent_id, "i-1")
        self.assertEqual(len(intent.files), 2)

    def test_no_conflict_same_actor(self):
        self.store.declare_file_intent("i-1", "agent-1", "developer", ["src/main.py"])
        conflicts = self.store.check_conflicts("agent-1", ["src/main.py"])
        self.assertEqual(len(conflicts), 0)

    def test_file_conflict_different_actors(self):
        self.store.declare_file_intent("i-1", "agent-1", "developer", ["src/main.py"])
        conflicts = self.store.check_conflicts("agent-2", ["src/main.py"])
        self.assertTrue(len(conflicts) > 0)
        self.assertEqual(conflicts[0].file_path, "src/main.py")
        self.assertEqual(conflicts[0].conflict_type, "file_overlap")

    def test_directory_conflict(self):
        self.store.declare_file_intent("i-1", "agent-1", "developer", ["src/auth/login.py"])
        conflicts = self.store.check_conflicts("agent-2", ["src/auth/register.py"])
        dir_conflicts = [c for c in conflicts if c.conflict_type == "directory_overlap"]
        self.assertTrue(len(dir_conflicts) > 0)

    def test_no_conflict_different_dirs(self):
        self.store.declare_file_intent("i-1", "agent-1", "developer", ["src/auth/login.py"])
        conflicts = self.store.check_conflicts("agent-2", ["src/billing/invoice.py"])
        self.assertEqual(len(conflicts), 0)


class TestCoordMessages(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()

    def test_send_and_receive(self):
        msg = CoordMessage(
            message_id="m-1", from_actor="agent-1", from_role="developer",
            to_actor="agent-2", content="I need src/main.py",
            sent_at="2026-01-01T00:00:00Z")
        self.store.send_message(msg)
        messages = self.store.get_messages("agent-2")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "I need src/main.py")

    def test_messages_for_wrong_actor_empty(self):
        msg = CoordMessage(
            message_id="m-1", from_actor="agent-1", from_role="developer",
            to_actor="agent-2", content="hello", sent_at="2026-01-01T00:00:00Z")
        self.store.send_message(msg)
        messages = self.store.get_messages("agent-3")
        self.assertEqual(len(messages), 0)


class TestTools(unittest.TestCase):
    def test_tools_registered(self):
        from adlc_mcp.modules.concurrency.tools import register_tools
        server = MagicMock()
        api = MagicMock()
        identity = MagicMock()
        identity.actor_id = "agent-1"
        identity.agent_role = "developer"
        tools = register_tools(server, api, identity)
        self.assertEqual(len(tools), 5)


if __name__ == "__main__":
    unittest.main()
