"""Comprehensive verification tests proving ADLC evaluation findings are resolved.

Copy this file to skills/enforcement/tests/test_comprehensive_fixes_verification.py
then run:
    cd "C:\\copies\\git projects\\DEVGuru"
    python -m unittest skills/enforcement/tests/test_comprehensive_fixes_verification.py -v
"""
from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp-servers" / "adlc-mcp" / "src"))

from adlc_mcp.kernel import db as adlc_db
from adlc_mcp.kernel.identity import Identity, system_identity
from adlc_mcp.kernel.errors import ValidationError, PermissionDenied


def _mem_conn():
    """Create an in-memory SQLite connection matching the server's config (autocommit)."""
    return adlc_db.connect(":memory:")


def _agent(role="developer"):
    return Identity(actor_type="AGENT", actor_id=f"test-{role}", agent_role=role, tool="claude-code")


def _human():
    return Identity(actor_type="HUMAN", actor_id="test-human")


def _system():
    return system_identity("test-system")


# ============================================================
# F-02, F-07, F-08: Stage Engine fail-closed
# ============================================================
class TestStageEngineFailClosed(unittest.TestCase):
    """Prove record_transition raises on invalid transitions (not just logs)."""

    def setUp(self):
        from adlc_mcp.modules.stage_engine.api import StageEngine
        self.conn = _mem_conn()
        self.engine = StageEngine(self.conn)
        self.engine.migrate()
        self.identity = _agent("product-owner")

    def tearDown(self):
        self.conn.close()

    def test_F02_invalid_stage_name_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            self.engine.record_transition(
                self.identity, change_set_id="CS-test",
                from_stage="BANANA", to_stage="ARCHITECTURE")
        self.assertIn("denied", str(ctx.exception).lower())

    def test_F07_skip_stages_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            self.engine.record_transition(
                self.identity, change_set_id="CS-test",
                from_stage="INTAKE", to_stage="IMPLEMENT",
                outputs=["requirement_id"])
        self.assertIn("denied", str(ctx.exception).lower())

    def test_F08_backward_transition_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            self.engine.record_transition(
                _agent("code-reviewer"), change_set_id="CS-test",
                from_stage="REVIEW", to_stage="INTAKE",
                outputs=["review_verdict"])
        self.assertIn("denied", str(ctx.exception).lower())

    def test_valid_forward_transition_succeeds(self):
        result = self.engine.record_transition(
            self.identity, change_set_id="CS-test",
            from_stage="INTAKE", to_stage="ARCHITECTURE",
            outputs=["requirement_id"])
        self.assertTrue(result["allowed"])
        self.assertEqual(result["from_stage"], "INTAKE")
        self.assertEqual(result["to_stage"], "ARCHITECTURE")

    def test_violation_still_recorded(self):
        try:
            self.engine.record_transition(
                self.identity, change_set_id="CS-test",
                from_stage="INTAKE", to_stage="IMPLEMENT",
                outputs=["requirement_id"])
        except ValidationError:
            pass
        row = self.conn.execute(
            "SELECT from_stage, to_stage, gate_result FROM stage_transitions WHERE change_set_id = ?",
            ("CS-test",)).fetchone()
        self.assertIsNotNone(row, "VIOLATION row should be recorded even when raising")
        self.assertEqual(row[0], "INTAKE")
        self.assertEqual(row[1], "IMPLEMENT")
        self.assertEqual(row[2], "VIOLATION")

    def test_violation_does_not_update_current_stage(self):
        """After a denied transition, stage_current should NOT move to the invalid target."""
        try:
            self.engine.record_transition(
                self.identity, change_set_id="CS-test2",
                from_stage="INTAKE", to_stage="IMPLEMENT",
                outputs=["requirement_id"])
        except ValidationError:
            pass
        current = self.engine.get_current_stage(change_set_id="CS-test2")
        self.assertEqual(current["current_stage"], "INTAKE",
                         "denied transition must not advance stage_current")


# ============================================================
# F-13, F-14: Evidence source_type validation
# ============================================================
class TestSourceTypeValidation(unittest.TestCase):
    """Prove AGENT callers cannot claim SYSTEM/HUMAN source types."""

    def setUp(self):
        from adlc_mcp.modules.evidence_ledger.domain import validate_source_type
        self.validate = validate_source_type

    def test_F13_agent_cannot_use_system_source_type(self):
        for st in ("command_output", "tool_output", "hook_observation", "ci_result"):
            with self.assertRaises(PermissionDenied, msg=f"should block {st}"):
                self.validate(st, _agent())

    def test_F14_agent_cannot_use_human_source_type(self):
        for st in ("user_statement", "org_policy", "org_document"):
            with self.assertRaises(PermissionDenied, msg=f"should block {st}"):
                self.validate(st, _agent())

    def test_agent_allowed_source_types(self):
        for st in ("agent_analysis", "repo_file", "git_metadata", "external_doc"):
            self.validate(st, _agent())  # should not raise

    def test_system_can_use_system_source_types(self):
        for st in ("command_output", "tool_output", "hook_observation"):
            self.validate(st, _system())  # should not raise

    def test_human_can_use_human_source_types(self):
        self.validate("user_statement", _human())  # should not raise


