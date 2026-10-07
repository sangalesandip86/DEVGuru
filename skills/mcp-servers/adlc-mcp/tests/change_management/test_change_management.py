import os
import unittest

from tests._support import CI, CODE_REVIEWER, DEVELOPER, HUMAN_LEAD, SECURITY, TempEnv

from adlc_mcp.app import build_modules
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError
from adlc_mcp.kernel.identity import Identity

SHA = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"
SHA2 = "b1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"
HASH = "sha256:" + "9f" * 32


class CMTestCase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv("evidence_ledger,change_management")
        self.registry = build_modules(self.env.config)
        self.cm = self.registry.get("change_management").api
        self.ledger = self.registry.get("evidence_ledger").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def new_cs(self, repos=("repo-a",), story_refs=("ST-1",)):
        return self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                         repositories=list(repos), story_refs=list(story_refs))

    def drive_to(self, cs_id, target, tier_paths=("README.md",)):
        """Walk the lifecycle the legitimate way."""
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="SCOPED", reason="scoped")
        self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs_id, paths=list(tier_paths))
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="PLANNED", reason="planned")
        if target == "PLANNED":
            return
        self.cm.ingest_forge_event(CI, change_set_id=cs_id, event_type="plan_check_passed", payload={"run": "1"})
        if target == "PLAN_APPROVED":
            return
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="EXECUTING", reason="go")
        if target == "EXECUTING":
            return
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="VERIFYING", reason="done")


class PrivilegedStates(CMTestCase):
    def test_no_caller_sets_privileged_states_via_update_status(self):
        cs = self.new_cs()
        for who in (DEVELOPER, HUMAN_LEAD, CI):
            for state in ("PLAN_APPROVED", "INTEGRATED", "RELEASED", "ROLLED_BACK"):
                with self.assertRaises(PermissionDenied):
                    self.cm.update_status(who, change_set_id=cs["id"], status=state, reason="please")

    def test_forge_ingestion_is_system_only(self):
        cs = self.new_cs()
        for who in (DEVELOPER, HUMAN_LEAD):
            with self.assertRaises(PermissionDenied):
                self.cm.ingest_forge_event(who, change_set_id=cs["id"], event_type="pr_merged",
                                           payload={"repository": "repo-a", "commit_sha": SHA, "target_branch": "main"})

    def test_tool_surface_is_role_scoped(self):
        class Rec:
            def __init__(self):
                self.names = []

            def tool(self, name=None, description=None):
                return lambda fn: self.names.append(name) or fn

        module = self.registry.get("change_management")
        for ident, present, absent in ((DEVELOPER, [], ["ingest_forge_event", "override_risk_tier"]),
                                       (CI, ["ingest_forge_event"], ["override_risk_tier"]),
                                       (HUMAN_LEAD, ["override_risk_tier"], ["ingest_forge_event"])):
            rec = Rec()
            module.register_tools(rec, ident)
            for n in present:
                self.assertIn(n, rec.names)
            for n in absent:
                self.assertNotIn(n, rec.names)

    def test_only_human_cancels(self):
        cs = self.new_cs()
        with self.assertRaises(PermissionDenied):
            self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="CANCELLED", reason="meh")
        self.cm.update_status(HUMAN_LEAD, change_set_id=cs["id"], status="CANCELLED", reason="dropped")


