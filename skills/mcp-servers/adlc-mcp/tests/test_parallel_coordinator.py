"""Tests for the Parallel Execution Coordinator module."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(src))

from adlc_mcp.modules.parallel_coordinator.domain import MAX_WORKERS, WorkItem, ParallelPlan
from adlc_mcp.modules.parallel_coordinator.store import ParallelCoordinatorStore


def _make_store() -> ParallelCoordinatorStore:
    conn = sqlite3.connect(":memory:")
    store = ParallelCoordinatorStore(conn)
    store.migrate()
    return store


def _make_plan(store, n_items=3):
    items = [WorkItem(item_id=f"item-{i}", change_set_id="CS-1",
                      description=f"Task {i}", planned_files=[f"src/file{i}.py"])
             for i in range(n_items)]
    plan = ParallelPlan(plan_id="plan-1", change_set_id="CS-1", items=items)
    store.create_plan(plan, "2026-01-01T00:00:00Z")
    return plan


class TestCreatePlan(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()

    def test_create_plan(self):
        result = _make_plan(self.store)
        self.assertEqual(len(result.items), 3)

    def test_plan_retrievable(self):
        _make_plan(self.store)
        plan = self.store.get_plan("plan-1")
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan["items"]), 3)
        self.assertEqual(plan["change_set_id"], "CS-1")

    def test_max_workers_capped(self):
        items = [WorkItem(item_id=f"item-{i}", change_set_id="CS-1",
                          description=f"Task {i}") for i in range(20)]
        plan = ParallelPlan(plan_id="plan-big", change_set_id="CS-1",
                            items=items, max_workers=20)
        self.store.create_plan(plan, "2026-01-01T00:00:00Z")
        stored = self.store.get_plan("plan-big")
        self.assertLessEqual(stored["max_workers"], MAX_WORKERS)


class TestStartWorker(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()
        _make_plan(self.store)

    def test_start_worker(self):
        result = self.store.start_worker("item-0", "worker-1", "/tmp/wt/cs1-0",
                                         "2026-01-01T00:01:00Z")
        self.assertEqual(result["state"], "running")
        self.assertEqual(result["worker_id"], "worker-1")

    def test_cannot_start_running_item(self):
        self.store.start_worker("item-0", "worker-1", "/tmp/wt/cs1-0",
                                "2026-01-01T00:01:00Z")
        result = self.store.start_worker("item-0", "worker-2", "/tmp/wt/cs1-0b",
                                         "2026-01-01T00:02:00Z")
        self.assertIn("error", result)

    def test_max_workers_enforced(self):
        items = [WorkItem(item_id=f"mw-{i}", change_set_id="CS-2",
                          description=f"T{i}") for i in range(10)]
        plan = ParallelPlan(plan_id="plan-2", change_set_id="CS-2",
                            items=items, max_workers=2)
        self.store.create_plan(plan, "2026-01-01T00:00:00Z")
        self.store.start_worker("mw-0", "w1", "/wt/0", "2026-01-01T00:01:00Z")
        self.store.start_worker("mw-1", "w2", "/wt/1", "2026-01-01T00:01:00Z")
        result = self.store.start_worker("mw-2", "w3", "/wt/2", "2026-01-01T00:02:00Z")
        self.assertIn("error", result)
        self.assertIn("max workers", result["error"])


class TestWorkerStatus(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()
        _make_plan(self.store)

    def test_all_pending_initially(self):
        workers = self.store.get_worker_status("plan-1")
        self.assertEqual(len(workers), 3)
        for w in workers:
            self.assertEqual(w.state, "pending")

    def test_state_reflects_running(self):
        self.store.start_worker("item-0", "w1", "/wt/0", "2026-01-01T00:01:00Z")
        workers = self.store.get_worker_status("plan-1")
        states = {w.item_id: w.state for w in workers}
        self.assertEqual(states["item-0"], "running")
        self.assertEqual(states["item-1"], "pending")


class TestStopAllWorkers(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()
        _make_plan(self.store)

    def test_stop_all(self):
        self.store.start_worker("item-0", "w1", "/wt/0", "2026-01-01T00:01:00Z")
        result = self.store.stop_all_workers("plan-1", "2026-01-01T00:02:00Z")
        self.assertEqual(result["stopped"], 3)
        workers = self.store.get_worker_status("plan-1")
        for w in workers:
            self.assertEqual(w.state, "stopped")


class TestIntegrateResults(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()
        _make_plan(self.store, n_items=2)

    def test_not_ready_if_running(self):
        self.store.start_worker("item-0", "w1", "/wt/0", "2026-01-01T00:01:00Z")
        from adlc_mcp.modules.parallel_coordinator.api import ParallelCoordinator
        conn = sqlite3.connect(":memory:")
        # Access store method directly
        plan = self.store.get_plan("plan-1")
        incomplete = [i for i in plan["items"] if i["state"] not in ("completed", "stopped")]
        self.assertTrue(len(incomplete) > 0)

    def test_ready_when_all_completed(self):
        self.store.start_worker("item-0", "w1", "/wt/0", "2026-01-01T00:01:00Z")
        self.store.start_worker("item-1", "w2", "/wt/1", "2026-01-01T00:01:00Z")
        self.store.update_worker_state("item-0", "completed", {"ok": True}, "2026-01-01T00:05:00Z")
        self.store.update_worker_state("item-1", "completed", {"ok": True}, "2026-01-01T00:06:00Z")
        plan = self.store.get_plan("plan-1")
        incomplete = [i for i in plan["items"] if i["state"] not in ("completed", "stopped")]
        self.assertEqual(len(incomplete), 0)


class TestTools(unittest.TestCase):
    def test_tools_registered(self):
        from adlc_mcp.modules.parallel_coordinator.tools import register_tools
        server = MagicMock()
        api = MagicMock()
        identity = MagicMock()
        identity.actor_id = "agent-1"
        identity.agent_role = "developer"
        tools = register_tools(server, api, identity)
        self.assertEqual(len(tools), 5)


if __name__ == "__main__":
    unittest.main()