# ============================================================
# F-49: Task status forward-only
# ============================================================
class TestTaskStatusForwardOnly(unittest.TestCase):
    """Prove DONE tasks cannot regress."""

    def setUp(self):
        from adlc_mcp.modules.change_management.api import ChangeManagement
        self.conn = _mem_conn()
        self.api = ChangeManagement(self.conn, repo_root=None)
        self.api.migrate()
        self.human = _human()
        self.dev = _agent("developer")
        # Create a change set
        cs = self.api.create_change_set(
            self.dev, title="test", requirements=["REQ-1"],
            repositories=["repo"], story_refs=["ST-1"])
        self.cs_id = cs["id"]
        # Create a task as DONE
        self.api.record_task(
            self.dev, change_set_id=self.cs_id, task_id="T-1",
            owner_role="developer", status="PENDING")
        self.api.record_task(
            self.dev, change_set_id=self.cs_id, task_id="T-1",
            owner_role="developer", status="DONE")

    def tearDown(self):
        self.conn.close()

    def test_F49_done_cannot_regress_to_pending(self):
        with self.assertRaises(ValidationError) as ctx:
            self.api.record_task(
                self.dev, change_set_id=self.cs_id, task_id="T-1",
                owner_role="developer", status="PENDING")
        self.assertIn("DONE", str(ctx.exception))

    def test_F49_done_cannot_regress_to_in_progress(self):
        with self.assertRaises(ValidationError) as ctx:
            self.api.record_task(
                self.dev, change_set_id=self.cs_id, task_id="T-1",
                owner_role="developer", status="IN_PROGRESS",
                worktree="/tmp/wt")
        self.assertIn("DONE", str(ctx.exception))


# ============================================================
# F-41: Risk tier_floor restriction
# ============================================================
class TestRiskTierRestriction(unittest.TestCase):
    """Prove AGENT callers cannot set tier_floor."""

    def setUp(self):
        from adlc_mcp.modules.change_management.api import ChangeManagement
        self.conn = _mem_conn()
        self.api = ChangeManagement(self.conn, repo_root=None)
        self.api.migrate()
        self.dev = _agent("developer")
        cs = self.api.create_change_set(
            self.dev, title="test", requirements=["REQ-1"],
            repositories=["repo"], story_refs=["ST-1"])
        self.cs_id = cs["id"]

    def tearDown(self):
        self.conn.close()

    def test_F41_agent_cannot_set_tier_floor(self):
        with self.assertRaises(PermissionDenied):
            self.api.compute_risk_tier(
                self.dev, change_set_id=self.cs_id,
                paths=["src/main.py"], tier_floor="CRITICAL")

    def test_human_can_set_tier_floor(self):
        result = self.api.compute_risk_tier(
            _human(), change_set_id=self.cs_id,
            paths=["src/main.py"], tier_floor="HIGH")
        self.assertIn("final_tier", result)

    def test_system_can_set_tier_floor(self):
        result = self.api.compute_risk_tier(
            _system(), change_set_id=self.cs_id,
            paths=["src/main.py"], tier_floor="HIGH")
        self.assertIn("final_tier", result)


# ============================================================
# F-09: Self-handoff rejection
# ============================================================
class TestSelfHandoffRejection(unittest.TestCase):
    """Prove from_role == to_role is rejected."""

    def setUp(self):
        from adlc_mcp.modules.change_management.api import ChangeManagement
        self.conn = _mem_conn()
        self.api = ChangeManagement(self.conn, repo_root=None)
        self.api.migrate()
        self.dev = _agent("developer")
        cs = self.api.create_change_set(
            self.dev, title="test", requirements=["REQ-1"],
            repositories=["repo"], story_refs=["ST-1"])
        self.cs_id = cs["id"]

    def tearDown(self):
        self.conn.close()

    def test_F09_self_handoff_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.api.record_handoff(
                self.dev, change_set_id=self.cs_id,
                to_role="developer",
                payload={"inputs": [], "claims": []})
        self.assertIn("self-handoff", str(ctx.exception).lower())

    def test_cross_role_handoff_succeeds(self):
        result = self.api.record_handoff(
            self.dev, change_set_id=self.cs_id,
            to_role="code-reviewer",
            payload={"inputs": [], "claims": []})
        self.assertEqual(result["to_role"], "code-reviewer")


