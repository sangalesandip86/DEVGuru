#!/usr/bin/env python3
"""Multi-agent delegation + LLM-as-judge evaluation.

Tests whether the ADLC platform correctly:
  1. Spins up agents with distinct role identities
  2. Delegates tasks to the right role via handoffs
  3. Each role performs ONLY its authorized duties
  4. Cross-role evidence chains are complete and accurate
  5. A "judge" function scores the quality of each role's output

The judge is a deterministic scoring function that evaluates what a real LLM
judge would check: role accuracy, permission boundaries, evidence quality,
handoff completeness, and cross-role coordination.

    python -m unittest skills/testing/pipeline-tests/test_multiagent_judge.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_SRC = REPO_ROOT / "skills" / "mcp-servers" / "adlc-mcp" / "src"
MCP_TESTS = REPO_ROOT / "skills" / "mcp-servers" / "adlc-mcp" / "tests"
sys.path.insert(0, str(MCP_SRC))
sys.path.insert(0, str(MCP_TESTS))

from _support import DEVELOPER, CODE_REVIEWER, HUMAN_LEAD, CI, SECURITY, TempEnv  # noqa: E402
from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError, NotFound  # noqa: E402
from adlc_mcp.kernel.identity import Identity  # noqa: E402

# ---- All 9 agent role identities ----
PRODUCT_OWNER = Identity("AGENT", "agent:product-owner", agent_role="product-owner",
                         tool="claude-code", model_id="opus-4")
PRODUCT_PLANNER = Identity("AGENT", "agent:product-planner", agent_role="product-planner",
                           tool="claude-code", model_id="opus-4")
ARCHITECT = Identity("AGENT", "agent:architect", agent_role="architect",
                     tool="claude-code", model_id="opus-4")
DEV = Identity("AGENT", "agent:developer", agent_role="developer",
               tool="claude-code", model_id="opus-4")
QA_DERIVE = Identity("AGENT", "agent:qa-derive", agent_role="qa-derive",
                     tool="claude-code", model_id="opus-4")
QA_DIAGNOSE = Identity("AGENT", "agent:qa-diagnose", agent_role="qa-diagnose",
                       tool="claude-code", model_id="opus-4")
TEST_ENGINEER = Identity("AGENT", "agent:test-engineer", agent_role="test-engineer",
                         tool="claude-code", model_id="opus-4")
SEC_REVIEWER = Identity("AGENT", "agent:security-reviewer", agent_role="security-reviewer",
                        tool="claude-code", model_id="opus-4")
CODE_REV = Identity("AGENT", "agent:code-reviewer", agent_role="code-reviewer",
                    tool="claude-code", model_id="opus-4")

ALL_MODULES = "evidence_ledger,change_management,work_planning,contract_registry"
RUN_ID = "run-multiagent"
SHA = "a" * 7
HASH = "sha256:" + "11" * 32


# =========================================================================
# Judge: scores each role's work product
# =========================================================================
@dataclass
class RoleScore:
    role: str
    evidence_produced: int = 0
    correct_classifications: int = 0
    wrong_classifications: int = 0
    permission_violations_caught: int = 0
    permission_violations_missed: int = 0
    handoffs_sent: int = 0
    handoffs_received: int = 0
    grounding_ratio: float = 1.0
    stayed_in_lane: bool = True
    issues: list = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        total = self.correct_classifications + self.wrong_classifications
        return self.correct_classifications / total if total > 0 else 1.0

    @property
    def score(self) -> float:
        """0-100 composite score."""
        acc = self.accuracy * 40
        grounding = self.grounding_ratio * 30
        lane = 20 if self.stayed_in_lane else 0
        perm = 10 if self.permission_violations_missed == 0 else 0
        return acc + grounding + lane + perm


def judge_evidence(entries: list[dict], role: str, expected_classifications: set[str]) -> RoleScore:
    """Judge a role's evidence output against expected behavior."""
    s = RoleScore(role=role)
    role_entries = [e for e in entries if e.get("agent_role") == role]
    s.evidence_produced = len(role_entries)

    for e in role_entries:
        cls = e["classification"]
        if cls in expected_classifications:
            s.correct_classifications += 1
        else:
            s.wrong_classifications += 1
            s.issues.append(f"{role} wrote {cls}, expected one of {expected_classifications}")

        if cls == "INFERENCE":
            refs = json.loads(e["input_references"]) if isinstance(
                e["input_references"], str) else (e["input_references"] or [])
            if not refs:
                s.grounding_ratio = 0.0
                s.issues.append(f"{role} wrote unsourced INFERENCE")

    if role_entries:
        grounded = sum(1 for e in role_entries
                       if e["classification"] != "INFERENCE" or
                       (json.loads(e["input_references"]) if isinstance(
                           e["input_references"], str) else (e["input_references"] or [])))
        s.grounding_ratio = grounded / len(role_entries)

    return s


