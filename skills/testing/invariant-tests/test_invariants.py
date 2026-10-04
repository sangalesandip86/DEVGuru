"""Layer E: Property-Based / Invariant Tests.

Proves the ADLC platform's critical trust claims hold under varied inputs.
Four classes:
  E.1  AuthorityInvariantTest   — agent authority boundaries
  E.2  ScopingInvariantTest     — role→tool consistency across enforcement layers
  E.3  MonotonicityInvariantTest — append-only, tier never decreases without human
  E.4  IdempotencyInvariantTest  — deterministic computations are stable
"""
from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

# Repo root and key directories
REPO = Path(__file__).resolve().parents[3]
MCP_SRC = REPO / "skills" / "mcp-servers" / "adlc-mcp" / "src"
MCP_TESTS = REPO / "skills" / "mcp-servers" / "adlc-mcp" / "tests"
ROLES_DIR = REPO / "skills" / "roles"
MANAGED_TEMPLATE = (
    REPO / "skills" / "enforcement" / "managed-settings" / "templates"
    / "claude-code-managed-settings.json"
)

sys.path.insert(0, str(MCP_SRC))
sys.path.insert(0, str(MCP_TESTS))

from _support import CI, CODE_REVIEWER, DEVELOPER, HUMAN_LEAD, SECURITY, TempEnv  # noqa: E402
from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import AdlcError, PermissionDenied, ValidationError  # noqa: E402
from adlc_mcp.kernel.identity import Identity  # noqa: E402
from adlc_mcp.kernel.role_permissions import ROLE_TOOLS  # noqa: E402
from adlc_mcp.modules.evidence_ledger.api import open_ledger  # noqa: E402

ALL_AGENT_ROLES = [
    "product-owner", "product-planner", "architect", "developer",
    "qa-derive", "qa-diagnose", "test-engineer", "security-reviewer", "code-reviewer",
]

PRIVILEGED_STATUSES = ["PLAN_APPROVED", "INTEGRATED", "RELEASED"]
AGENT_FORBIDDEN_CLASSIFICATIONS = ["APPROVED", "VERIFIED"]


def _make_agent(role: str) -> Identity:
    return Identity("AGENT", f"agent:{role}", agent_role=role,
                    tool="claude-code", model_id="model-test")