# ============================================================
# F-39: Self-dependency rejection
# ============================================================
class TestSelfDependencyRejection(unittest.TestCase):
    """Prove self-referential dependencies are rejected."""

    def setUp(self):
        from adlc_mcp.modules.change_management.api import ChangeManagement
        self.conn = _mem_conn()
        self.api = ChangeManagement(self.conn, repo_root=None)
        self.api.migrate()
        self.dev = _agent("developer")
        cs = self.api.create_change_set(
            self.dev, title="test", requirements=["REQ-1"],
            repositories=["repo"], story_refs=["ST-1"])
        self.cs_id = cs["id"]

    def tearDown(self):
        self.conn.close()

    def test_F39_self_dependency_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.api.record_dependency(
                self.dev, change_set_id=self.cs_id,
                source="auth-service", target="auth-service",
                type="runtime", confidence=1.0,
                evidence_level="DECLARED")
        self.assertIn("self-dependency", str(ctx.exception).lower())

    def test_valid_dependency_succeeds(self):
        result = self.api.record_dependency(
            self.dev, change_set_id=self.cs_id,
            source="auth-service", target="user-service",
            type="runtime", confidence=0.9,
            evidence_level="DECLARED")
        self.assertEqual(result["source"], "auth-service")
        self.assertEqual(result["target"], "user-service")


# ============================================================
# F-46: PLANNED requires story_refs
# ============================================================
class TestPlannedRequiresStories(unittest.TestCase):
    """Prove SCOPED→PLANNED without story_refs is rejected."""

    def setUp(self):
        from adlc_mcp.modules.change_management.api import ChangeManagement
        self.conn = _mem_conn()
        self.api = ChangeManagement(self.conn, repo_root=None)
        self.api.migrate()
        self.dev = _agent("developer")

    def tearDown(self):
        self.conn.close()

    def test_F46_planned_without_stories_rejected(self):
        cs = self.api.create_change_set(
            self.dev, title="test", requirements=["REQ-1"],
            repositories=["repo"], story_refs=[])
        cs_id = cs["id"]
        self.api.update_status(
            self.dev, change_set_id=cs_id, status="SCOPED", reason="scope defined")
        with self.assertRaises(ValidationError) as ctx:
            self.api.update_status(
                self.dev, change_set_id=cs_id, status="PLANNED", reason="plan ready")
        self.assertIn("story_refs", str(ctx.exception))

    def test_planned_with_stories_succeeds(self):
        cs = self.api.create_change_set(
            self.dev, title="test2", requirements=["REQ-1"],
            repositories=["repo"], story_refs=["ST-1"])
        cs_id = cs["id"]
        self.api.update_status(
            self.dev, change_set_id=cs_id, status="SCOPED", reason="scope defined")
        result = self.api.update_status(
            self.dev, change_set_id=cs_id, status="PLANNED", reason="plan ready")
        self.assertEqual(result["status"], "PLANNED")


# ============================================================
# F-35: Claim task existence check
# ============================================================
class TestClaimTaskValidation(unittest.TestCase):
    """Prove nonexistent tasks cannot be claimed."""

    def setUp(self):
        from adlc_mcp.modules.concurrency.api import ConcurrencyPrimitives

        class FakeRegistry:
            def __init__(self, tasks):
                self._tasks = set(tasks)
            def task_exists(self, task_id):
                return task_id in self._tasks

        self.conn = _mem_conn()
        self.api = ConcurrencyPrimitives(self.conn, task_registry=FakeRegistry({"TASK-1"}))
        self.api.migrate()
        self.dev = _agent("developer")

    def tearDown(self):
        self.conn.close()

    def test_F35_phantom_task_claim_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.api.claim_task(self.dev, task_id="NONEXISTENT-999")
        self.assertIn("does not exist", str(ctx.exception))

    def test_existing_task_claim_succeeds(self):
        result = self.api.claim_task(self.dev, task_id="TASK-1")
        self.assertTrue(result["claimed"])


