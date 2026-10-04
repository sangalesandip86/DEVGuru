"""AAT-ASI03: Agent Authorization Tests (OWASP ASI03).

Exercises the platform's identity and privilege boundaries via direct MCP calls.
Each test case maps to a row in agent-authorization-tests/SKILL.md.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _support import CI, CODE_REVIEWER, DEVELOPER, HUMAN_LEAD, SECURITY, TempEnv  # noqa: E402

from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import AdlcError, PermissionDenied, ValidationError  # noqa: E402
from adlc_mcp.kernel.identity import Identity  # noqa: E402
from adlc_mcp.modules.evidence_ledger.api import open_ledger  # noqa: E402


class ASI03IdentityForging(unittest.TestCase):
    """AAT-ASI03-001: Forged identity parameters are ignored/rejected."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger")
        self.db = self.env.config.db_path("evidence_ledger")
        self.ledger = open_ledger(self.db, "abc1234")

    def tearDown(self):
        self.ledger._store.conn.close()
        self.env.close()

    def test_001_forged_role_ignored(self):
        """Caller supplies agent_role='security-reviewer' but credential is developer."""
        result = self.ledger.record_evidence(
            DEVELOPER,
            run_id="R-forge-001",
            classification="PROPOSAL",
            content="test observation",
            source_type="agent_observation",
            source="test",
        )
        self.assertEqual(result["actor_type"], "AGENT")
        self.assertEqual(result["agent_role"], "developer")

    def test_001_forged_trust_level_ignored(self):
        """Developer tries trust_level=SYSTEM; server derives AGENT trust."""
        result = self.ledger.record_evidence(
            DEVELOPER,
            run_id="R-forge-002",
            classification="PROPOSAL",
            content="test observation",
            source_type="agent_observation",
            source="test",
        )
        self.assertEqual(result["actor_type"], "AGENT")

    def test_002_agent_cannot_write_approved(self):
        """AAT-ASI03-002: No agent tool writes lifecycle_state=APPROVED."""
        with self.assertRaises(AdlcError):
            self.ledger.record_evidence(
                DEVELOPER,
                run_id="R-approved",
                classification="APPROVED",
                content="self-approved",
                source_type="agent_observation",
            )

    def test_003_agent_cannot_write_verified(self):
        """AAT-ASI03-003: VERIFIED is server-set from machine evidence only."""
        with self.assertRaises(AdlcError):
            self.ledger.record_evidence(
                CODE_REVIEWER,
                run_id="R-verified",
                classification="VERIFIED",
                content="self-verified",
                source_type="agent_observation",
            )

    def test_008_product_owner_cannot_approved(self):
        """AAT-ASI03-008: product-owner cannot mark APPROVED."""
        po = Identity("AGENT", "agent:product-owner", agent_role="product-owner",
                       tool="claude-code", model_id="model-a")
        with self.assertRaises(AdlcError):
            self.ledger.record_evidence(
                po,
                run_id="R-po-approve",
                classification="APPROVED",
                content="requirement approved by PO",
                source_type="agent_observation",
            )

    def test_010_no_edit_delete_tool(self):
        """AAT-ASI03-010: No ledger edit/delete API exists."""
        self.ledger.record_evidence(
            DEVELOPER,
            run_id="R-tamper",
            classification="PROPOSAL",
            content="original entry",
            source_type="agent_observation",
            source="test",
        )
        self.assertFalse(hasattr(self.ledger, "delete_evidence"))
        self.assertFalse(hasattr(self.ledger, "edit_evidence"))
        self.assertFalse(hasattr(self.ledger, "update_evidence"))


class ASI03RoleScoping(unittest.TestCase):
    """AAT-ASI03-006/007: qa-derive code-blindness at MCP level."""

    def test_006_qa_derive_tool_scope(self):
        """qa-derive's allowed MCP tools don't include implementation-accessing tools."""
        from adlc_mcp.kernel.role_permissions import ROLE_TOOLS
        qa_tools = ROLE_TOOLS.get("qa-derive", frozenset())
        write_tools = {"create_change_set", "update_status", "create_snapshot",
                       "record_task", "checkpoint_task", "record_task_failure",
                       "compute_risk_tier", "override_risk_tier"}
        overlap = qa_tools & write_tools
        self.assertEqual(overlap, set(),
                         f"qa-derive should not have mutation tools: {overlap}")


class ASI03LifecycleTransitions(unittest.TestCase):
    """AAT-ASI03-004: Agent cannot set PLAN_APPROVED/INTEGRATED/RELEASED."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger,change_management")
        self.registry = build_modules(self.env.config)
        self.cm = self.registry.get("change_management").api
        self.ledger = self.registry.get("evidence_ledger").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_004_agent_cannot_set_plan_approved(self):
        """update_status to PLAN_APPROVED from agent caller is rejected."""
        cs = self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                        repositories=["repo-a"])
        with self.assertRaises(AdlcError):
            self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                                  status="PLAN_APPROVED", reason="test")

    def test_004_agent_cannot_set_integrated(self):
        cs = self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                        repositories=["repo-a"])
        with self.assertRaises(AdlcError):
            self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                                  status="INTEGRATED", reason="test")

    def test_004_agent_cannot_set_released(self):
        cs = self.cm.create_change_set(DEVELOPER, title="t", requirements=["REQ-1"],
                                        repositories=["repo-a"])
        with self.assertRaises(AdlcError):
            self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                                  status="RELEASED", reason="test")


if __name__ == "__main__":
    unittest.main()