class Lifecycle(CMTestCase):
    def test_invalid_transitions_rejected(self):
        cs = self.new_cs()
        with self.assertRaises(ValidationError):
            self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="EXECUTING", reason="skip ahead")

    def test_low_tier_full_path_to_released_and_rollback(self):
        cs = self.new_cs()
        self.drive_to(cs["id"], "VERIFYING")
        self.assertEqual(self.cm.get_change_set(CI, cs["id"])["status"], "VERIFYING")
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="pr_merged",
                                       payload={"repository": "repo-a", "commit_sha": SHA, "target_branch": "main"})
        self.assertEqual(r["status"], "INTEGRATED", r["note"])
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="deployment",
                                       payload={"environment": "production", "status": "success"})
        self.assertEqual(r["status"], "RELEASED")
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="rollback", payload={})
        self.assertEqual(r["status"], "ROLLED_BACK")
        self.assertTrue(all(v["ok"] for v in self.cm.verify()))
        facts = self.ledger.query_evidence(CI, change_set_id=cs["id"], classification="FACT")
        self.assertTrue(any("VERIFYING -> INTEGRATED" in f["content"] for f in facts))

    def test_rollback_only_from_released(self):
        cs = self.new_cs()
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="rollback", payload={})
        self.assertEqual(r["status"], "DRAFT")

    def test_blocked_returns_to_prior_state_and_escalation_needs_human(self):
        cs = self.new_cs()
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="SCOPED", reason="s")
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="BLOCKED", reason="dep",
                              block_kind="ESCALATION")
        with self.assertRaises(ValidationError):
            self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="PLANNED", reason="no")
        with self.assertRaises(PermissionDenied):
            self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="SCOPED", reason="unblock myself")
        self.cm.update_status(HUMAN_LEAD, change_set_id=cs["id"], status="SCOPED", reason="resolved")
        self.assertEqual(self.cm.get_change_set(CI, cs["id"])["status"], "SCOPED")

    def test_high_tier_plan_needs_human_codeowners_approval(self):
        cs = self.new_cs()
        self.drive_to(cs["id"], "PLANNED", tier_paths=("src/auth/login.py",))
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="plan_check_passed", payload={})
        self.assertEqual(r["status"], "PLANNED")
        self.assertIn("human:tech-lead", r["note"])
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="codeowners_review",
                                       payload={"approver": "alice", "approver_role": "human:tech-lead",
                                                "state": "approved"})
        self.assertEqual(r["status"], "PLAN_APPROVED")

    def test_uncomputed_tier_is_treated_as_high(self):
        cs = self.new_cs()
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="SCOPED", reason="s")
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"], status="PLANNED", reason="p")
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="plan_check_passed", payload={})
        self.assertEqual(r["status"], "PLANNED")

    def test_medium_plan_needs_code_reviewer_accept(self):
        cs = self.new_cs()
        self.drive_to(cs["id"], "PLANNED", tier_paths=("src/service/thing.py",))
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="plan_check_passed", payload={})
        self.assertEqual(r["status"], "PLANNED")
        self.cm.record_handoff(CODE_REVIEWER, change_set_id=cs["id"], to_role="developer", payload={},
                               verdict="ACCEPT", domain_name="code-quality")
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="plan_check_passed", payload={})
        self.assertEqual(r["status"], "PLAN_APPROVED")

    def test_merge_blocked_by_completion_criteria(self):
        cs = self.new_cs()
        self.cm.record_dependency(DEVELOPER, change_set_id=cs["id"], source="repo-a", target="lib-x", type="import",
                                  confidence=0.6, evidence_level="STATIC")
        self.drive_to(cs["id"], "VERIFYING")
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="pr_merged",
                                       payload={"repository": "repo-a", "commit_sha": SHA, "target_branch": "main"})
        self.assertEqual(r["status"], "BLOCKED")
        self.assertIn("UNRESOLVED", r["note"])

    def test_merge_while_not_verifying_escalates(self):
        cs = self.new_cs()
        r = self.cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="pr_merged",
                                       payload={"repository": "repo-a", "commit_sha": SHA, "target_branch": "main"})
        self.assertEqual(r["status"], "BLOCKED")

    def test_standalone_without_ledger_fails_safe(self):
        env = TempEnv("change_management")
        reg = build_modules(env.config)
        try:
            cm = reg.get("change_management").api
            cs = cm.create_change_set(DEVELOPER, title="t", requirements=["R"],
                                      repositories=["repo-a"], story_refs=["ST-1"])
            for s in ("SCOPED",):
                cm.update_status(DEVELOPER, change_set_id=cs["id"], status=s, reason="x")
            cm.compute_risk_tier(DEVELOPER, change_set_id=cs["id"], paths=["README.md"])
            cm.update_status(DEVELOPER, change_set_id=cs["id"], status="PLANNED", reason="x")
            cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="plan_check_passed", payload={})
            cm.update_status(DEVELOPER, change_set_id=cs["id"], status="EXECUTING", reason="x")
            cm.update_status(DEVELOPER, change_set_id=cs["id"], status="VERIFYING", reason="x")
            r = cm.ingest_forge_event(CI, change_set_id=cs["id"], event_type="pr_merged",
                                      payload={"repository": "repo-a", "commit_sha": SHA, "target_branch": "main"})
            self.assertEqual(r["status"], "BLOCKED")
            self.assertIn("evidence ledger not connected", r["note"])
        finally:
            reg.close()
            env.close()


