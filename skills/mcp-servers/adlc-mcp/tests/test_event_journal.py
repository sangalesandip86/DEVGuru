import unittest
from datetime import datetime, timedelta, timezone

from tests._support import CI, DEVELOPER, TempEnv

from adlc_mcp.app import build_modules
from adlc_mcp.kernel.errors import ValidationError
from adlc_mcp.modules.event_journal.api import JournalUnreadable
from adlc_mcp.modules.event_journal.domain import JournalEntry


class JournalCase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv("event_journal")
        self.registry = build_modules(self.env.config)
        self.api = self.registry.get("event_journal").api
        self.store = self.api._store

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def add(self, event_type, payload=None, run_id="run-1", who=DEVELOPER, **kw):
        return self.api.append_journal(who, run_id=run_id, event_type=event_type, payload=payload, **kw)


class TestAppendQuery(JournalCase):
    def test_append_and_query(self):
        e = self.add("task.start", {"task_id": "T1"}, change_set_id="CS-1")
        self.assertEqual(e["actor_id"], DEVELOPER.actor_id)
        self.assertEqual(e["agent_role"], "developer")
        rows = self.api.query_journal(run_id="run-1")
        self.assertEqual([r["id"] for r in rows], [e["id"]])
        self.assertEqual(rows[0]["payload"], {"task_id": "T1"})
        self.assertEqual(rows[0]["change_set_id"], "CS-1")

    def test_invalid_event_type_rejected(self):
        with self.assertRaises(ValidationError):
            self.add("task.bogus")
        self.assertEqual(self.api.query_journal(), [])

    def test_invalid_actor_type_rejected(self):
        e = JournalEntry(id="x", run_id="r", event_type="task.start", actor_type="ROBOT", actor_id="a",
                         payload={}, timestamp="2026-01-01T00:00:00+00:00")
        with self.assertRaises(ValidationError):
            self.store.append(e)

    def test_query_filters(self):
        self.add("task.start", run_id="a", change_set_id="CS-1")
        self.add("stage.enter", {"stage": "x"}, run_id="a")
        self.add("task.start", run_id="b", change_set_id="CS-2")
        self.assertEqual(len(self.api.query_journal(run_id="a")), 2)
        self.assertEqual(len(self.api.query_journal(event_type="task.start")), 2)
        self.assertEqual(len(self.api.query_journal(change_set_id="CS-2")), 1)
        self.assertEqual(len(self.api.query_journal(run_id="a", event_type="task.start")), 1)
        self.assertEqual(len(self.api.query_journal(limit=1)), 1)

    def test_query_time_range(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(3):
            self.add("task.checkpoint", {"i": i}, timestamp=(base + timedelta(hours=i)).isoformat())
        since = (base + timedelta(hours=1)).isoformat()
        until = (base + timedelta(hours=2)).isoformat()
        self.assertEqual([r["payload"]["i"] for r in self.api.query_journal(since=since)], [1, 2])
        self.assertEqual([r["payload"]["i"] for r in self.api.query_journal(until=until)], [0, 1])
        self.assertEqual([r["payload"]["i"] for r in self.api.query_journal(since=since, until=until)], [1])


class TestChain(JournalCase):
    def test_chain_verifies(self):
        for t in ("session.join", "task.start", "stage.enter"):
            self.add(t)
        self.assertEqual(self.api.verify_chain("run-1")["ok"], True)
        rows = self.api.query_journal(run_id="run-1")
        self.assertEqual(rows[1]["prev_hash"], rows[0]["entry_hash"])
        self.assertEqual(self.store.last_hash("run-1"), rows[2]["entry_hash"])
        self.assertEqual(self.store.last_hash(), rows[2]["entry_hash"])

    def test_chain_is_per_run(self):
        self.add("task.start", run_id="a")
        self.add("task.start", run_id="b")
        self.add("task.start", run_id="a")
        self.assertTrue(self.api.verify_chain("a")["ok"])
        self.assertTrue(self.api.verify_chain("b")["ok"])

    def test_detects_payload_tampering(self):
        for t in ("session.join", "task.start", "stage.enter"):
            self.add(t, {"v": 1})
        self.store.conn.execute("UPDATE journal_entries SET payload = '{\"v\":2}' WHERE event_type = 'task.start'")
        res = self.api.verify_chain("run-1")
        self.assertFalse(res["ok"])
        self.assertIn("altered", res["detail"])

    def test_detects_deletion(self):
        for t in ("session.join", "task.start", "stage.enter"):
            self.add(t)
        self.store.conn.execute("DELETE FROM journal_entries WHERE event_type = 'task.start'")
        self.assertFalse(self.api.verify_chain("run-1")["ok"])

    def test_unreadable_journal_blocks(self):
        self.add("task.start")
        self.store.conn.execute("UPDATE journal_entries SET payload = 'not json'")
        with self.assertRaises(JournalUnreadable):
            self.api.fold_state("run-1")
        self.store.conn.execute("DROP TABLE journal_entries")
        with self.assertRaises(JournalUnreadable):
            self.api.query_journal()


class TestFoldAndHeartbeat(JournalCase):
    def test_fold_state(self):
        self.add("session.join")
        self.add("task.start", {"task_id": "T1"})
        self.add("stage.enter", {"stage": "implement"})
        self.add("coord.intent_claim", {"intent_id": "I1", "target": "a.py"})
        self.add("evidence.decision", {"summary": "use sqlite"})
        s = self.api.fold_state("run-1")
        self.assertIn(DEVELOPER.actor_id, s["active_sessions"])
        self.assertEqual(s["active_sessions"][DEVELOPER.actor_id]["liveness"], "active")
        self.assertIn("T1", s["active_tasks"])
        self.assertEqual(s["current_stage"], "implement")
        self.assertEqual(len(s["stage_history"]), 1)
        self.assertIn("I1", s["open_intents"])
        self.assertEqual(s["decisions"][0]["summary"], "use sqlite")
        self.assertFalse(s["halted"])

    def test_fold_removals_and_halt(self):
        self.add("session.join")
        self.add("task.start", {"task_id": "T1"})
        self.add("task.deliver", {"task_id": "T1"})
        self.add("coord.intent_claim", {"intent_id": "I1"})
        self.add("coord.intent_release", {"intent_id": "I1"})
        self.add("stage.enter", {"stage": "s"})
        self.add("stage.exit", {"stage": "s"})
        self.add("system.halt", {"reason": "budget"}, who=CI)
        s = self.api.fold_state("run-1")
        self.assertEqual((s["active_tasks"], s["open_intents"], s["current_stage"]), ({}, {}, ""))
        self.assertEqual((s["halted"], s["halt_reason"]), (True, "budget"))
        self.add("session.leave")
        self.add("system.resume", who=CI)
        s = self.api.fold_state("run-1")
        self.assertEqual((s["active_sessions"], s["halted"]), ({}, False))

    def test_liveness_from_age(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self.add("session.heartbeat", timestamp=old)
        s = self.api.fold_state("run-1")
        self.assertEqual(s["active_sessions"][DEVELOPER.actor_id]["liveness"], "quiet")

    def test_heartbeat_creates_entry(self):
        e = self.api.heartbeat(DEVELOPER, run_id="run-1", agent_role="developer")
        self.assertEqual(e["event_type"], "session.heartbeat")
        rows = self.api.query_journal(run_id="run-1", event_type="session.heartbeat")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["actor_id"], DEVELOPER.actor_id)


class TestTools(JournalCase):
    def test_tools_registered(self):
        class Rec:
            def __init__(self):
                self.names = []

            def tool(self, name=None, description=None, **kw):
                return lambda fn: self.names.append(name) or fn

        names = self.registry.get("event_journal").register_tools(Rec(), DEVELOPER)
        self.assertEqual(sorted(names), ["append_journal", "fold_state", "heartbeat", "query_journal"])


if __name__ == "__main__":
    unittest.main()