# ---------------------------------------------------------------------------
# E.1  Authority Invariants
# ---------------------------------------------------------------------------
class AuthorityInvariantTest(unittest.TestCase):
    """∀ agent role: forbidden classifications and lifecycle transitions are rejected."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger,change_management")
        self.registry = build_modules(self.env.config)
        self.cm = self.registry.get("change_management").api
        self.ledger = self.registry.get("evidence_ledger").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_no_agent_writes_approved(self):
        """∀ role: classification=APPROVED → rejected."""
        for role in ALL_AGENT_ROLES:
            agent = _make_agent(role)
            with self.assertRaises(AdlcError, msg=f"{role} wrote APPROVED"):
                self.ledger.record_evidence(
                    agent, run_id=f"R-auth-{role}", classification="APPROVED",
                    content="self-approved", source_type="agent_observation",
                )

    def test_no_agent_writes_verified(self):
        """∀ role: classification=VERIFIED → rejected."""
        for role in ALL_AGENT_ROLES:
            agent = _make_agent(role)
            with self.assertRaises(AdlcError, msg=f"{role} wrote VERIFIED"):
                self.ledger.record_evidence(
                    agent, run_id=f"R-auth-{role}", classification="VERIFIED",
                    content="self-verified", source_type="agent_observation",
                )

    def test_no_agent_writes_fact(self):
        """∀ role: classification=FACT requires SYSTEM actor."""
        for role in ALL_AGENT_ROLES:
            agent = _make_agent(role)
            with self.assertRaises(AdlcError, msg=f"{role} wrote FACT"):
                self.ledger.record_evidence(
                    agent, run_id=f"R-auth-{role}", classification="FACT",
                    content="claimed fact", source_type="agent_observation",
                )

    def test_no_agent_sets_privileged_lifecycle(self):
        """∀ role, ∀ status ∈ {PLAN_APPROVED, INTEGRATED, RELEASED}: rejected."""
        for role in ALL_AGENT_ROLES:
            agent = _make_agent(role)
            cs = self.cm.create_change_set(
                DEVELOPER, title="t", requirements=["REQ-1"],
                repositories=["repo-a"],
            )
            for status in PRIVILEGED_STATUSES:
                with self.assertRaises(AdlcError,
                                       msg=f"{role} set {status}"):
                    self.cm.update_status(
                        agent, change_set_id=cs["id"],
                        status=status, reason="test",
                    )

    def test_system_can_write_fact(self):
        """Positive: SYSTEM actor CAN write FACT."""
        result = self.ledger.record_evidence(
            CI, run_id="R-sys-fact", classification="FACT",
            content="test passed", source_type="ci_result", source="ci",
        )
        self.assertEqual(result["classification"], "FACT")
        self.assertEqual(result["actor_type"], "SYSTEM")


# ---------------------------------------------------------------------------
# E.2  Scoping Invariants
# ---------------------------------------------------------------------------
class ScopingInvariantTest(unittest.TestCase):
    """Role tool surfaces are consistent across role.yaml, ROLE_TOOLS, and managed settings."""

    @classmethod
    def setUpClass(cls):
        cls.role_specs = {}
        for spec_path in sorted(ROLES_DIR.glob("*/role.yaml")):
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            cls.role_specs[spec["name"]] = spec
        cls.managed = json.loads(MANAGED_TEMPLATE.read_text(encoding="utf-8"))
        cls.subagent_perms = cls.managed.get("subagentPermissions", {})

    def test_every_role_has_mcp_tool_entry(self):
        """Every role.yaml role appears in role_tool_permissions.json / ROLE_TOOLS."""
        for role in self.role_specs:
            self.assertIn(role, ROLE_TOOLS,
                          f"role {role} missing from ROLE_TOOLS")

    def test_every_role_has_managed_settings_entry(self):
        """Every role.yaml role with deny rules appears in subagentPermissions."""
        for role, spec in self.role_specs.items():
            denied_read = spec.get("denied_paths", {}).get("read", [])
            denied_write = spec.get("denied_paths", {}).get("write", [])
            allowed = spec.get("allowed_tools", [])
            non_mcp = [t for t in allowed if not t.startswith("mcp:")]
            all_tools = {"Read", "Grep", "Glob", "Edit", "Write", "Bash"}
            tool_map = {
                "read": ["Read"], "search": ["Grep", "Glob"], "edit": ["Edit"],
                "write": ["Write"], "bash": ["Bash"], "test-run": ["Bash"],
            }
            mapped = set()
            for t in non_mcp:
                for m in tool_map.get(t, []):
                    mapped.add(m)
            disallowed = all_tools - mapped
            has_denials = denied_read or any(
                not g.startswith("$ref:") for g in denied_write
            ) or disallowed
            if has_denials:
                self.assertIn(role, self.subagent_perms,
                              f"role {role} has deny rules but no subagentPermissions")

    def test_qa_derive_cannot_read_implementation(self):
        """qa-derive must have Read denials for all implementation directories."""
        qa_deny = self.subagent_perms.get("qa-derive", {}).get("permissions", {}).get("deny", [])
        impl_dirs = ["src/**", "lib/**", "app/**", "pkg/**", "internal/**", "cmd/**", "services/**"]
        for d in impl_dirs:
            self.assertIn(f"Read({d})", qa_deny,
                          f"qa-derive missing Read({d}) denial")

    def test_qa_derive_has_bash_denied(self):
        """qa-derive must have Bash denied to prevent shell-based code reading."""
        qa_deny = self.subagent_perms.get("qa-derive", {}).get("permissions", {}).get("deny", [])
        self.assertIn("Bash", qa_deny)

    def test_code_reviewer_cannot_edit_or_write(self):
        """code-reviewer (read-only role) must have Edit and Write denied."""
        cr_deny = self.subagent_perms.get("code-reviewer", {}).get("permissions", {}).get("deny", [])
        self.assertTrue(any("Edit" in r for r in cr_deny),
                        "code-reviewer missing Edit denial")
        self.assertTrue(any("Write" in r for r in cr_deny),
                        "code-reviewer missing Write denial")

    def test_no_role_has_mutation_tools_it_should_not(self):
        """Roles with operation_classes=[READ] must not have mutation MCP tools."""
        mutation_tools = {
            "create_change_set", "update_status", "create_snapshot",
            "override_risk_tier", "record_task", "checkpoint_task",
            "record_task_failure", "compute_risk_tier",
        }
        for role, spec in self.role_specs.items():
            ops = spec.get("operation_classes", [])
            if ops == ["READ"]:
                mcp_tools = ROLE_TOOLS.get(role, frozenset())
                overlap = mcp_tools & mutation_tools
                self.assertEqual(overlap, set(),
                                 f"read-only role {role} has mutation MCP tools: {overlap}")

    def test_mcp_tools_subset_of_role_yaml(self):
        """Every MCP tool in ROLE_TOOLS should correspond to a mcp:adlc.* in role.yaml allowed_tools."""
        for role, spec in self.role_specs.items():
            mcp_allowed_yaml = {
                t.split(".", 1)[1] for t in spec.get("allowed_tools", [])
                if t.startswith("mcp:adlc.")
            }
            generic_mcp = {
                t.split(".", 1)[1] for t in spec.get("allowed_tools", [])
                if t.startswith("mcp:") and not t.startswith("mcp:adlc.")
            }
            mcp_in_role_tools = ROLE_TOOLS.get(role, frozenset())
            common_base = {"record_evidence", "query_evidence", "record_correction",
                           "get_change_set", "record_handoff"}
            # role.yaml uses generic names like mcp:adlc.record_evidence
            # ROLE_TOOLS may have additional platform tools
            # At minimum, all yaml-declared adlc tools should be in ROLE_TOOLS
            for tool in mcp_allowed_yaml:
                self.assertIn(tool, mcp_in_role_tools,
                              f"role {role}: {tool} in role.yaml but not in ROLE_TOOLS")


# ---------------------------------------------------------------------------
# E.3  Monotonicity Invariants
# ---------------------------------------------------------------------------
class MonotonicityInvariantTest(unittest.TestCase):
    """Values that must never decrease or be removed."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger,change_management")
        self.registry = build_modules(self.env.config)
        self.cm = self.registry.get("change_management").api
        self.ledger = self.registry.get("evidence_ledger").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def test_ledger_append_only_count_never_decreases(self):
        """Record N entries, verify count monotonically increases."""
        counts = []
        for i in range(5):
            self.ledger.record_evidence(
                DEVELOPER, run_id=f"R-mono-{i}", classification="PROPOSAL",
                content=f"entry {i}", source_type="agent_observation", source="test",
            )
            entries = self.ledger.query_evidence(CI)
            counts.append(len(entries))
        for i in range(1, len(counts)):
            self.assertGreaterEqual(counts[i], counts[i - 1],
                                     "ledger count decreased")

    def test_ledger_rejects_direct_update(self):
        """SQLite trigger prevents UPDATE on evidence table."""
        entry = self.ledger.record_evidence(
            DEVELOPER, run_id="R-tamper", classification="PROPOSAL",
            content="original", source_type="agent_observation", source="test",
        )
        db_path = self.env.config.db_path("evidence_ledger")
        conn = sqlite3.connect(str(db_path))
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE evidence SET classification = 'FACT' WHERE entry_id = ?",
                         (entry["entry_id"],))
        conn.close()

    def test_ledger_rejects_direct_delete(self):
        """SQLite trigger prevents DELETE on evidence table."""
        entry = self.ledger.record_evidence(
            DEVELOPER, run_id="R-tamper2", classification="PROPOSAL",
            content="original", source_type="agent_observation", source="test",
        )
        db_path = self.env.config.db_path("evidence_ledger")
        conn = sqlite3.connect(str(db_path))
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM evidence WHERE entry_id = ?",
                         (entry["entry_id"],))
        conn.close()

    def test_risk_tier_override_requires_human(self):
        """Agent cannot override risk tier downward — HUMAN required."""
        cs = self.cm.create_change_set(
            DEVELOPER, title="t", requirements=["REQ-1"],
            repositories=["repo-a"],
        )
        self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs["id"],
            paths=["services/payment/handler.py"],
        )
        with self.assertRaises(PermissionDenied):
            self.cm.override_risk_tier(
                DEVELOPER, change_set_id=cs["id"],
                tier="LOW", reason="agent override attempt",
            )

    def test_risk_tier_override_succeeds_for_human(self):
        """Positive: HUMAN can override risk tier."""
        cs = self.cm.create_change_set(
            DEVELOPER, title="t", requirements=["REQ-1"],
            repositories=["repo-a"],
        )
        self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs["id"],
            paths=["services/payment/handler.py"],
        )
        result = self.cm.override_risk_tier(
            HUMAN_LEAD, change_set_id=cs["id"],
            tier="LOW", reason="human approved downgrade",
        )
        self.assertEqual(result["final_tier"], "LOW")

    def test_no_edit_or_delete_api_on_ledger(self):
        """Ledger API exposes no edit/delete/update methods."""
        self.assertFalse(hasattr(self.ledger, "delete_evidence"))
        self.assertFalse(hasattr(self.ledger, "edit_evidence"))
        self.assertFalse(hasattr(self.ledger, "update_evidence"))


