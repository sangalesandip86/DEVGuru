import unittest

from tests._support import CI, DEVELOPER, HUMAN_LEAD, TempEnv

from adlc_mcp.app import build_modules
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError
from adlc_mcp.modules.work_planning.api import WorkPlanning
from adlc_mcp.kernel import db

SHA = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"


def story(ac_then="the payment is refunded"):
    return {
        "id": "ST-101", "title": "Refund a payment", "type": "FEATURE_STORY", "epic": "EPIC-1", "milestone": "MS-1",
        "size": "S", "source_refs": [{"ref": "REQ-7", "trust_level": "ORGANIZATIONAL"}],
        "acceptance_criteria": [
            {"id": "ST-101/AC-1", "given": "a settled payment", "when": "the user requests a refund",
             "then": ac_then, "kind": "functional", "verification": "automated"},
            {"id": "ST-101/AC-2", "given": "an unsettled payment", "when": "a refund is requested",
             "then": "the request is rejected", "kind": "negative", "verification": "automated"},
        ],
    }


PLAN = [
    {"id": "REQ-7", "path": "plans/requirements/REQ-7.yaml", "data": {"title": "Refunds"}},
    {"id": "EPIC-1", "path": "plans/epics/EPIC-1.yaml", "data": {"title": "Payments", "requirements": ["REQ-7"]}},
    {"id": "MS-1", "path": "plans/milestones/MS-1.yaml", "data": {"title": "Q4"}},
]


class PassingEvaluator:
    def evaluate(self, gate, story, context):
        return {"passed": True, "missing": []}


class WPTestCase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv("evidence_ledger,change_management,work_planning")
        self.registry = build_modules(self.env.config)
        self.wp = self.registry.get("work_planning").api
        self.cm = self.registry.get("change_management").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def ingest(self, st=None):
        return self.wp.ingest_plan_commit(CI, repository="plans", commit_sha=SHA,
                                          items=[*PLAN, {"id": "ST-101", "path": "plans/stories/ST-101.yaml",
                                                         "data": st or story()}])

    def status(self):
        return self.wp.get_work_item(DEVELOPER, "ST-101")["status"]

    def gate(self, event_type, passed=True):
        h = self.wp.get_work_item(DEVELOPER, "ST-101")["ac_hash"]
        return self.wp.ingest_work_event(CI, story_id="ST-101", event_type=event_type,
                                         payload={"passed": passed, "ac_hash": h})


class NoAgentSetsStatus(WPTestCase):
    def test_ingestion_is_system_only(self):
        for who in (DEVELOPER, HUMAN_LEAD):
            with self.assertRaises(PermissionDenied):
                self.wp.ingest_plan_commit(who, repository="plans", commit_sha=SHA, items=PLAN)
        self.ingest()
        for who in (DEVELOPER, HUMAN_LEAD):
            for et, payload in (("readiness_gate", {"passed": True, "ac_hash": "x"}),
                                ("completion_gate", {"passed": True, "ac_hash": "x"}),
                                ("po_acceptance", {"approver": "p", "approver_role": "human:product-owner"})):
                with self.assertRaises(PermissionDenied):
                    self.wp.ingest_work_event(who, story_id="ST-101", event_type=et, payload=payload)

    def test_plan_files_cannot_carry_status(self):
        for field in ("status", "ready", "done", "accepted"):
            with self.assertRaises(ValidationError):
                self.ingest({**story(), field: "READY"})

    def test_no_status_setting_tool_exists(self):
        class Rec:
            def __init__(self):
                self.names = []

            def tool(self, name=None, description=None):
                return lambda fn: self.names.append(name) or fn

        for ident in (DEVELOPER, HUMAN_LEAD, CI):
            rec = Rec()
            self.registry.get("work_planning").register_tools(rec, ident)
            self.assertFalse([n for n in rec.names if any(w in n for w in ("set_", "status", "accept", "ready"))])
            self.assertEqual("ingest_plan_commit" in rec.names, ident is CI)

    def test_po_acceptance_must_be_product_owner(self):
        self.ingest()
        with self.assertRaises(ValidationError):
            self.wp.ingest_work_event(CI, story_id="ST-101", event_type="po_acceptance",
                                      payload={"approver": "bob", "approver_role": "human:tech-lead"})