class RiskTiering(CMTestCase):
    def test_tiers_escalation_and_floor(self):
        cs = self.new_cs()
        r = self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs["id"], paths=["docs/guide.md"])
        self.assertEqual(r["final_tier"], "LOW")
        r = self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs["id"], paths=["docs/guide.md"],
                                      reason_codes=["UNKNOWN_BLAST_RADIUS", "SENSITIVE_PATH"])
        self.assertEqual(r["final_tier"], "MEDIUM")                     # exactly one level
        with self.assertRaises(ValidationError):
            self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs["id"], paths=["a"], reason_codes=["I_FEEL_UNEASY"])
        r = self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs["id"], paths=["docs/guide.md"])
        self.assertEqual(r["final_tier"], "MEDIUM")                     # never lowered by recomputation
        r = self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs["id"], paths=[".github/workflows/ci.yml"])
        self.assertEqual(r["final_tier"], "CRITICAL")                   # control files

    def test_uncomputable_and_disagreement(self):
        cs = self.new_cs()
        self.assertEqual(self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs["id"], paths=[])["final_tier"], "HIGH")
        cs2 = self.new_cs()
        r = self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs2["id"], paths=["README.md"],
                                      assessed_tiers=["LOW", "HIGH"])
        self.assertEqual(r["final_tier"], "HIGH")
        r = self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs2["id"], paths=["README.md"], diff_lines=5000)
        self.assertTrue(r["decompose_required"])

    def test_human_override_logged_as_downgrade(self):
        cs = self.new_cs()
        self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs["id"], paths=["src/auth/x.py"])
        with self.assertRaises(PermissionDenied):
            self.cm.override_risk_tier(DEVELOPER, change_set_id=cs["id"], tier="LOW", reason="trust me")
        self.cm.override_risk_tier(HUMAN_LEAD, change_set_id=cs["id"], tier="MEDIUM", reason="test-only file")
        self.assertEqual(self.cm.override_stats()["downgrades"], 1)