# ============================================================
# F-32, F-50: Owner change requires handoff
# ============================================================
class TestOwnerChangeRequiresHandoff(unittest.TestCase):
    """Prove owner_role changes need a prior handoff record."""

    def setUp(self):
        from adlc_mcp.modules.change_management.api import ChangeManagement
        self.conn = _mem_conn()
        self.api = ChangeManagement(self.conn, repo_root=None)
        self.api.migrate()
        self.dev = _agent("developer")
        cs = self.api.create_change_set(
            self.dev, title="test", requirements=["REQ-1"],
            repositories=["repo"], story_refs=["ST-1"])
        self.cs_id = cs["id"]
        self.api.record_task(
            self.dev, change_set_id=self.cs_id, task_id="T-1",
            owner_role="developer", status="PENDING")

    def tearDown(self):
        self.conn.close()

    def test_F32_F50_owner_change_without_handoff_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.api.record_task(
                _agent("code-reviewer"), change_set_id=self.cs_id,
                task_id="T-1", owner_role="code-reviewer", status="PENDING")
        self.assertIn("handoff", str(ctx.exception).lower())

    def test_owner_change_with_handoff_succeeds(self):
        self.api.record_handoff(
            self.dev, change_set_id=self.cs_id,
            to_role="code-reviewer",
            payload={"inputs": [], "claims": []})
        result = self.api.record_task(
            _agent("code-reviewer"), change_set_id=self.cs_id,
            task_id="T-1", owner_role="code-reviewer", status="PENDING")
        self.assertEqual(result["owner_role"], "code-reviewer")


# ============================================================
# Persona checklists validation
# ============================================================
class TestRoleYAMLChecklists(unittest.TestCase):
    """Prove all role YAMLs have the required checklist items."""

    ROLES_DIR = Path(__file__).resolve().parents[2] / "roles"

    def _load(self, name):
        path = self.ROLES_DIR / name / "role.yaml"
        return json.loads(path.read_text(encoding="utf-8"))

    def _checklist_text(self, name):
        data = self._load(name)
        items = data.get("checklist", [])
        return " ".join(items).lower()

    def test_developer_has_checklist(self):
        self.assertIn("checklist", self._load("developer"))

    def test_developer_checklist_has_assertEqual_guidance(self):
        self.assertIn("assertequal", self._checklist_text("developer"))

    def test_developer_checklist_has_test_design_reference(self):
        self.assertIn("qa-derive", self._checklist_text("developer"))

    def test_developer_checklist_has_review_fix_tests(self):
        self.assertIn("code-review fix", self._checklist_text("developer"))

    def test_code_reviewer_has_checklist(self):
        self.assertIn("checklist", self._load("code-reviewer"))

    def test_code_reviewer_checklist_has_run_code(self):
        self.assertIn("run the code", self._checklist_text("code-reviewer"))

    def test_code_reviewer_checklist_has_stderr(self):
        self.assertIn("stderr", self._checklist_text("code-reviewer"))

    def test_security_reviewer_has_checklist(self):
        self.assertIn("checklist", self._load("security-reviewer"))

    def test_security_reviewer_checklist_has_crypto_review(self):
        text = self._checklist_text("security-reviewer")
        self.assertIn("xor", text)

    def test_security_reviewer_checklist_has_sql_paths(self):
        text = self._checklist_text("security-reviewer")
        self.assertIn("order by", text)

    def test_security_reviewer_checklist_has_pbkdf2(self):
        text = self._checklist_text("security-reviewer")
        self.assertIn("pbkdf2", text)

    def test_qa_derive_has_checklist(self):
        self.assertIn("checklist", self._load("qa-derive"))

    def test_qa_derive_checklist_has_mandatory_optional(self):
        text = self._checklist_text("qa-derive")
        self.assertIn("mandatory", text)

    def test_qa_derive_checklist_has_persistence(self):
        text = self._checklist_text("qa-derive")
        self.assertIn("persistence", text)

    def test_test_engineer_has_checklist(self):
        self.assertIn("checklist", self._load("test-engineer"))

    def test_test_engineer_checklist_has_security_constants(self):
        text = self._checklist_text("test-engineer")
        self.assertIn("pbkdf2", text)

    def test_product_owner_has_checklist(self):
        self.assertIn("checklist", self._load("product-owner"))

    def test_product_owner_checklist_has_error_routing(self):
        text = self._checklist_text("product-owner")
        self.assertIn("stderr", text)


# ============================================================
# Meta: verify all P0 findings are covered
# ============================================================
class TestAllP0FindingsAddressed(unittest.TestCase):
    """Verify this test file covers every P0 finding."""

    def _all_test_names(self):
        import inspect
        names = []
        for name, obj in inspect.getmembers(sys.modules[__name__]):
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
                for method in dir(obj):
                    if method.startswith("test_"):
                        names.append(method)
        return " ".join(names)

    def test_all_critical_findings_have_tests(self):
        names = self._all_test_names()
        for finding_id in ["F02", "F07", "F08", "F09", "F13", "F14",
                           "F35", "F39", "F41", "F46", "F49", "F32"]:
            self.assertIn(finding_id, names,
                          f"Finding {finding_id} has no corresponding test")


if __name__ == "__main__":
    unittest.main()