def judge_handoffs(handoffs: list[dict], expected_chain: list[tuple[str, str]]) -> dict:
    """Judge whether the handoff chain matches the expected role delegation."""
    actual_chain = [(h["from_role"], h["to_role"]) for h in handoffs]
    matched = sum(1 for exp in expected_chain if exp in actual_chain)
    missing = [exp for exp in expected_chain if exp not in actual_chain]
    extra = [act for act in actual_chain if act not in expected_chain]
    return {
        "expected": len(expected_chain),
        "matched": matched,
        "missing": missing,
        "extra": extra,
        "completeness": matched / len(expected_chain) if expected_chain else 1.0,
    }


def judge_permissions(violations: list[dict]) -> dict:
    """Judge whether the platform correctly enforced role permissions."""
    caught = [v for v in violations if v["caught"]]
    missed = [v for v in violations if not v["caught"]]
    return {
        "total_probes": len(violations),
        "caught": len(caught),
        "missed": len(missed),
        "enforcement_rate": len(caught) / len(violations) if violations else 1.0,
        "missed_details": [v["description"] for v in missed],
    }


# =========================================================================
# Test base
# =========================================================================
class _MultiAgentBase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv(ALL_MODULES)
        self.registry = build_modules(self.env.config)
        self.ledger = self.registry.get("evidence_ledger").api
        self.cm = self.registry.get("change_management").api
        self.wp = self.registry.get("work_planning").api
        self.cr = self.registry.get("contract_registry").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def _cs(self, title, reqs, repos, **kw):
        return self.cm.create_change_set(DEV, title=title,
                                         requirements=reqs, repositories=repos, **kw)

    def _fact(self, content, cs_id, source="cmd:test"):
        return self.ledger.append_fact("test-hook", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output", "content": content,
            "source": source, "change_set_id": cs_id,
        })

    def _handoff(self, identity, cs_id, to_role, summary, verdict="ACCEPT"):
        return self.cm.record_handoff(
            identity, change_set_id=cs_id, to_role=to_role,
            payload={
                "summary": summary,
                "inputs": [{"artifact_ref": f"repo@{SHA}:src/main.ts",
                            "content_hash": HASH}],
                "outputs": [{"artifact_kind": "implementation",
                             "content_hash": HASH}],
                "classifications": [],
            },
            verdict=verdict,
        )