class SnapshotsTasksHandoffs(CMTestCase):
    def test_snapshot_requires_shas_and_staleness(self):
        cs = self.new_cs(("repo-a", "repo-b"))
        with self.assertRaises(ValidationError):
            self.cm.create_snapshot(DEVELOPER, change_set_id=cs["id"], repositories={"repo-a": "latest", "repo-b": SHA})
        snap = self.cm.create_snapshot(DEVELOPER, change_set_id=cs["id"], repositories={"repo-a": SHA, "repo-b": SHA})
        r = self.cm.validate_snapshot_currency(DEVELOPER, snapshot_id=snap["id"],
                                               current_heads={"repo-a": SHA, "repo-b": SHA2},
                                               changed_paths={"repo-b": ["services/other/package-lock.json"]},
                                               task_paths={"repo-b": ["services/mine/app.py"]})
        self.assertEqual(r["verdict"], "STALE")
        self.assertEqual(r["repositories"]["repo-b"]["always_overlap_classes"], ["lockfile"])
        r = self.cm.validate_snapshot_currency(DEVELOPER, snapshot_id=snap["id"], current_heads={"repo-a": SHA})
        self.assertEqual(r["repositories"]["repo-b"]["verdict"], "STALE")   # unknown → stale
        r = self.cm.validate_snapshot_currency(DEVELOPER, snapshot_id=snap["id"],
                                               current_heads={"repo-a": SHA, "repo-b": SHA2},
                                               changed_paths={"repo-b": ["services/other/x.py"]},
                                               task_paths={"repo-b": ["services/mine/app.py"]})
        self.assertEqual(r["verdict"], "STALE_NON_OVERLAPPING")

    def test_failure_classes_and_iteration_cap(self):
        cs = self.new_cs()
        self.cm.record_task(DEVELOPER, change_set_id=cs["id"], task_id="T1", owner_role="developer")
        r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs["id"], task_id="T1", failure_class="SCOPE_VIOLATION")
        self.assertEqual((r["policy"], r["task"]["attempts"], r["task"]["status"]), ("ESCALATE", 0, "BLOCKED"))
        with self.assertRaises(PermissionDenied):
            self.cm.record_task(DEVELOPER, change_set_id=cs["id"], task_id="T1", owner_role="developer", status="PENDING")
        self.cm.record_task(HUMAN_LEAD, change_set_id=cs["id"], task_id="T1", owner_role="developer", status="PENDING")
        for _ in range(2):
            r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs["id"], task_id="T1", failure_class="LOOP")
            self.assertEqual(r["action"], "RETRY")
        r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs["id"], task_id="T1", failure_class="TOOL_TRANSIENT")
        self.assertEqual((r["action"], r["task"]["status"]), ("STOP", "BLOCKED"))

    def test_worktree_per_running_task(self):
        cs = self.new_cs()
        self.drive_to(cs["id"], "EXECUTING")
        self.cm.record_task(DEVELOPER, change_set_id=cs["id"], task_id="T1", owner_role="developer",
                            worktree="/w/t1", status="IN_PROGRESS")
        with self.assertRaises(ValidationError):
            self.cm.record_task(DEVELOPER, change_set_id=cs["id"], task_id="T2", owner_role="developer",
                                worktree="/w/t1", status="IN_PROGRESS")
        with self.assertRaises(ValidationError):
            self.cm.record_task(DEVELOPER, change_set_id=cs["id"], task_id="T3", owner_role="developer",
                                worktree="/w/t3", status="IN_PROGRESS", depends_on=["T1"])
        snap = self.cm.create_snapshot(DEVELOPER, change_set_id=cs["id"], repositories={"repo-a": SHA})
        t = self.cm.checkpoint_task(DEVELOPER, change_set_id=cs["id"], task_id="T1", commit_sha=SHA,
                                    ledger_cursor="ENTRY-1", snapshot_id=snap["id"])
        self.assertEqual(t["checkpoint"]["snapshot_id"], snap["id"])
        r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs["id"], task_id="T1", failure_class="SESSION_CRASH")
        self.assertEqual(r["resume_from"]["commit_sha"], SHA)

    def test_handoff_refs_and_security_reject(self):
        cs = self.new_cs()
        with self.assertRaises(ValidationError):
            self.cm.record_handoff(DEVELOPER, change_set_id=cs["id"], to_role="code-reviewer",
                                   payload={"inputs": [{"artifact_ref": "design.md", "content_hash": HASH}]})
        with self.assertRaises(ValidationError):
            self.cm.record_handoff(DEVELOPER, change_set_id=cs["id"], to_role="code-reviewer",
                                   payload={"claims": [{"text": "it is fast"}]})
        h = self.cm.record_handoff(DEVELOPER, change_set_id=cs["id"], to_role="code-reviewer", payload={
            "inputs": [{"artifact_ref": "repo-a@a1b2c3d:docs/ad-77.md", "content_hash": HASH}]})
        self.assertEqual(h["from_role"], "developer")
        h = self.cm.record_handoff(SECURITY, change_set_id=cs["id"], to_role="developer", payload={}, verdict="REJECT",
                                   domain_name="security")
        self.assertTrue(h["escalated"])
        self.assertEqual(self.cm.get_change_set(CI, cs["id"])["status"], "BLOCKED")

    def test_handoff_inference_needs_input_references(self):
        cs = self.new_cs()
        with self.assertRaises(ValidationError):
            self.cm.record_handoff(DEVELOPER, change_set_id=cs["id"], to_role="code-reviewer",
                                   payload={"claims": [{"classification": "INFERENCE", "text": "perf is good",
                                                         "source": "bench.py"}]})

    def test_handoff_fact_needs_source(self):
        cs = self.new_cs()
        with self.assertRaises(ValidationError):
            self.cm.record_handoff(DEVELOPER, change_set_id=cs["id"], to_role="code-reviewer",
                                   payload={"claims": [{"classification": "FACT", "text": "tests pass"}]})

    def test_max_three_rejection_cycles(self):
        cs = self.new_cs()
        for i in range(3):
            h = self.cm.record_handoff(CODE_REVIEWER, change_set_id=cs["id"], to_role="developer", payload={},
                                       verdict="REJECT")
        self.assertTrue(h["escalated"])


if __name__ == "__main__":
    unittest.main()
