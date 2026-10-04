"""AAT-ASI02: Tool Misuse Tests (OWASP ASI02).

Exercises per-role tool scoping at the MCP level.
Test cases map to rows in tool-misuse-tests/SKILL.md.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _support import CODE_REVIEWER, DEVELOPER, SECURITY, TempEnv  # noqa: E402

from adlc_mcp.kernel.identity import Identity  # noqa: E402


class ASI02ManagedSettings(unittest.TestCase):
    """AAT-ASI02-006: Control file write via any route is denied by managed settings."""

    def test_006_control_file_deny_rules_present(self):
        """Managed settings template contains Edit/Write denials for control-file globs."""
        template_path = (Path(__file__).resolve().parents[4]
                         / "enforcement" / "managed-settings" / "templates"
                         / "claude-code-managed-settings.json")
        template = json.loads(template_path.read_text(encoding="utf-8"))
        deny = template["permissions"]["deny"]
        control_globs = [r for r in deny if "CLAUDE.md" in r or "AGENTS.md" in r
                         or "CODEOWNERS" in r or ".claude/" in r]
        self.assertTrue(len(control_globs) >= 2,
                        "Expected deny rules for CLAUDE.md, AGENTS.md, .claude/")


class ASI02RoleToolScoping(unittest.TestCase):
    """AAT-ASI02-007: Roles cannot call MCP tools outside their scope."""

    def test_007_code_reviewer_cannot_create_change_set(self):
        """code-reviewer should not have create_change_set in allowed tools."""
        from adlc_mcp.kernel.role_permissions import ROLE_TOOLS
        reviewer_tools = ROLE_TOOLS.get("code-reviewer", frozenset())
        self.assertNotIn("create_change_set", reviewer_tools)
        self.assertNotIn("update_status", reviewer_tools)

    def test_007_security_reviewer_cannot_update_status(self):
        from adlc_mcp.kernel.role_permissions import ROLE_TOOLS
        sec_tools = ROLE_TOOLS.get("security-reviewer", frozenset())
        self.assertNotIn("update_status", sec_tools)
        self.assertNotIn("create_change_set", sec_tools)

    def test_007_qa_derive_no_mutation_tools(self):
        from adlc_mcp.kernel.role_permissions import ROLE_TOOLS
        qa = ROLE_TOOLS.get("qa-derive", frozenset())
        mutation = {"create_change_set", "update_status", "create_snapshot",
                    "override_risk_tier", "record_task", "checkpoint_task"}
        self.assertEqual(qa & mutation, set())

    def test_007_developer_has_expected_tools(self):
        from adlc_mcp.kernel.role_permissions import ROLE_TOOLS
        dev = ROLE_TOOLS.get("developer", frozenset())
        expected = {"record_evidence", "query_evidence", "create_change_set",
                    "update_status", "record_task"}
        self.assertTrue(expected.issubset(dev),
                        f"developer missing: {expected - dev}")

    def test_all_roles_have_query_evidence(self):
        """Every role can at least query evidence."""
        from adlc_mcp.kernel.role_permissions import ROLE_TOOLS
        for role, tools in ROLE_TOOLS.items():
            self.assertIn("query_evidence", tools,
                          f"{role} missing query_evidence")

    def test_no_role_has_ingest_forge_event(self):
        """ingest_forge_event is SYSTEM-only, no agent role should have it."""
        from adlc_mcp.kernel.role_permissions import ROLE_TOOLS
        for role, tools in ROLE_TOOLS.items():
            self.assertNotIn("ingest_forge_event", tools,
                             f"{role} must not have ingest_forge_event")


class ASI02SubagentDeny(unittest.TestCase):
    """AAT-ASI02-004: Read-only roles have file-tool denials in managed settings."""

    def test_004_code_reviewer_deny_in_managed_settings(self):
        """code-reviewer subagentPermissions should deny Edit and Write."""
        template_path = (Path(__file__).resolve().parents[4]
                         / "enforcement" / "managed-settings" / "templates"
                         / "claude-code-managed-settings.json")
        template = json.loads(template_path.read_text(encoding="utf-8"))
        sa = template.get("subagentPermissions", {})
        reviewer = sa.get("code-reviewer", {}).get("permissions", {}).get("deny", [])
        self.assertTrue(any("Edit" in r for r in reviewer),
                        "code-reviewer should have Edit denials")

    def test_qa_derive_bash_denied(self):
        """qa-derive must have Bash denied to prevent shell-based code reading."""
        template_path = (Path(__file__).resolve().parents[4]
                         / "enforcement" / "managed-settings" / "templates"
                         / "claude-code-managed-settings.json")
        template = json.loads(template_path.read_text(encoding="utf-8"))
        sa = template.get("subagentPermissions", {})
        qa = sa.get("qa-derive", {}).get("permissions", {}).get("deny", [])
        self.assertIn("Bash", qa, "qa-derive must deny Bash")


if __name__ == "__main__":
    unittest.main()