# =========================================================================
# Test 1: Full 9-role delegation pipeline
# =========================================================================
class TestFullRoleDelegation(_MultiAgentBase):
    """A feature requirement flows through all 9 roles with proper handoffs."""

    def test_full_pipeline_delegation(self):
        """Simulate: 'Add webhook notifications for order events'
        flowing through PO → planner → architect → dev → qa-derive →
        test-engineer → code-reviewer → security-reviewer → qa-diagnose."""

        cs = self._cs("Add webhook notifications", ["REQ-WEBHOOK-1"],
                      ["order-svc", "webhook-svc"])
        cs_id = cs["id"]

        # ---- SYSTEM: Hooks capture initial facts ----
        f1 = self._fact("order-svc/src/events.ts: OrderEventEmitter with 4 event types",
                        cs_id, source="cmd:cat order-svc/src/events.ts")
        f2 = self._fact("No webhook delivery system exists in the codebase",
                        cs_id, source="cmd:grep -r webhook .")

        # ---- PRODUCT-OWNER: Raises requirement, records intent ----
        po_intent = self.ledger.record_evidence(
            PRODUCT_OWNER, run_id=RUN_ID, classification="DECISION",
            content="Webhook notifications for order events are needed for partner integrations. "
                    "Priority: P1 for Q4. Must support retry with exponential backoff.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[f1["entry_id"]],
            lifecycle_state="PROPOSED",
        )
        po_question = self.ledger.record_evidence(
            PRODUCT_OWNER, run_id=RUN_ID, classification="QUESTION",
            content="Which order events should partners receive? All 4, or a configurable subset?",
            source_type="agent_analysis", change_set_id=cs_id,
            metadata={"blocking": True},
        )
        self._handoff(PRODUCT_OWNER, cs_id, "product-planner",
                      "Decompose webhook notification requirement into stories")

        # ---- PRODUCT-PLANNER: Decomposes into stories ----
        planner_plan = self.ledger.record_evidence(
            PRODUCT_PLANNER, run_id=RUN_ID, classification="INFERENCE",
            content="Decomposition: 3 stories — ST-20 (webhook registration API), "
                    "ST-21 (event dispatch with retry), ST-22 (webhook management UI). "
                    "Each story has 3-4 acceptance criteria.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[po_intent["entry_id"]],
        )
        # Ingest plan via SYSTEM
        self.wp.ingest_plan_commit(CI, repository="order-svc", commit_sha="b" * 7, items=[
            {"id": "REQ-1", "path": "plans/requirements/REQ-1.json",
             "data": {"title": "Webhook notifications for order events"}},
            {"id": "ST-20", "path": "plans/stories/ST-20.json", "data": {
                "title": "Webhook registration API",
                "type": "FEATURE_STORY", "size": "M", "source_refs": ["REQ-1"],
                "acceptance_criteria": [
                    {"id": "ST-20/AC-1", "given": "A partner", "when": "they POST to /webhooks",
                     "then": "a webhook endpoint is registered with URL and secret",
                     "kind": "functional", "verification": "automated"},
                    {"id": "ST-20/AC-2", "given": "An invalid URL", "when": "registration attempted",
                     "then": "400 with validation error",
                     "kind": "negative", "verification": "automated"},
                    {"id": "ST-20/AC-3", "given": "A registered webhook", "when": "partner DELETEs it",
                     "then": "webhook is removed and no further events delivered",
                     "kind": "functional", "verification": "automated"},
                ],
            }},
        ])
        self._handoff(PRODUCT_PLANNER, cs_id, "architect",
                      "Stories decomposed: ST-20 webhook registration API")

        # ---- ARCHITECT: Designs the system ----
        arch_design = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="DECISION",
            content="Architecture: webhook-svc as separate microservice. Uses BullMQ for "
                    "reliable delivery with exponential backoff (1s, 2s, 4s, 8s, 16s). "
                    "HMAC-SHA256 signing with per-webhook secret. "
                    "Event fan-out via Redis pub/sub from order-svc.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[planner_plan["entry_id"], f1["entry_id"]],
            lifecycle_state="PROPOSED",
        )
        arch_risk = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="RISK",
            content="Webhook secrets stored in plaintext in DB. Must encrypt at rest "
                    "using AES-256-GCM with key from environment variable.",
            source_type="agent_analysis", change_set_id=cs_id,
            metadata={"impact": "HIGH", "mitigation": "Encrypt secrets with AES-256-GCM"},
        )
        # Register contract
        self.cr.register_contract(
            ARCHITECT, contract_id="webhook-delivery-api", provider="webhook-svc",
            version="1.0.0", type="http", consumers=["partner-portal"],
            spec={"fields": {
                "url": {"type": "string", "required": True},
                "secret": {"type": "string", "required": True},
                "events": {"type": "array", "required": True},
            }},
        )
        self._handoff(ARCHITECT, cs_id, "developer",
                      "Architecture: webhook-svc with BullMQ, HMAC signing, Redis pub/sub")

        # ---- QA-DERIVE: Creates test design (implementation-blind) ----
        qa_design = self.ledger.record_evidence(
            QA_DERIVE, run_id=RUN_ID, classification="INFERENCE",
            content="Test design for ST-20: "
                    "1. Register webhook with valid URL → 201, secret returned "
                    "2. Register with invalid URL → 400 "
                    "3. Delete registered webhook → 204, no more deliveries "
                    "4. Duplicate URL → idempotent or 409 "
                    "5. HMAC signature verification on delivery",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[po_intent["entry_id"]],
        )
        self._handoff(QA_DERIVE, cs_id, "test-engineer",
                      "Test design for ST-20: 5 test cases")

        # ---- DEVELOPER: Implements the story ----
        dev_impl = self.ledger.record_evidence(
            DEV, run_id=RUN_ID, classification="INFERENCE",
            content="Implementation: webhook-svc/src/routes/webhooks.ts with POST/DELETE. "
                    "HMAC signing in webhook-svc/src/crypto/hmac.ts. "
                    "BullMQ producer in order-svc/src/events/webhook-dispatcher.ts.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[arch_design["entry_id"]],
        )
        dev_tests = self._fact(
            "npm test: 12/12 pass. Coverage: webhooks.ts 94%, hmac.ts 100%, dispatcher.ts 87%.",
            cs_id, source="cmd:npm test --coverage")
        self._handoff(DEV, cs_id, "code-reviewer",
                      "Webhook registration API implemented with tests")

        # ---- TEST-ENGINEER: Binds qa-derive's test design ----
        te_impl = self.ledger.record_evidence(
            TEST_ENGINEER, run_id=RUN_ID, classification="INFERENCE",
            content="Test binding: jest integration tests in test/integration/webhooks.test.ts. "
                    "Using supertest for HTTP, nock for external URL validation. "
                    "5 tests matching qa-derive design + 2 edge cases (timeout, malformed JSON).",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[qa_design["entry_id"]],
        )
        self._handoff(TEST_ENGINEER, cs_id, "qa-diagnose",
                      "Test binding complete: 7 integration tests")

        # ---- CODE-REVIEWER: Reviews the implementation ----
        cr_review = self.ledger.record_evidence(
            CODE_REV, run_id=RUN_ID, classification="DECISION",
            content="Code review: ACCEPT. Clean separation of concerns. "
                    "Minor: consider extracting HMAC key rotation into a separate module. "
                    "No bugs found. Test coverage adequate.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[dev_impl["entry_id"]],
            lifecycle_state="REVIEWED",
        )
        self._handoff(CODE_REV, cs_id, "security-reviewer",
                      "Code review passed: ACCEPT")

        # ---- SECURITY-REVIEWER: Security pass ----
        sec_review = self.ledger.record_evidence(
            SEC_REVIEWER, run_id=RUN_ID, classification="DECISION",
            content="Security review: ACCEPT with condition. "
                    "HMAC-SHA256 is correct. Secret storage needs encryption at rest "
                    "(tracked as RISK). No injection vectors. Rate limiting on "
                    "registration endpoint recommended.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[dev_impl["entry_id"], arch_risk["entry_id"]],
            lifecycle_state="REVIEWED",
        )
        self._handoff(SEC_REVIEWER, cs_id, "developer",
                      "Security review: ACCEPT with encryption condition",
                      verdict="ACCEPT")

        # ---- QA-DIAGNOSE: Diagnoses any test failures ----
        qa_diag = self.ledger.record_evidence(
            QA_DIAGNOSE, run_id=RUN_ID, classification="INFERENCE",
            content="All 7 integration tests pass. Test #4 (duplicate URL) returns 409 — "
                    "matches AC. HMAC verification test confirms correct signature. "
                    "No diagnosis needed — clean run.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[te_impl["entry_id"], dev_tests["entry_id"]],
        )

        # ========= JUDGE: Evaluate each role's work =========
        all_evidence = self.ledger.query_evidence(DEV, change_set_id=cs_id, limit=1000)
        cs_state = self.cm.get_change_set(DEV, cs_id)
        handoffs = cs_state["handoffs"]

        # Judge each role's evidence classifications
        scores = {}
        scores["product-owner"] = judge_evidence(
            all_evidence, "product-owner", {"DECISION", "QUESTION", "RISK"})
        scores["product-planner"] = judge_evidence(
            all_evidence, "product-planner", {"INFERENCE"})
        scores["architect"] = judge_evidence(
            all_evidence, "architect", {"DECISION", "INFERENCE", "RISK", "PROPOSAL"})
        scores["developer"] = judge_evidence(
            all_evidence, "developer", {"INFERENCE", "DECISION"})
        scores["qa-derive"] = judge_evidence(
            all_evidence, "qa-derive", {"INFERENCE"})
        scores["test-engineer"] = judge_evidence(
            all_evidence, "test-engineer", {"INFERENCE"})
        scores["code-reviewer"] = judge_evidence(
            all_evidence, "code-reviewer", {"DECISION", "INFERENCE"})
        scores["security-reviewer"] = judge_evidence(
            all_evidence, "security-reviewer", {"DECISION", "INFERENCE", "RISK"})
        scores["qa-diagnose"] = judge_evidence(
            all_evidence, "qa-diagnose", {"INFERENCE"})

        # Every role should have produced evidence
        for role, s in scores.items():
            self.assertGreater(s.evidence_produced, 0,
                               f"{role} produced no evidence — was not delegated work")

        # Every role's evidence should match expected classifications
        for role, s in scores.items():
            self.assertEqual(s.accuracy, 1.0,
                             f"{role} accuracy {s.accuracy:.0%}: {s.issues}")

        # Every role's evidence should be grounded
        for role, s in scores.items():
            self.assertEqual(s.grounding_ratio, 1.0,
                             f"{role} has ungrounded evidence")

        # Judge handoff chain
        expected_handoffs = [
            ("product-owner", "product-planner"),
            ("product-planner", "architect"),
            ("architect", "developer"),
            ("qa-derive", "test-engineer"),
            ("developer", "code-reviewer"),
            ("test-engineer", "qa-diagnose"),
            ("code-reviewer", "security-reviewer"),
            ("security-reviewer", "developer"),
        ]
        handoff_result = judge_handoffs(handoffs, expected_handoffs)
        self.assertEqual(handoff_result["completeness"], 1.0,
                         f"Handoff chain incomplete. Missing: {handoff_result['missing']}")

        # All 9 roles produced work
        roles_with_evidence = {e["agent_role"] for e in all_evidence if e.get("agent_role")}
        self.assertEqual(len(roles_with_evidence), 9,
                         f"Not all 9 roles produced evidence: {roles_with_evidence}")

        # Print judge scorecard
        print("\n" + "=" * 70)
        print("MULTI-AGENT JUDGE SCORECARD")
        print("=" * 70)
        for role, s in scores.items():
            print(f"  {role:22s}  score={s.score:5.1f}/100  "
                  f"evidence={s.evidence_produced}  "
                  f"accuracy={s.accuracy:.0%}  "
                  f"grounding={s.grounding_ratio:.0%}"
                  + (f"  ISSUES: {s.issues}" if s.issues else ""))
        print(f"\n  Handoff completeness: {handoff_result['completeness']:.0%} "
              f"({handoff_result['matched']}/{handoff_result['expected']})")
        print("=" * 70)


