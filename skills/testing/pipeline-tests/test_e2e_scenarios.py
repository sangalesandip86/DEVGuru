"""End-to-end scenario tests: realistic ADLC pipeline workflows via MCP API.

Tests what actually happens when someone uses the pipeline — realistic multi-stage
workflows through the real MCP API, covering:
  - Full INTAKE -> DESIGN -> IMPLEMENT evidence chains
  - BUG_FIX flow with root cause analysis and security review
  - UI story with convention scanning and contract drift detection
  - Authority boundary enforcement across all 8 agent roles
  - Edge cases: empty content, invalid classification, bad references

No LLM calls — these simulate the MCP tool calls an LLM agent would make,
exercising the same code paths as real usage.

    python -m pytest skills/testing/pipeline-tests/test_e2e_scenarios.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

MCP_SRC = Path(__file__).resolve().parents[2] / "mcp-servers" / "adlc-mcp" / "src"
MCP_TESTS = Path(__file__).resolve().parents[2] / "mcp-servers" / "adlc-mcp" / "tests"
sys.path.insert(0, str(MCP_SRC))
sys.path.insert(0, str(MCP_TESTS))

from _support import DEVELOPER, CODE_REVIEWER, HUMAN_LEAD, CI, TempEnv  # noqa: E402
from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError, NotFound  # noqa: E402
from adlc_mcp.kernel.identity import Identity  # noqa: E402

PRODUCT_PLANNER = Identity("AGENT", "agent:product-planner", agent_role="product-planner",
                           tool="claude-code", model_id="model-a")
ARCHITECT = Identity("AGENT", "agent:architect", agent_role="architect",
                     tool="claude-code", model_id="model-a")
QA_DERIVE = Identity("AGENT", "agent:qa-derive", agent_role="qa-derive",
                     tool="claude-code", model_id="model-a")
PRODUCT_OWNER = Identity("AGENT", "agent:product-owner", agent_role="product-owner",
                         tool="claude-code", model_id="model-a")
TEST_ENGINEER = Identity("AGENT", "agent:test-engineer", agent_role="test-engineer",
                         tool="claude-code", model_id="model-a")
SECURITY = Identity("AGENT", "agent:security-reviewer", agent_role="security-reviewer",
                    tool="claude-code", model_id="model-a")

ALL_MODULES = "evidence_ledger,change_management,work_planning,contract_registry"
RUN_ID = "run-e2e-test"


class _ScenarioBase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv(ALL_MODULES)
        self.registry = build_modules(self.env.config)
        self.ledger = self.registry.get("evidence_ledger").api
        self.cm = self.registry.get("change_management").api
        self.cr = self.registry.get("contract_registry").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def _create_cs(self, title, reqs, repos):
        return self.cm.create_change_set(DEVELOPER, title=title,
                                         requirements=reqs, repositories=repos)

    def _fact(self, content, cs_id, source="cmd:test"):
        return self.ledger.append_fact("test-hook", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output", "content": content,
            "source": source, "change_set_id": cs_id,
        })


class TestTaskManagerAPI(_ScenarioBase):
    """Scenario: Build a REST API for a task manager — full INTAKE->DESIGN->IMPLEMENT."""

    def test_full_pipeline(self):
        cs = self._create_cs("Task Manager REST API", ["REQ-E2E-1"], ["task-mgr"])
        cs_id = cs["id"]
        self.assertEqual(cs["status"], "DRAFT")

        req_fact = self._fact(
            "REQ-E2E-1: Build REST API with CRUD, filtering and pagination.", cs_id)
        self.assertEqual(req_fact["classification"], "FACT")
        self.assertEqual(req_fact["actor_type"], "SYSTEM")

        story = self.ledger.record_evidence(
            PRODUCT_PLANNER, run_id=RUN_ID, classification="INFERENCE",
            content="Decomposed into 3 stories: CRUD, filtering, validation. Sized S, S, XS.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[req_fact["entry_id"]],
        )
        self.assertEqual(story["agent_role"], "product-planner")

        code_fact = self._fact("package.json: express@4.18, prisma@5.8, zod@3.22", cs_id)
        design = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Express + Prisma stack. REST at /api/v1/tasks. Zod for validation.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[code_fact["entry_id"], req_fact["entry_id"]],
        )
        refs = json.loads(design["input_references"]) if isinstance(design["input_references"], str) else design["input_references"]
        self.assertEqual(len(refs), 2)

        question = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="QUESTION",
            content="Markdown or plain text for descriptions?",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"blocking": True},
        )
        self.assertGreater(len(self.ledger.blocking_items(cs_id)), 0)

        self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="PO confirmed: plain text only for v1.",
            source_type="TOOL", change_set_id=cs_id,
            answers_entry_id=question["entry_id"],
            input_references=[question["entry_id"]],
        )
        q_entries = [e for e in self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id, classification="QUESTION")
                     if e["entry_id"] == question["entry_id"]]
        self.assertEqual(q_entries[0]["derived_status"], "ANSWERED")

        decision = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="DECISION",
            content="Express router at /api/v1/tasks. Prisma TEXT column. ADR-0005.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[design["entry_id"]],
            lifecycle_state="PROPOSED",
        )
        self.assertEqual(decision["lifecycle_state"], "PROPOSED")

        ho1 = self.cm.record_handoff(
            ARCHITECT, change_set_id=cs_id, to_role="developer",
            payload={
                "summary": "Architecture approved",
                "inputs": [{"artifact_ref": "task-mgr@abc1234:package.json",
                            "content_hash": "sha256:" + "aa" * 32}],
                "outputs": [{"artifact_kind": "architecture-design",
                             "content_hash": "sha256:" + "bb" * 32}],
                "classifications": [],
            },
            verdict="ACCEPT",
        )
        self.assertEqual(ho1["from_role"], "architect")
        self.assertEqual(ho1["to_role"], "developer")

        test_fact = self._fact("npm test: 12 passed, 0 failed. Coverage: 87%", cs_id)
        impl = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="All CRUD endpoints passing. 12 unit tests, 87% coverage.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[test_fact["entry_id"]],
        )

        ho2 = self.cm.record_handoff(
            DEVELOPER, change_set_id=cs_id, to_role="code-reviewer",
            payload={
                "summary": "4 endpoints, 12 tests, 87% coverage",
                "inputs": [{"artifact_ref": "task-mgr@def5678:src/api/tasks.ts",
                            "content_hash": "sha256:" + "cc" * 32}],
                "outputs": [{"artifact_kind": "implementation",
                             "content_hash": "sha256:" + "dd" * 32}],
                "classifications": [],
            },
            verdict="ACCEPT",
        )
        self.assertEqual(ho2["to_role"], "code-reviewer")

        self.ledger.record_correction(
            CODE_REVIEWER, parent_entry_id=impl["entry_id"],
            run_id=RUN_ID,
            content="DELETE endpoint has 0% coverage.",
            source_type="TOOL",
        )
        orig = [e for e in self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
                if e["entry_id"] == impl["entry_id"]]
        self.assertEqual(orig[0]["derived_status"], "CHALLENGED")

        all_entries = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        classifications = {e["classification"] for e in all_entries}
        self.assertTrue({"FACT", "INFERENCE", "QUESTION", "DECISION"}.issubset(classifications))

        broken = [r for r in self.ledger.verify() if not r.get("ok", True)]
        self.assertEqual(len(broken), 0)

        full_cs = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(len(full_cs.get("handoffs", [])), 2)


class TestBugFixFlow(_ScenarioBase):
    """Scenario: Fix random logout bug — multi-repo, root cause, security review."""

    def test_bug_fix_pipeline(self):
        cs = self._create_cs("Fix random logout", ["BUG-2026-999"], ["auth-svc", "gateway"])
        cs_id = cs["id"]

        log_fact = self._fact(
            "auth.log: token refresh race condition for user_id=12345", cs_id,
            source="cmd:grep 'race condition' /var/log/auth.log")

        root_cause = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Root cause: no mutex on token refresh. 3% of multi-tab users affected.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[log_fact["entry_id"]],
        )

        fix = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="Add Redis SETNX mutex with 5s TTL. ADR-0011.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[root_cause["entry_id"]],
            lifecycle_state="PROPOSED",
        )
        self.assertEqual(fix["lifecycle_state"], "PROPOSED")

        risk = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="RISK",
            content="Redis down = all refreshes fail. Mitigation: fallback to no-mutex.",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"impact": "HIGH", "mitigation": "Redis fallback"},
        )
        self.assertEqual(risk["classification"], "RISK")

        sec = self.ledger.record_evidence(
            SECURITY, run_id=RUN_ID, classification="INFERENCE",
            content="SETNX key should include user_id. TTL 5s is fine. No new attack surface.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[fix["entry_id"]],
        )
        self.assertEqual(sec["agent_role"], "security-reviewer")

        self.cr.register_contract(
            DEVELOPER, contract_id="auth-refresh", provider="auth-svc", version="1",
            spec={"fields": {
                "refresh_token": {"type": "string", "required": True},
                "access_token": {"type": "string", "required": True},
            }},
            type="http", consumers=["gateway"],
        )
        drift = self.cr.detect_drift(
            DEVELOPER, contract_id="auth-refresh",
            observed_spec={"fields": {
                "refresh_token": {"type": "string", "required": True},
                "access_token": {"type": "string", "required": True},
            }},
        )
        self.assertFalse(drift["drift"])

    def test_request_response_spec_format(self):
        """Contract registry should accept request/response shorthand."""
        self.cr.register_contract(
            DEVELOPER, contract_id="login-api", provider="auth-svc", version="1",
            spec={"request": {"email": {"type": "string", "required": True},
                              "password": {"type": "string", "required": True}},
                  "response": {"token": {"type": "string", "required": True},
                               "expires_in": {"type": "integer", "required": True}}},
            type="http", consumers=["web-app"],
        )
        drift = self.cr.detect_drift(
            DEVELOPER, contract_id="login-api",
            observed_spec={"request": {"email": {"type": "string", "required": True},
                                       "password": {"type": "string", "required": True}},
                           "response": {"token": {"type": "string", "required": True},
                                        "expires_in": {"type": "integer", "required": True}}},
        )
        self.assertFalse(drift["drift"])

    def test_new_contract_types(self):
        """Contract registry should accept graphql, module, websocket types."""
        for ctype in ("graphql", "module", "websocket"):
            self.cr.register_contract(
                DEVELOPER, contract_id=f"test-{ctype}", provider="svc", version="1",
                spec={"fields": {"id": {"type": "string"}}},
                type=ctype,
            )


class TestDarkModeUI(_ScenarioBase):
    """Scenario: Add dark mode — conventions, deviations, contract drift."""

    def test_convention_flow(self):
        cs = self._create_cs("Dashboard dark mode", ["REQ-UI-42"], ["dashboard-app"])
        cs_id = cs["id"]

        css_fact = self._fact(
            "src/styles/theme.ts: lightTheme with 42 CSS custom properties, styled-components.",
            cs_id, source="cmd:cat src/styles/theme.ts")

        convention = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Follow existing ThemeProvider pattern. Add darkTheme + ThemeToggle.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[css_fact["entry_id"]],
        )

        deviation = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="New dep: use-local-storage-state@19. Needs architect REVIEWED. ADR-0015.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[convention["entry_id"]],
            lifecycle_state="PROPOSED",
        )
        self.assertEqual(deviation["lifecycle_state"], "PROPOSED")

        ho = self.cm.record_handoff(
            DEVELOPER, change_set_id=cs_id, to_role="code-reviewer",
            payload={
                "summary": "Dark mode: 42 CSS vars, ThemeToggle, localStorage. 8 unit tests.",
                "inputs": [{"artifact_ref": "dashboard-app@abc1234:src/styles/theme.ts",
                            "content_hash": "sha256:" + "11" * 32}],
                "outputs": [
                    {"artifact_kind": "implementation", "content_hash": "sha256:" + "22" * 32},
                    {"artifact_kind": "unit_tests", "content_hash": "sha256:" + "33" * 32},
                ],
                "classifications": [],
            },
            verdict="ACCEPT",
        )
        self.assertIn("id", ho)

        theme = {"fields": {
            "lightTheme": {"type": "object", "required": True},
            "darkTheme": {"type": "object", "required": True},
            "ThemeToggle": {"type": "component", "required": True},
        }}
        self.cr.register_contract(
            DEVELOPER, contract_id="theme", provider="dashboard-app", version="2",
            spec=theme, type="schema", consumers=["widgets"],
        )
        self.assertFalse(self.cr.detect_drift(
            DEVELOPER, contract_id="theme", observed_spec=theme)["drift"])

        drift = self.cr.detect_drift(
            DEVELOPER, contract_id="theme",
            observed_spec={"fields": {
                "lightTheme": {"type": "object", "required": True},
                "darkTheme": {"type": "object", "required": True},
            }},
        )
        self.assertTrue(drift["drift"])


class TestAuthorityBoundaries(_ScenarioBase):
    """Every agent role must be blocked from writing FACT entries."""

    def test_all_roles_blocked_from_fact(self):
        cs = self._create_cs("Authority test", ["REQ-AUTH"], ["test-repo"])
        cs_id = cs["id"]
        for identity, name in [(DEVELOPER, "developer"), (ARCHITECT, "architect"),
                               (PRODUCT_PLANNER, "product-planner"),
                               (CODE_REVIEWER, "code-reviewer"),
                               (SECURITY, "security-reviewer"),
                               (QA_DERIVE, "qa-derive"),
                               (TEST_ENGINEER, "test-engineer"),
                               (PRODUCT_OWNER, "product-owner")]:
            with self.assertRaises(PermissionDenied, msg=f"{name} should not write FACT"):
                self.ledger.record_evidence(
                    identity, run_id=RUN_ID, classification="FACT",
                    content="Should fail", source_type="command_output",
                    change_set_id=cs_id)

    def test_correction_nonexistent_entry(self):
        with self.assertRaises(NotFound):
            self.ledger.record_correction(
                CODE_REVIEWER, parent_entry_id="ENTRY-ghost",
                run_id=RUN_ID, content="Ghost", source_type="TOOL")

    def test_cannot_answer_decision(self):
        cs = self._create_cs("Decision test", ["REQ-D"], ["r"])
        decision = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="Use GraphQL", source_type="TOOL",
            change_set_id=cs["id"], lifecycle_state="PROPOSED",
        )
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="Answering a decision", source_type="TOOL",
                change_set_id=cs["id"],
                answers_entry_id=decision["entry_id"],
                input_references=[decision["entry_id"]])


class TestEdgeCases(_ScenarioBase):
    """Edge cases that would trip up LLM agents in real usage."""

    def test_empty_content_isolated(self):
        """Empty content is rejected even when input_references are valid."""
        cs = self._create_cs("Edge", ["REQ-X"], ["r"])
        fact = self._fact("test", cs["id"])
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="", source_type="TOOL", change_set_id=cs["id"],
                input_references=[fact["entry_id"]])

    def test_inference_empty_refs(self):
        cs = self._create_cs("Edge", ["REQ-X"], ["r"])
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="Unsourced", source_type="TOOL",
                change_set_id=cs["id"], input_references=[])

    def test_inference_no_refs(self):
        cs = self._create_cs("Edge", ["REQ-X"], ["r"])
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="Unsourced", source_type="TOOL",
                change_set_id=cs["id"])

    def test_assumption_missing_expiry(self):
        cs = self._create_cs("Edge", ["REQ-X"], ["r"])
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="ASSUMPTION",
                content="Guess", source_type="TOOL",
                change_set_id=cs["id"],
                metadata={"impact": "LOW"})

    def test_assumption_missing_impact(self):
        cs = self._create_cs("Edge", ["REQ-X"], ["r"])
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="ASSUMPTION",
                content="Guess", source_type="TOOL",
                change_set_id=cs["id"],
                metadata={"expires_at": "2027-01-01T00:00:00Z"})

    def test_unknown_classification(self):
        cs = self._create_cs("Edge", ["REQ-X"], ["r"])
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="PROOF",
                content="Proven", source_type="TOOL",
                change_set_id=cs["id"])

    def test_empty_run_id(self):
        cs = self._create_cs("Edge", ["REQ-X"], ["r"])
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id="", classification="QUESTION",
                content="What?", source_type="TOOL",
                change_set_id=cs["id"], metadata={"blocking": False})

    def test_artifact_ref_short_sha_rejected(self):
        """artifact_ref with sha shorter than 7 chars must be rejected."""
        cs = self._create_cs("Edge", ["REQ-X"], ["r"])
        with self.assertRaises(ValidationError):
            self.cm.record_handoff(
                DEVELOPER, change_set_id=cs["id"], to_role="code-reviewer",
                payload={
                    "summary": "Test",
                    "inputs": [{"artifact_ref": "repo@abc:file.ts",
                                "content_hash": "sha256:" + "ff" * 32}],
                    "outputs": [],
                    "classifications": [],
                },
                verdict="ACCEPT",
            )


if __name__ == "__main__":
    unittest.main()