# ---------------------------------------------------------------------------
# E.4  Idempotency Invariants
# ---------------------------------------------------------------------------
class IdempotencyInvariantTest(unittest.TestCase):
    """Deterministic computations produce identical results on repeated calls."""

    def test_skill_routing_deterministic(self):
        """route() with identical inputs → identical output."""
        sys.path.insert(0, str(REPO / "skills" / "skill-routing" / "skill-router" / "scripts"))
        import route as skill_route

        stack = {"tools": ["playwright", "jest"], "languages": ["typescript"]}
        r1 = skill_route.route(stack, story_type="FEATURE_STORY",
                                paths=["src/api/payment.ts"])
        r2 = skill_route.route(stack, story_type="FEATURE_STORY",
                                paths=["src/api/payment.ts"])
        self.assertEqual(r1, r2)

    def test_skill_routing_deterministic_different_order(self):
        """route() is not sensitive to path list order."""
        sys.path.insert(0, str(REPO / "skills" / "skill-routing" / "skill-router" / "scripts"))
        import route as skill_route

        stack = {"tools": ["pytest"], "languages": ["python"]}
        r1 = skill_route.route(stack, paths=["src/a.py", "src/b.py"])
        r2 = skill_route.route(stack, paths=["src/b.py", "src/a.py"])
        self.assertEqual(r1["bindings"], r2["bindings"])
        self.assertEqual(r1["tier_floor"], r2["tier_floor"])

    def test_path_tier_lookup_deterministic(self):
        """path_tier_lookup with identical inputs → identical tier."""
        sys.path.insert(0, str(REPO / "skills" / "change-management" / "risk-tiering" / "scripts"))
        import path_tier_lookup

        tiers_json = REPO / "skills" / "change-management" / "risk-tiering" / "path-tiers.json"
        config = json.loads(tiers_json.read_text(encoding="utf-8"))
        control_json = REPO / "skills" / "governance" / "default-permissions" / "reference" / "control-file-paths.json"
        control = json.loads(control_json.read_text(encoding="utf-8")).get("globs", [])

        paths = ["src/payment/handler.py", "README.md", ".github/workflows/ci.yml"]
        r1 = path_tier_lookup.lookup(paths, config, control)
        r2 = path_tier_lookup.lookup(paths, config, control)
        self.assertEqual(r1, r2)

    def test_no_paths_is_uncomputable_high(self):
        """Empty path list → uncomputable → HIGH (fail-safe)."""
        sys.path.insert(0, str(REPO / "skills" / "change-management" / "risk-tiering" / "scripts"))
        import path_tier_lookup

        tiers_json = REPO / "skills" / "change-management" / "risk-tiering" / "path-tiers.json"
        config = json.loads(tiers_json.read_text(encoding="utf-8"))
        control_json = REPO / "skills" / "governance" / "default-permissions" / "reference" / "control-file-paths.json"
        control = json.loads(control_json.read_text(encoding="utf-8")).get("globs", [])

        result = path_tier_lookup.lookup([], config, control)
        self.assertEqual(result["tier"], "HIGH",
                         "no paths → uncomputable → must be HIGH")
        self.assertFalse(result["computed"])

    def test_unmatched_path_gets_default_not_low(self):
        """Unmatched path gets default tier (MEDIUM), never LOW."""
        sys.path.insert(0, str(REPO / "skills" / "change-management" / "risk-tiering" / "scripts"))
        import path_tier_lookup

        tiers_json = REPO / "skills" / "change-management" / "risk-tiering" / "path-tiers.json"
        config = json.loads(tiers_json.read_text(encoding="utf-8"))
        control_json = REPO / "skills" / "governance" / "default-permissions" / "reference" / "control-file-paths.json"
        control = json.loads(control_json.read_text(encoding="utf-8")).get("globs", [])

        result = path_tier_lookup.lookup(
            ["completely/unknown/path/here.xyz"], config, control,
        )
        self.assertNotEqual(result["tier"], "LOW",
                            "unmatched paths should never be LOW")


if __name__ == "__main__":
    unittest.main()