# =========================================================================
# Test 2: Permission boundary enforcement — every role tested
# =========================================================================
class TestRolePermissionBoundaries(_MultiAgentBase):
    """Every role is probed for actions it should NOT be able to perform."""

    def test_no_agent_can_write_facts(self):
        """All 9 agent roles are blocked from writing FACTs."""
        cs = self._cs("Test", ["T-1"], ["repo"])
        violations = []
        for role_id, role_name in [
            (PRODUCT_OWNER, "product-owner"), (PRODUCT_PLANNER, "product-planner"),
            (ARCHITECT, "architect"), (DEV, "developer"),
            (QA_DERIVE, "qa-derive"), (QA_DIAGNOSE, "qa-diagnose"),
            (TEST_ENGINEER, "test-engineer"), (SEC_REVIEWER, "security-reviewer"),
            (CODE_REV, "code-reviewer"),
        ]:
            caught = False
            try:
                self.ledger.record_evidence(
                    role_id, run_id=RUN_ID, classification="FACT",
                    content="Fabricated fact", source_type="agent_analysis",
                    source="observation", change_set_id=cs["id"],
                )
            except PermissionDenied:
                caught = True
            violations.append({"role": role_name, "action": "write FACT",
                               "caught": caught, "description": f"{role_name} write FACT"})

        result = judge_permissions(violations)
        self.assertEqual(result["enforcement_rate"], 1.0,
                         f"FACT write not blocked for: {result['missed_details']}")

    def test_only_human_can_approve_lifecycle(self):
        """APPROVED lifecycle_state is human-only — all agent roles blocked."""
        cs = self._cs("Test", ["T-2"], ["repo"])
        fact = self._fact("data", cs["id"])
        violations = []

        for role_id, role_name in [
            (PRODUCT_OWNER, "product-owner"), (ARCHITECT, "architect"),
            (DEV, "developer"), (CODE_REV, "code-reviewer"),
        ]:
            caught = False
            try:
                self.ledger.record_evidence(
                    role_id, run_id=RUN_ID, classification="DECISION",
                    content="Approved", source_type="agent_analysis",
                    change_set_id=cs["id"], input_references=[fact["entry_id"]],
                    lifecycle_state="APPROVED",
                )
            except PermissionDenied:
                caught = True
            violations.append({"role": role_name, "action": "set APPROVED",
                               "caught": caught, "description": f"{role_name} set APPROVED"})

        result = judge_permissions(violations)
        self.assertEqual(result["enforcement_rate"], 1.0,
                         f"APPROVED not blocked for: {result['missed_details']}")

    def test_only_system_can_ingest_forge_events(self):
        """Agents cannot ingest forge events — only SYSTEM/CI."""
        cs = self._cs("Test", ["T-3"], ["repo"])
        self.cm.update_status(DEV, change_set_id=cs["id"],
                              status="SCOPED", reason="s")
        self.cm.update_status(DEV, change_set_id=cs["id"],
                              status="PLANNED", reason="p")
        violations = []

        for role_id, role_name in [
            (ARCHITECT, "architect"), (DEV, "developer"),
            (SEC_REVIEWER, "security-reviewer"),
        ]:
            caught = False
            try:
                self.cm.ingest_forge_event(
                    role_id, change_set_id=cs["id"],
                    event_type="plan_check_passed", payload={},
                )
            except PermissionDenied:
                caught = True
            violations.append({"role": role_name, "action": "ingest forge event",
                               "caught": caught, "description": f"{role_name} ingest forge"})

        result = judge_permissions(violations)
        self.assertEqual(result["enforcement_rate"], 1.0,
                         f"Forge ingest not blocked for: {result['missed_details']}")

    def test_only_system_can_ingest_plan_commits(self):
        """Only SYSTEM can ingest plan commits — agents cannot."""
        violations = []
        for role_id, role_name in [
            (PRODUCT_PLANNER, "product-planner"), (DEV, "developer"),
        ]:
            caught = False
            try:
                self.wp.ingest_plan_commit(
                    role_id, repository="repo", commit_sha="c" * 7,
                    items=[{"id": "REQ-1", "path": "plans/requirements/REQ-1.json",
                            "data": {"title": "Test"}}],
                )
            except PermissionDenied:
                caught = True
            violations.append({"role": role_name, "action": "ingest plan commit",
                               "caught": caught, "description": f"{role_name} ingest plan"})

        result = judge_permissions(violations)
        self.assertEqual(result["enforcement_rate"], 1.0,
                         f"Plan ingest not blocked for: {result['missed_details']}")

    def test_only_human_can_cancel(self):
        """Only HUMAN can set CANCELLED — all agent roles blocked."""
        violations = []
        for role_id, role_name in [
            (PRODUCT_OWNER, "product-owner"), (DEV, "developer"),
            (ARCHITECT, "architect"),
        ]:
            cs = self._cs(f"Test-{role_name}", [f"T-{role_name}"], ["repo"])
            caught = False
            try:
                self.cm.update_status(role_id, change_set_id=cs["id"],
                                      status="CANCELLED", reason="want to cancel")
            except PermissionDenied:
                caught = True
            violations.append({"role": role_name, "action": "CANCELLED",
                               "caught": caught, "description": f"{role_name} cancel"})

        result = judge_permissions(violations)
        self.assertEqual(result["enforcement_rate"], 1.0,
                         f"CANCELLED not blocked for: {result['missed_details']}")

    def test_only_human_can_override_risk_tier(self):
        """Risk tier overrides are human-only."""
        cs = self._cs("Test", ["T-5"], ["repo"])
        self.cm.compute_risk_tier(DEV, change_set_id=cs["id"],
                                  paths=["src/main.ts"], reason_codes=[], diff_lines=10)
        violations = []
        for role_id, role_name in [(ARCHITECT, "architect"), (DEV, "developer")]:
            caught = False
            try:
                self.cm.override_risk_tier(role_id, change_set_id=cs["id"],
                                           tier="LOW", reason="downgrade")
            except PermissionDenied:
                caught = True
            violations.append({"role": role_name, "action": "override risk tier",
                               "caught": caught, "description": f"{role_name} override risk"})

        result = judge_permissions(violations)
        self.assertEqual(result["enforcement_rate"], 1.0,
                         f"Risk override not blocked for: {result['missed_details']}")

    def test_agent_cannot_set_verified(self):
        """VERIFIED lifecycle state is SYSTEM-only — agents cannot claim machine verification."""
        cs = self._cs("Test", ["T-6"], ["repo"])
        fact = self._fact("data", cs["id"])
        violations = []

        for role_id, role_name in [
            (DEV, "developer"), (CODE_REV, "code-reviewer"),
            (SEC_REVIEWER, "security-reviewer"),
        ]:
            caught = False
            try:
                self.ledger.record_evidence(
                    role_id, run_id=RUN_ID, classification="DECISION",
                    content="Verified by machine", source_type="ci_result",
                    source="ci:test-run", change_set_id=cs["id"],
                    input_references=[fact["entry_id"]],
                    lifecycle_state="VERIFIED",
                )
            except PermissionDenied:
                caught = True
            violations.append({"role": role_name, "action": "set VERIFIED",
                               "caught": caught, "description": f"{role_name} set VERIFIED"})

        result = judge_permissions(violations)
        self.assertEqual(result["enforcement_rate"], 1.0,
                         f"VERIFIED not blocked for: {result['missed_details']}")