class DerivedStatus(WPTestCase):
    def test_full_lifecycle(self):
        self.ingest({**story(), "acceptance_criteria": []})
        self.assertEqual(self.status(), "DRAFT")
        self.ingest()
        self.assertEqual(self.status(), "REFINING")
        self.gate("readiness_gate")
        self.assertEqual(self.status(), "READY")
        cs = self.cm.create_change_set(DEVELOPER, title="refunds", requirements=["REQ-7"], repositories=["pay"],
                                       story_refs=["ST-101"])
        self.wp.link_change_set(DEVELOPER, story_id="ST-101", change_set_id=cs["id"],
                                implements_declaration="Adds refunds.\nImplements: ST-101")
        self.assertEqual(self.status(), "IN_PROGRESS")
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="BLOCKED", reason="x", block_kind="GATE_FAILED")
        self.assertEqual(self.status(), "BLOCKED")
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="DRAFT", reason="unblocked")
        self.assertEqual(self.status(), "IN_PROGRESS")
        self.gate("completion_gate")
        self.assertEqual(self.status(), "DONE")
        self.wp.ingest_work_event(CI, story_id="ST-101", event_type="po_acceptance",
                                  payload={"approver": "pat", "approver_role": "human:product-owner"})
        self.assertEqual(self.status(), "ACCEPTED")
        self.assertTrue(all(r["ok"] for r in self.wp.verify()))

    def test_ac_freeze_violation_returns_to_refining(self):
        self.ingest()
        self.gate("readiness_gate")
        self.assertEqual(self.status(), "READY")
        result = self.ingest(story(ac_then="the payment is partially refunded"))
        self.assertEqual(self.status(), "REFINING")
        self.assertTrue(any("AC_FREEZE_VIOLATION" in " ".join(c["flags"]) for c in result["status_changes"]))

    def test_failed_gate_does_not_make_ready(self):
        self.ingest()
        self.gate("readiness_gate", passed=False)
        self.assertEqual(self.status(), "REFINING")


class Tools(WPTestCase):
    def test_link_validated_against_implements(self):
        self.ingest()
        with self.assertRaises(ValidationError):
            self.wp.link_change_set(DEVELOPER, story_id="ST-101", change_set_id="CS-1",
                                    implements_declaration="Implements: ST-999")
        self.wp.link_change_set(DEVELOPER, story_id="ST-101", change_set_id="CS-1",
                                implements_declaration="Implements: ST-100, ST-101")

    def test_work_graph(self):
        self.ingest()
        g = self.wp.query_work_graph(DEVELOPER, root_id="REQ-7", depth=3)
        ids = {n["id"] for n in g["nodes"]}
        self.assertTrue({"REQ-7", "EPIC-1", "ST-101", "MS-1"} <= ids)
        g = self.wp.query_work_graph(DEVELOPER, root_id="ST-101", relations=["time"], depth=1)
        self.assertEqual({n["id"] for n in g["nodes"]}, {"ST-101", "MS-1"})

    def test_evaluate_is_dry_run_and_fails_safe_without_evaluator(self):
        self.ingest()
        r = self.wp.evaluate_readiness(DEVELOPER, story_id="ST-101")
        self.assertFalse(r["passed"])
        self.assertTrue(any("no readiness policy evaluator" in m for m in r["missing"]))
        self.assertEqual(self.status(), "REFINING")                  # unchanged
        wp = WorkPlanning(self.registry.get("work_planning")._conn, evaluator=PassingEvaluator())
        self.assertTrue(wp.evaluate_readiness(DEVELOPER, story_id="ST-101")["passed"])
        self.assertEqual(self.status(), "REFINING")                  # still unchanged
        bad = {**story(), "size": "L", "acceptance_criteria": [story()["acceptance_criteria"][0]]}
        self.ingest(bad)
        missing = wp.evaluate_readiness(DEVELOPER, story_id="ST-101")["missing"]
        self.assertTrue(any("negative" in m for m in missing))
        self.assertTrue(any("size" in m for m in missing))
        done = wp.evaluate_done(DEVELOPER, story_id="ST-101")
        self.assertFalse(done["passed"])


if __name__ == "__main__":
    unittest.main()
