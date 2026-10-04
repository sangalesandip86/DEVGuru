"""AAT-ASI06: Excessive Agency Tests (OWASP ASI06).

Exercises the platform's iteration caps, role boundaries, and escalation
controls. An agent must never exceed its declared scope or bypass human
escalation requirements.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _support import CI, CODE_REVIEWER, DEVELOPER, HUMAN_LEAD, SECURITY, TempEnv  # noqa: E402

from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError  # noqa: E402
from adlc_mcp.kernel.identity import Identity  # noqa: E402
from adlc_mcp.modules.change_management.domain import FAILURE_POLICY, ITERATION_CAP  # noqa: E402


class ASI06IterationCap(unittest.TestCase):
    """3-attempt iteration cap is enforced for all retryable failure classes."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger,change_management")
        self.registry = build_modules(self.env.config)
        self.cm = self.registry.get("change_management").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def _new_cs_with_task(self):
        cs = self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                        repositories=["repo-a"])
        self.cm.record_task(DEVELOPER, change_set_id=cs["id"], task_id="T1", owner_role="developer")
        return cs["id"]

    def test_001_loop_failures_hit_cap(self):
        """LOOP is retryable; after ITERATION_CAP attempts, the task is BLOCKED."""
        cs_id = self._new_cs_with_task()
        for i in range(ITERATION_CAP - 1):
            r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs_id, task_id="T1",
                                             failure_class="LOOP")
            self.assertEqual(r["action"], "RETRY")
        r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs_id, task_id="T1",
                                         failure_class="LOOP")
        self.assertEqual(r["action"], "STOP")
        self.assertEqual(r["task"]["status"], "BLOCKED")

    def test_002_invalid_output_hits_cap(self):
        """INVALID_OUTPUT also counts toward the 3-attempt cap."""
        cs_id = self._new_cs_with_task()
        for i in range(ITERATION_CAP - 1):
            r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs_id, task_id="T1",
                                             failure_class="INVALID_OUTPUT")
            self.assertEqual(r["action"], "RETRY")
        r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs_id, task_id="T1",
                                         failure_class="INVALID_OUTPUT")
        self.assertEqual(r["action"], "STOP")

    def test_003_tool_transient_hits_cap(self):
        """TOOL_TRANSIENT is retryable and counts toward cap."""
        cs_id = self._new_cs_with_task()
        for _ in range(ITERATION_CAP):
            self.cm.record_task_failure(DEVELOPER, change_set_id=cs_id, task_id="T1",
                                        failure_class="TOOL_TRANSIENT")
        task = self.cm._store.get_task(cs_id, "T1")
        self.assertEqual(task["status"], "BLOCKED")

    def test_004_non_retryable_blocks_immediately(self):
        """SCOPE_VIOLATION and PERMISSION_DENIAL block immediately, don't count toward cap."""
        for fc in ("SCOPE_VIOLATION", "PERMISSION_DENIAL", "SECURITY_REJECTION"):
            cs_id = self._new_cs_with_task()
            r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs_id, task_id="T1",
                                             failure_class=fc)
            self.assertEqual(r["policy"], "ESCALATE", f"{fc} should escalate")
            self.assertEqual(r["task"]["status"], "BLOCKED")
            self.assertEqual(r["task"]["attempts"], 0, f"{fc} should not count toward cap")

    def test_005_tool_persistent_stops_without_escalation(self):
        """TOOL_PERSISTENT stops without counting toward cap."""
        cs_id = self._new_cs_with_task()
        r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs_id, task_id="T1",
                                         failure_class="TOOL_PERSISTENT")
        self.assertEqual(r["policy"], "STOP")
        self.assertEqual(r["task"]["status"], "BLOCKED")

    def test_006_context_exceeded_replans(self):
        """CONTEXT_EXCEEDED triggers REPLAN, not RETRY."""
        cs_id = self._new_cs_with_task()
        r = self.cm.record_task_failure(DEVELOPER, change_set_id=cs_id, task_id="T1",
                                         failure_class="CONTEXT_EXCEEDED")
        self.assertEqual(r["policy"], "REPLAN")

    def test_007_all_failure_classes_have_policy(self):
        """Every failure class in FAILURE_POLICY is a known class."""
        self.assertTrue(len(FAILURE_POLICY) >= 8)
        for fc, (policy, counts) in FAILURE_POLICY.items():
            self.assertIn(policy, ("RETRY", "STOP", "ESCALATE", "REPLAN", "RESUME"))
            self.assertIsInstance(counts, bool)