# =========================================================================
# Test 3: Security reviewer REJECT blocks the pipeline
# =========================================================================
class TestSecurityRejectBlocks(_MultiAgentBase):
    """When security-reviewer REJECTs, the change set should be BLOCKED."""

    def test_security_reject_blocks_change_set(self):
        """A security REJECT is a domain block — only a human can lift it."""
        cs = self._cs("Risky change", ["T-SEC-1"], ["repo"])
        cs_id = cs["id"]

        fact = self._fact("Hardcoded API key found in source", cs_id)

        # Security reviewer records finding and REJECTs
        self.ledger.record_evidence(
            SEC_REVIEWER, run_id=RUN_ID, classification="RISK",
            content="Hardcoded API key in config.ts. REJECT until remediated.",
            source_type="agent_analysis", change_set_id=cs_id,
            metadata={"impact": "HIGH", "mitigation": "Use environment variable"},
        )

        reject = self._handoff(SEC_REVIEWER, cs_id, "developer",
                               "Security REJECT: hardcoded API key", verdict="REJECT")
        self.assertIsNotNone(reject.get("escalated"),
                             "Security REJECT should escalate")

        cs_state = self.cm.get_change_set(DEV, cs_id)
        self.assertEqual(cs_state["status"], "BLOCKED",
                         "Security REJECT should BLOCK the change set")

        # Agent cannot unblock it
        with self.assertRaises(PermissionDenied):
            self.cm.update_status(DEV, change_set_id=cs_id,
                                  status="DRAFT", reason="trying to unblock")

        # Human CAN unblock it
        self.cm.update_status(HUMAN_LEAD, change_set_id=cs_id,
                              status="DRAFT", reason="Remediated, unblocking")
        cs_state = self.cm.get_change_set(DEV, cs_id)
        self.assertEqual(cs_state["status"], "DRAFT")


# =========================================================================
# Test 4: Handoff cycle limit triggers escalation
# =========================================================================
class TestHandoffCycleLimitEscalation(_MultiAgentBase):
    """After MAX_HANDOFF_CYCLES (3) rejections between the same pair, escalation fires."""

    def test_repeated_rejections_trigger_escalation(self):
        """3 rejections between code-reviewer and developer → BLOCKED."""
        cs = self._cs("Contentious PR", ["T-CYCLE-1"], ["repo"])
        cs_id = cs["id"]
        fact = self._fact("code with issues", cs_id)

        # 3 rejection cycles
        for i in range(3):
            self.ledger.record_evidence(
                CODE_REV, run_id=RUN_ID, classification="INFERENCE",
                content=f"Review round {i+1}: still has issues",
                source_type="agent_analysis", change_set_id=cs_id,
                input_references=[fact["entry_id"]],
            )
            result = self._handoff(CODE_REV, cs_id, "developer",
                                   f"REJECT round {i+1}", verdict="REJECT")

        # After 3 rejections, should be escalated/blocked
        cs_state = self.cm.get_change_set(DEV, cs_id)
        self.assertEqual(cs_state["status"], "BLOCKED",
                         "3 rejections should trigger escalation block")


# =========================================================================
# Test 5: Incident self-authorship prevention
# =========================================================================
class TestIncidentSelfAuthorshipBlocked(_MultiAgentBase):
    """The agent that failed cannot write the lesson about its own failure."""

    def test_developer_cannot_write_lesson_about_own_failure(self):
        """Developer's code produced the evidence → developer cannot write the lesson."""
        cs = self._cs("Test", ["T-SELF-1"], ["repo"])
        cs_id = cs["id"]

        # Developer writes evidence that later becomes the failure
        dev_evidence = self.ledger.record_evidence(
            DEV, run_id=RUN_ID, classification="INFERENCE",
            content="Implementation is correct",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[self._fact("test data", cs_id)["entry_id"]],
        )

        # Code reviewer records incident pointing at developer's evidence
        incident = self.ledger.record_incident(
            CODE_REV, skill="evidence-gate", step="review",
            failure_class="INCORRECT_BEHAVIOR",
            signal_type="negative", signal_source="REVIEWER",
            pattern_eligible=True,
            evidence_refs=[dev_evidence["entry_id"]],
        )

        # Developer tries to write the lesson — should be blocked
        with self.assertRaises(PermissionDenied) as ctx:
            self.ledger.record_lesson(
                DEV,
                skill="evidence-gate", step="review",
                failure_class="INCORRECT_BEHAVIOR",
                occurrences={"incidents": 1, "change_sets": 1, "projects": 1},
                what_failed="Implementation was incorrect",
                advice="Review more carefully",
                remedy_kind="SKILL_TEXT",
                incident_refs=[incident["incident_id"]],
                sanitization_result={"passed": True, "checker_version": "1.0",
                                     "checked_at": "2026-10-04T12:00:00Z"},
            )
        self.assertIn("failed", str(ctx.exception).lower())

        # Code reviewer CAN write the lesson (different role)
        lesson = self.ledger.record_lesson(
            CODE_REV,
            skill="evidence-gate", step="review",
            failure_class="INCORRECT_BEHAVIOR",
            occurrences={"incidents": 1, "change_sets": 1, "projects": 1},
            what_failed="Implementation was incorrect",
            advice="Review more carefully",
            remedy_kind="SKILL_TEXT",
            incident_refs=[incident["incident_id"]],
            sanitization_result={"passed": True, "checker_version": "1.0",
                                 "checked_at": "2026-10-04T12:00:00Z"},
        )
        self.assertTrue(lesson["lesson_id"].startswith("LES-"))