class ASI06RoleBoundaryEscalation(unittest.TestCase):
    """Agents can't escalate beyond their role's authority."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger,change_management")
        self.registry = build_modules(self.env.config)
        self.cm = self.registry.get("change_management").api
        self.ledger = self.registry.get("evidence_ledger").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_008_agent_cannot_unblock_escalated_task(self):
        """After ESCALATE, only a human can unblock the task."""
        cs = self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                        repositories=["repo-a"])
        self.cm.record_task(DEVELOPER, change_set_id=cs["id"], task_id="T1", owner_role="developer")
        self.cm.record_task_failure(DEVELOPER, change_set_id=cs["id"], task_id="T1",
                                    failure_class="SCOPE_VIOLATION")
        with self.assertRaises(PermissionDenied):
            self.cm.record_task(DEVELOPER, change_set_id=cs["id"], task_id="T1",
                                owner_role="developer", status="PENDING")
        # Human CAN unblock
        self.cm.record_task(HUMAN_LEAD, change_set_id=cs["id"], task_id="T1",
                            owner_role="developer", status="PENDING")

    def test_009_cross_role_evidence_attribution(self):
        """Evidence recorded by developer is attributed to developer, not another role."""
        result = self.ledger.record_evidence(
            DEVELOPER,
            run_id="R-attr-001",
            classification="PROPOSAL",
            content="my proposal",
            source_type="agent_analysis",
            source="test",
        )
        self.assertEqual(result["agent_role"], "developer")
        self.assertEqual(result["actor_type"], "AGENT")

        result2 = self.ledger.record_evidence(
            CODE_REVIEWER,
            run_id="R-attr-002",
            classification="PROPOSAL",
            content="reviewer's proposal",
            source_type="agent_analysis",
            source="test",
        )
        self.assertEqual(result2["agent_role"], "code-reviewer")

    def test_010_developer_cannot_write_approved_lifecycle(self):
        """Developer cannot set lifecycle_state to APPROVED on a DECISION."""
        with self.assertRaises(PermissionDenied):
            self.ledger.record_evidence(
                DEVELOPER,
                run_id="R-lifecycle-001",
                classification="DECISION",
                content="I approve this",
                source_type="agent_analysis",
                source="test",
                lifecycle_state="APPROVED",
            )

    def test_011_developer_can_write_reviewed_lifecycle(self):
        """Developer CAN set lifecycle_state to REVIEWED (agent judgment)."""
        result = self.ledger.record_evidence(
            DEVELOPER,
            run_id="R-lifecycle-002",
            classification="DECISION",
            content="I reviewed this",
            source_type="agent_analysis",
            source="test",
            lifecycle_state="REVIEWED",
        )
        self.assertEqual(result["lifecycle_state"], "REVIEWED")

    def test_012_invalid_failure_class_rejected(self):
        """An invented failure class is rejected."""
        cs = self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                        repositories=["repo-a"])
        self.cm.record_task(DEVELOPER, change_set_id=cs["id"], task_id="T1", owner_role="developer")
        with self.assertRaises(ValidationError):
            self.cm.record_task_failure(DEVELOPER, change_set_id=cs["id"], task_id="T1",
                                        failure_class="MAGIC_BYPASS")


if __name__ == "__main__":
    unittest.main()