# =========================================================================
# Test 6: Cross-role evidence chain integrity
# =========================================================================
class TestCrossRoleEvidenceChain(_MultiAgentBase):
    """Evidence produced by one role should be properly referenceable by another."""

    def test_chain_spans_all_roles(self):
        """Build an evidence chain that spans PO → architect → dev → qa-diagnose
        and verify every link is traceable."""
        cs = self._cs("Cross-role chain", ["T-CHAIN-1"], ["repo"])
        cs_id = cs["id"]

        # SYSTEM fact (hook)
        f = self._fact("requirement document received", cs_id)

        # PO → intent
        po = self.ledger.record_evidence(
            PRODUCT_OWNER, run_id=RUN_ID, classification="DECISION",
            content="Requirement accepted, P1 priority",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[f["entry_id"]], lifecycle_state="PROPOSED",
        )

        # Architect → design referencing PO's decision
        arch = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="DECISION",
            content="Microservice architecture chosen",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[po["entry_id"]], lifecycle_state="PROPOSED",
        )

        # Developer → implementation referencing architect's design
        dev = self.ledger.record_evidence(
            DEV, run_id=RUN_ID, classification="INFERENCE",
            content="Implemented per architecture spec",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[arch["entry_id"]],
        )

        # QA-diagnose → analysis referencing developer's impl
        qa = self.ledger.record_evidence(
            QA_DIAGNOSE, run_id=RUN_ID, classification="INFERENCE",
            content="All tests pass, no issues found",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[dev["entry_id"]],
        )

        # Walk the chain backwards from QA to FACT
        chain = []
        current = qa
        seen = set()
        while current and current["entry_id"] not in seen:
            chain.append((current["agent_role"] or "SYSTEM", current["classification"]))
            seen.add(current["entry_id"])
            refs = json.loads(current["input_references"]) if isinstance(
                current["input_references"], str) else (current["input_references"] or [])
            if refs:
                current = self.ledger.get_entry(refs[0])
            else:
                break

        expected_chain = [
            ("qa-diagnose", "INFERENCE"),
            ("developer", "INFERENCE"),
            ("architect", "DECISION"),
            ("product-owner", "DECISION"),
            ("SYSTEM", "FACT"),  # SYSTEM agent_role is None → fallback "SYSTEM"
        ]

        self.assertEqual(len(chain), 5, f"Chain should be 5 deep, got {chain}")
        for i, (actual, expected) in enumerate(zip(chain, expected_chain)):
            self.assertEqual(actual[0], expected[0],
                             f"Chain step {i}: expected role {expected[0]}, got {actual[0]}")
            self.assertEqual(actual[1], expected[1],
                             f"Chain step {i}: expected class {expected[1]}, got {actual[1]}")


# =========================================================================
# Test 7: Judge summary across all tests
# =========================================================================
class TestJudgeSummary(_MultiAgentBase):
    """Final judge: are multi-agent delegation and role enforcement working?"""

    def test_all_9_roles_have_valid_identities(self):
        """Every AGENT_ROLE in vocab.py can be instantiated as a valid Identity."""
        from adlc_mcp.kernel.vocab import AGENT_ROLES
        for role in AGENT_ROLES:
            ident = Identity("AGENT", f"agent:{role}", agent_role=role,
                             tool="claude-code", model_id="opus-4")
            self.assertEqual(ident.agent_role, role)
            self.assertTrue(ident.is_agent)
            self.assertFalse(ident.is_human)
            self.assertFalse(ident.is_system)

    def test_invalid_role_rejected_at_identity_creation(self):
        """An unknown agent_role is rejected — you can't invent roles."""
        from adlc_mcp.kernel.errors import AuthError
        with self.assertRaises(AuthError):
            Identity("AGENT", "agent:hacker", agent_role="hacker",
                     tool="claude-code", model_id="opus-4")

    def test_agent_identity_requires_model_id(self):
        """AGENT evidence requires model_id — every agent must declare its model."""
        cs = self._cs("Test", ["T-MODEL-1"], ["repo"])
        fact = self._fact("data", cs["id"])

        no_model = Identity("AGENT", "agent:dev-nomodel", agent_role="developer",
                            tool="claude-code")  # no model_id

        with self.assertRaises(ValidationError) as ctx:
            self.ledger.record_evidence(
                no_model, run_id=RUN_ID, classification="INFERENCE",
                content="Analysis", source_type="agent_analysis",
                change_set_id=cs["id"], input_references=[fact["entry_id"]],
            )
        self.assertIn("model_id", str(ctx.exception))


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")
    unittest.main()
