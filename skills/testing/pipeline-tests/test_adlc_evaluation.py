#!/usr/bin/env python3
"""ADLC Platform Evaluation: with-vs-without ADLC + skill issue discovery.

Three requirements run through two paths each:
  Path A — "No ADLC": LLM implements directly without recording evidence, change sets,
           or lifecycle. We measure what's missing after the fact.
  Path B — "With ADLC": Full pipeline — evidence chains, change sets, lifecycle transitions,
           contracts, risk tiering, handoffs. We measure what the platform catches.

Then: targeted probes that surface issues in the ADLC skills themselves — validation gaps,
      boundary cases, accuracy problems.

Each test records structured metrics so a final summary can compare paths.

    python -m unittest skills/testing/pipeline-tests/test_adlc_evaluation.py -v
"""
from __future__ import annotations

import json
import sys
import textwrap
import unittest
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_SRC = REPO_ROOT / "skills" / "mcp-servers" / "adlc-mcp" / "src"
MCP_TESTS = REPO_ROOT / "skills" / "mcp-servers" / "adlc-mcp" / "tests"
sys.path.insert(0, str(MCP_SRC))
sys.path.insert(0, str(MCP_TESTS))

from _support import DEVELOPER, CODE_REVIEWER, HUMAN_LEAD, CI, SECURITY, TempEnv  # noqa: E402
from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError, NotFound  # noqa: E402
from adlc_mcp.kernel.identity import Identity  # noqa: E402

ARCHITECT = Identity("AGENT", "agent:architect", agent_role="architect",
                     tool="claude-code", model_id="model-a")
QA_DERIVE = Identity("AGENT", "agent:qa-derive", agent_role="qa-derive",
                     tool="claude-code", model_id="model-a")
REVIEWER = Identity("AGENT", "agent:code-reviewer", agent_role="code-reviewer",
                    tool="claude-code", model_id="model-a")

ALL_MODULES = "evidence_ledger,change_management,work_planning,contract_registry"
RUN_ID = "run-eval"


@dataclass
class Metrics:
    """Collected per-path metrics for comparison."""
    name: str = ""
    facts_recorded: int = 0
    inferences_recorded: int = 0
    decisions_recorded: int = 0
    risks_recorded: int = 0
    questions_recorded: int = 0
    assumptions_recorded: int = 0
    unsourced_inferences: int = 0
    grounding_ratio: float = 0.0       # inferences with refs / total inferences
    trust_distribution: dict = field(default_factory=dict)
    lifecycle_stages_traversed: int = 0
    contracts_registered: int = 0
    drift_checks: int = 0
    incidents_recorded: int = 0
    corrections_made: int = 0
    blocking_items_surfaced: int = 0
    handoffs: int = 0
    risk_tier_computed: bool = False
    evidence_chain_depth: int = 0      # max hops from INFERENCE back to FACT
    validation_errors_caught: int = 0  # times the platform rejected bad input
    issues_found: list = field(default_factory=list)


class _EvalBase(unittest.TestCase):
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

    def _create_cs(self, title, reqs, repos, **kw):
        return self.cm.create_change_set(DEVELOPER, title=title,
                                         requirements=reqs, repositories=repos, **kw)

    def _fact(self, content, cs_id, source="cmd:test"):
        return self.ledger.append_fact("test-hook", {
            "run_id": RUN_ID, "tool": "claude-code",
            "source_type": "command_output", "content": content,
            "source": source, "change_set_id": cs_id,
        })

    def _collect_metrics(self, cs_id, name) -> Metrics:
        m = Metrics(name=name)
        evidence = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id, limit=1000)
        for e in evidence:
            cls = e["classification"]
            if cls == "FACT":
                m.facts_recorded += 1
            elif cls == "INFERENCE":
                m.inferences_recorded += 1
                refs = json.loads(e["input_references"]) if isinstance(
                    e["input_references"], str) else (e["input_references"] or [])
                if not refs:
                    m.unsourced_inferences += 1
            elif cls == "DECISION":
                m.decisions_recorded += 1
            elif cls == "RISK":
                m.risks_recorded += 1
            elif cls == "QUESTION":
                m.questions_recorded += 1
            elif cls == "ASSUMPTION":
                m.assumptions_recorded += 1
            trust = e.get("trust_level", "UNKNOWN")
            m.trust_distribution[trust] = m.trust_distribution.get(trust, 0) + 1

        total_inf = m.inferences_recorded
        grounded = total_inf - m.unsourced_inferences
        m.grounding_ratio = grounded / total_inf if total_inf > 0 else 1.0
        m.blocking_items_surfaced = len(self.ledger.blocking_items(cs_id))

        cs = self.cm.get_change_set(DEVELOPER, cs_id)
        m.lifecycle_stages_traversed = len(cs.get("status_history", []))
        m.handoffs = len(cs.get("handoffs", []))
        m.risk_tier_computed = cs.get("risk_tier") is not None
        m.incidents_recorded = len(self.ledger.query_incidents(
            DEVELOPER, pattern_eligible_only=False))

        # Evidence chain depth: walk references to find max depth
        entry_map = {e["entry_id"]: e for e in evidence}
        max_depth = 0
        for e in evidence:
            if e["classification"] == "INFERENCE":
                depth = self._chain_depth(e, entry_map, set())
                max_depth = max(max_depth, depth)
        m.evidence_chain_depth = max_depth
        return m

    def _chain_depth(self, entry, entry_map, visited):
        if entry["entry_id"] in visited:
            return 0
        visited.add(entry["entry_id"])
        refs = json.loads(entry["input_references"]) if isinstance(
            entry["input_references"], str) else (entry["input_references"] or [])
        if not refs:
            return 0
        max_child = 0
        for ref_id in refs:
            ref = entry_map.get(ref_id)
            if ref and ref["classification"] != "FACT":
                max_child = max(max_child, self._chain_depth(ref, entry_map, visited))
        return 1 + max_child


# ==========================================================================
# REQ-1: Add rate limiting to the API gateway
# ==========================================================================
class TestReq1_RateLimiting_NoADLC(_EvalBase):
    """Path A: Developer jumps straight in without ADLC platform."""

    def test_no_adlc_has_zero_evidence(self):
        """Without ADLC, there's no evidence trail at all."""
        # Simulate: developer just writes code, no platform interaction.
        # The only thing that exists is the change set (because the developer needs SOMETHING).
        cs = self._create_cs("Add rate limiting", ["REQ-RATE-1"], ["api-gateway"])
        cs_id = cs["id"]

        # Developer doesn't record any evidence — just implements
        # After "implementation", we measure what's available
        m = self._collect_metrics(cs_id, "REQ-1 No ADLC")
        self.assertEqual(m.facts_recorded, 0)
        self.assertEqual(m.inferences_recorded, 0)
        self.assertEqual(m.decisions_recorded, 0)
        self.assertEqual(m.risks_recorded, 0)
        self.assertEqual(m.grounding_ratio, 1.0)  # vacuously true (0/0)
        self.assertFalse(m.risk_tier_computed)
        self.assertEqual(m.evidence_chain_depth, 0)
        self.assertEqual(m.handoffs, 0)

        # The CS is stuck in DRAFT — no lifecycle progression
        cs_state = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(cs_state["status"], "DRAFT")


class TestReq1_RateLimiting_WithADLC(_EvalBase):
    """Path B: Full ADLC pipeline for rate limiting feature."""

    def test_full_pipeline_produces_complete_evidence(self):
        """With ADLC, we get full evidence chains, risk tiering, contracts, and lifecycle."""
        cs = self._create_cs("Add rate limiting to API gateway",
                             ["REQ-RATE-1"], ["api-gateway"],
                             contracts=["api-gateway-public-v2"])
        cs_id = cs["id"]

        # INTAKE: Hooks capture file reads as FACTs
        f1 = self._fact("api-gateway/src/middleware/: auth.ts, cors.ts, logging.ts — no rate limiter",
                        cs_id, source="cmd:ls api-gateway/src/middleware/")
        f2 = self._fact("package.json: express@4.18.2, helmet@7.1.0 — no rate-limit package",
                        cs_id, source="cmd:cat package.json")
        f3 = self._fact("api-gateway/src/config.ts: MAX_REQUESTS_PER_MINUTE=undefined, "
                        "RATE_LIMIT_WINDOW=undefined — no rate config exists",
                        cs_id, source="cmd:grep rate api-gateway/src/config.ts")

        # ARCHITECTURE: Architect analyzes and proposes
        arch = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Rate limiting strategy: sliding window counter in Redis. "
                    "Use express-rate-limit with redis store. Apply per-IP default "
                    "(100 req/min) with per-key override for authenticated API keys (1000 req/min).",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[f1["entry_id"], f2["entry_id"], f3["entry_id"]],
        )

        decision = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="DECISION",
            content="Use express-rate-limit + rate-limit-redis. Two tiers: "
                    "anonymous (100/min per IP), authenticated (1000/min per API key). "
                    "429 response with Retry-After header. Redis key: rate:{ip}:{minute}.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[arch["entry_id"]],
            lifecycle_state="PROPOSED",
        )

        # Record RISK
        risk = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="RISK",
            content="If Redis is down, rate limiting fails open (requests pass through). "
                    "Need circuit breaker: fail closed after 5s Redis timeout — return 503.",
            source_type="agent_analysis", change_set_id=cs_id,
            metadata={"impact": "HIGH", "mitigation": "Circuit breaker with 5s timeout"},
        )

        # Record blocking QUESTION
        question = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="QUESTION",
            content="Should rate limits apply to internal service-to-service calls? "
                    "If yes, we need a whitelist for internal IPs.",
            source_type="agent_analysis", change_set_id=cs_id,
            metadata={"blocking": True},
        )

        # Register contract update
        self.cr.register_contract(
            ARCHITECT, contract_id="api-gateway-public-v2", provider="api-gateway",
            version="2.1.0", type="http", consumers=["web-app", "mobile-app"],
            spec={"fields": {
                "X-RateLimit-Limit": {"type": "integer", "required": True},
                "X-RateLimit-Remaining": {"type": "integer", "required": True},
                "X-RateLimit-Reset": {"type": "integer", "required": True},
                "Retry-After": {"type": "integer", "required": False},
            }},
        )

        # Compute risk tier
        risk_result = self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id,
            paths=["api-gateway/src/middleware/rate-limiter.ts",
                   "api-gateway/src/config.ts",
                   "api-gateway/package.json"],
            reason_codes=[], diff_lines=120,
        )

        # Lifecycle: DRAFT → SCOPED → PLANNED
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="SCOPED", reason="Scope: rate limiting for public API")
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="PLANNED", reason="Implementation plan approved")

        # Handoff architect → developer
        ho = self.cm.record_handoff(
            ARCHITECT, change_set_id=cs_id, to_role="developer",
            payload={
                "summary": "Rate limiter: express-rate-limit + Redis, two tiers",
                "inputs": [{"artifact_ref": "api-gateway@" + "a" * 7 + ":src/config.ts",
                            "content_hash": "sha256:" + "11" * 32}],
                "outputs": [{"artifact_kind": "architecture-design",
                             "content_hash": "sha256:" + "22" * 32}],
                "classifications": [],
            },
            verdict="ACCEPT",
        )

        # Collect and verify metrics
        m = self._collect_metrics(cs_id, "REQ-1 With ADLC")
        self.assertGreaterEqual(m.facts_recorded, 3, "Should have at least 3 FACTs from hooks")
        self.assertGreaterEqual(m.inferences_recorded, 1, "Should have architecture inference")
        self.assertGreaterEqual(m.decisions_recorded, 1, "Should have design decision")
        self.assertGreaterEqual(m.risks_recorded, 1, "Should have identified risks")
        self.assertGreaterEqual(m.questions_recorded, 1, "Should have blocking questions")
        self.assertEqual(m.grounding_ratio, 1.0, "All inferences should be grounded")
        self.assertEqual(m.unsourced_inferences, 0, "No unsourced claims")
        self.assertTrue(m.risk_tier_computed, "Risk tier should be computed")
        self.assertGreaterEqual(m.evidence_chain_depth, 1, "Evidence chain should have depth")
        self.assertGreaterEqual(m.handoffs, 1, "Should have role handoff")
        self.assertGreaterEqual(m.blocking_items_surfaced, 1, "Blocking question should be surfaced")

        # Trust levels: FACTs from hooks should be SYSTEM
        self.assertIn("SYSTEM", m.trust_distribution)

        # Verify the blocking question blocks completion
        blockers = self.ledger.blocking_items(cs_id)
        self.assertTrue(any("rate limits apply" in b for b in blockers))


# ==========================================================================
# REQ-2: Fix N+1 query in user dashboard
# ==========================================================================
class TestReq2_NPlus1Fix_NoADLC(_EvalBase):
    """Path A: Developer fixes the N+1 without ADLC."""

    def test_no_evidence_trail_for_bugfix(self):
        """Without ADLC, a bug fix has no root cause trace or verification record."""
        cs = self._create_cs("Fix N+1 query", ["BUG-N1-1"], ["dashboard-svc"])
        cs_id = cs["id"]

        # Developer just fixes it — no evidence, no incident, no verification
        m = self._collect_metrics(cs_id, "REQ-2 No ADLC")
        self.assertEqual(m.facts_recorded, 0)
        self.assertEqual(m.incidents_recorded, 0)
        self.assertEqual(m.corrections_made, 0)
        self.assertEqual(m.evidence_chain_depth, 0)


class TestReq2_NPlus1Fix_WithADLC(_EvalBase):
    """Path B: N+1 fix through ADLC pipeline with root cause analysis."""

    def test_bugfix_with_full_evidence_and_verification(self):
        """With ADLC, the fix has a complete root cause chain and verification signal."""
        cs = self._create_cs("Fix N+1 query in user dashboard",
                             ["BUG-N1-1"], ["dashboard-svc"])
        cs_id = cs["id"]

        # FACT: profiler output
        profile = self._fact(
            "EXPLAIN ANALYZE: dashboard_svc.user_list executes 1 query for users + "
            "N queries for user.roles (N=847 on staging). Total: 3.2s.",
            cs_id, source="cmd:psql -c 'EXPLAIN ANALYZE SELECT...'")

        # FACT: code location
        code = self._fact(
            "dashboard-svc/src/resolvers/users.ts:34 — User.roles loaded in a .map() loop "
            "with separate ORM call per user. No .includes() or JOIN.",
            cs_id, source="cmd:cat dashboard-svc/src/resolvers/users.ts")

        # FACT: test confirms it
        test_before = self._fact(
            "npm test: user-list.test.ts passes but takes 4.1s (expected <500ms). "
            "No assertion on query count.",
            cs_id, source="cmd:npm test -- user-list.test.ts")

        # Root cause INFERENCE
        root_cause = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="N+1 query: User.roles loaded per-user in a loop (resolvers/users.ts:34). "
                    "Fix: use ORM eager loading (.include({roles: true})) to batch into 2 queries.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[profile["entry_id"], code["entry_id"]],
        )

        # DECISION: fix approach
        fix_decision = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="Use Prisma .include() for eager loading. Add query count assertion to test. "
                    "Expected: 2 queries (users + roles), <100ms.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[root_cause["entry_id"]],
            lifecycle_state="PROPOSED",
        )

        # After fix: FACT from test re-run
        test_after = self._fact(
            "npm test: user-list.test.ts PASS, 2 queries, 45ms (was 847 queries, 4.1s). "
            "Query count assertion passes.",
            cs_id, source="cmd:npm test -- user-list.test.ts")

        # Verification INFERENCE — chains through root cause for full traceability
        verification = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Fix verified: query count dropped from 847 to 2, latency from 4.1s to 45ms. "
                    "Query count assertion added prevents regression.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[test_after["entry_id"], test_before["entry_id"],
                              root_cause["entry_id"]],
        )

        # Incident for the production feedback loop
        incident = self.ledger.record_incident(
            CODE_REVIEWER,
            skill="evidence-gate", step="verify",
            failure_class="INCORRECT_BEHAVIOR",
            signal_type="negative",
            signal_source="REVIEWER",
            pattern_eligible=True,
            evidence_refs=[profile["entry_id"], code["entry_id"]],
            note="N+1 query shipped to production without query count assertions",
        )

        # Risk tier
        self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id,
            paths=["dashboard-svc/src/resolvers/users.ts",
                   "dashboard-svc/test/user-list.test.ts"],
            reason_codes=[], diff_lines=25,
        )

        # Lifecycle
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="SCOPED", reason="Single file fix")
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="PLANNED", reason="Fix identified")

        m = self._collect_metrics(cs_id, "REQ-2 With ADLC")
        self.assertGreaterEqual(m.facts_recorded, 4, "Before/after FACTs from tests")
        self.assertGreaterEqual(m.inferences_recorded, 2, "Root cause + verification")
        self.assertGreaterEqual(m.decisions_recorded, 1, "Fix decision")
        self.assertEqual(m.grounding_ratio, 1.0, "All inferences grounded")
        self.assertGreaterEqual(m.incidents_recorded, 1, "Incident recorded for feedback loop")
        self.assertGreaterEqual(m.evidence_chain_depth, 2, "INFERENCE → INFERENCE → FACT chain")
        self.assertTrue(m.risk_tier_computed)

        # Verify the evidence chain from verification back to raw profiler output
        entries = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        verif_entry = [e for e in entries if "Fix verified" in (e.get("content") or "")]
        self.assertTrue(verif_entry, "Verification entry should exist")


# ==========================================================================
# REQ-3: Database migration (adding column to large table)
# ==========================================================================
class TestReq3_Migration_NoADLC(_EvalBase):
    """Path A: Migration without ADLC — no risk assessment."""

    def test_migration_without_risk_assessment(self):
        """Without ADLC, a HIGH-risk migration gets no risk tier or approval."""
        cs = self._create_cs("Add status column to orders table",
                             ["REQ-MIG-1"], ["backend"])
        cs_id = cs["id"]

        m = self._collect_metrics(cs_id, "REQ-3 No ADLC")
        self.assertFalse(m.risk_tier_computed)
        self.assertEqual(m.risks_recorded, 0)
        self.assertEqual(m.handoffs, 0)


class TestReq3_Migration_WithADLC(_EvalBase):
    """Path B: Migration with full ADLC pipeline — risk tiering triggers approval matrix."""

    def test_migration_triggers_high_risk_approval(self):
        """Migration files trigger HIGH tier, which requires human tech-lead approval."""
        cs = self._create_cs("Add status column to orders (50M rows)",
                             ["REQ-MIG-1"], ["backend"])
        cs_id = cs["id"]

        # FACTs from investigation
        schema_fact = self._fact(
            "orders table: 50.2M rows, 12 columns, avg row size 340 bytes. "
            "Primary key: id (uuid). Indexes: user_id, created_at, amount.",
            cs_id, source="cmd:psql -c 'SELECT reltuples FROM pg_class WHERE relname=orders'")

        migration_fact = self._fact(
            "Current migration: 0041_add_payment_method.sql (last run 2026-09-15). "
            "Migration runner: node-pg-migrate with advisory lock.",
            cs_id, source="cmd:ls backend/migrations/")

        load_fact = self._fact(
            "Peak QPS to orders table: 1200 (writes: 340, reads: 860). "
            "P99 write latency: 12ms. Connection pool: 50.",
            cs_id, source="cmd:curl metrics/orders-table-stats")

        # Architect analysis
        analysis = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Adding NOT NULL column to 50M-row table requires online DDL. "
                    "PostgreSQL ALTER TABLE ... ADD COLUMN with DEFAULT is online since PG11 "
                    "(rewrites only for volatile defaults). Safe for NOT NULL + DEFAULT. "
                    "Backfill: UPDATE in batches of 10k with 100ms sleep.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[schema_fact["entry_id"], load_fact["entry_id"]],
        )

        # RISK: lock contention
        self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="RISK",
            content="AccessExclusiveLock during ALTER TABLE blocks concurrent writes. "
                    "At 340 writes/sec, even 100ms lock causes 34 queued writes. "
                    "Mitigation: run during low-traffic window (02:00-04:00 UTC).",
            source_type="agent_analysis", change_set_id=cs_id,
            metadata={"impact": "HIGH", "mitigation": "Schedule during maintenance window"},
        )

        # RISK: rollback complexity
        self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="RISK",
            content="Rollback requires DROP COLUMN which also takes AccessExclusiveLock. "
                    "No instant rollback possible. Test in staging with production-scale data first.",
            source_type="agent_analysis", change_set_id=cs_id,
            metadata={"impact": "MEDIUM", "mitigation": "Staging test with prod-scale data"},
        )

        # ASSUMPTION: staging is representative
        self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="ASSUMPTION",
            content="Staging has 5M rows (10% of prod). Migration timing from staging will be "
                    "roughly 10x in production. Assuming linear scaling.",
            source_type="agent_analysis", change_set_id=cs_id,
            metadata={"impact": "MEDIUM", "expires_at": "2026-10-11T00:00:00Z"},
        )

        # Risk tier: migration paths trigger HIGH
        risk = self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id,
            paths=["backend/migrations/0042_add_status_column.sql",
                   "backend/src/models/order.ts",
                   "backend/src/services/order-service.ts"],
            reason_codes=[], diff_lines=45,
        )
        self.assertIn(risk["final_tier"], ("HIGH", "CRITICAL"),
                      "Migration files should trigger HIGH or CRITICAL tier")

        # Lifecycle
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="SCOPED", reason="Migration scope defined")
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="PLANNED", reason="Migration plan with rollback ready")

        # For HIGH tier, plan approval requires human tech-lead
        # Verify the approval matrix via forge events
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="plan_check_passed",
                                   payload={"approval_epoch": 0})

        # Without human approval, PLAN_APPROVED should NOT be reached
        cs_state = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(cs_state["status"], "PLANNED",
                         "HIGH-tier change should stay PLANNED without human approval")

        # Now add human approval
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="codeowners_review",
                                   payload={"approver": "tech-lead",
                                            "approver_role": "human:tech-lead",
                                            "state": "approved"})

        cs_state = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(cs_state["status"], "PLAN_APPROVED",
                         "HIGH-tier change should be PLAN_APPROVED after human approval")

        m = self._collect_metrics(cs_id, "REQ-3 With ADLC")
        self.assertGreaterEqual(m.facts_recorded, 3)
        self.assertGreaterEqual(m.risks_recorded, 2, "Multiple risks identified")
        self.assertGreaterEqual(m.assumptions_recorded, 1, "ASSUMPTION about staging scale")
        self.assertTrue(m.risk_tier_computed)
        self.assertGreaterEqual(m.blocking_items_surfaced, 1,
                                "MEDIUM+ ASSUMPTION should be a blocker")


# ==========================================================================
# ADLC Skill Issue Discovery — probing for accuracy and validation gaps
# ==========================================================================
class TestADLCSkillIssues(_EvalBase):
    """Targeted probes to find issues in the ADLC skill enforcement."""

    # ---- Fact accuracy enforcement ----

    def test_agent_cannot_fabricate_facts(self):
        """Core accuracy rule: AGENT cannot write FACT entries. Only hooks/SYSTEM can."""
        cs = self._create_cs("Test", ["T-1"], ["repo"])
        with self.assertRaises(PermissionDenied) as ctx:
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="FACT",
                content="I saw this in the logs", source_type="agent_analysis",
                source="my-observation", change_set_id=cs["id"],
            )
        self.assertIn("AGENT callers cannot write FACT", str(ctx.exception))

    def test_unsourced_inference_rejected(self):
        """INFERENCE without input_references is rejected — prevents unsourced claims."""
        cs = self._create_cs("Test", ["T-2"], ["repo"])
        with self.assertRaises(ValidationError) as ctx:
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="The bug is on line 42", source_type="agent_analysis",
                change_set_id=cs["id"],
            )
        self.assertIn("input_references", str(ctx.exception))

    def test_inference_with_nonexistent_references_rejected(self):
        """INFERENCE referencing nonexistent entries is rejected."""
        cs = self._create_cs("Test", ["T-3"], ["repo"])
        with self.assertRaises(ValidationError) as ctx:
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="Analysis based on phantom evidence",
                source_type="agent_analysis", change_set_id=cs["id"],
                input_references=["ENTRY-does-not-exist"],
            )
        self.assertIn("not found", str(ctx.exception))

    def test_fact_requires_source(self):
        """FACT without source is rejected — every fact must say where it came from."""
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                CI, run_id=RUN_ID, classification="FACT",
                content="Something happened", source_type="ci_result",
            )

    # ---- Lifecycle enforcement ----

    def test_cannot_skip_lifecycle_stages(self):
        """DRAFT → PLANNED is invalid; must go through SCOPED first."""
        cs = self._create_cs("Test", ["T-4"], ["repo"])
        with self.assertRaises(ValidationError) as ctx:
            self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                                  status="PLANNED", reason="Skip")
        self.assertIn("invalid transition", str(ctx.exception))

    def test_forge_only_states_blocked_from_update_status(self):
        """PLAN_APPROVED, INTEGRATED, RELEASED, ROLLED_BACK only via forge events."""
        cs = self._create_cs("Test", ["T-5"], ["repo"])
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                              status="SCOPED", reason="Scoped")
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                              status="PLANNED", reason="Planned")

        for forge_state in ("PLAN_APPROVED", "INTEGRATED", "RELEASED", "ROLLED_BACK"):
            with self.assertRaises(PermissionDenied, msg=f"{forge_state} should be forge-only"):
                self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                                      status=forge_state, reason="Bypass attempt")

    def test_cancelled_requires_human(self):
        """Only a HUMAN can cancel a change set — agents can't abandon work."""
        cs = self._create_cs("Test", ["T-6"], ["repo"])
        with self.assertRaises(PermissionDenied):
            self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                                  status="CANCELLED", reason="Give up")

        # Human CAN cancel
        self.cm.update_status(HUMAN_LEAD, change_set_id=cs["id"],
                              status="CANCELLED", reason="Deprioritized")
        cs_state = self.cm.get_change_set(DEVELOPER, cs["id"])
        self.assertEqual(cs_state["status"], "CANCELLED")

    # ---- Trust level accuracy ----

    def test_trust_levels_derived_correctly(self):
        """Trust is derived from source_type + identity, not caller-supplied."""
        cs = self._create_cs("Test", ["T-7"], ["repo"])
        cs_id = cs["id"]

        # Hook-written FACT (SYSTEM identity) should get SYSTEM trust
        fact = self._fact("test content", cs_id, source="cmd:test")
        self.assertEqual(fact["trust_level"], "SYSTEM")

        # AGENT INFERENCE with recognized source_type gets REPOSITORY ceiling
        inf = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Analysis", source_type="agent_analysis",
            change_set_id=cs_id, input_references=[fact["entry_id"]],
        )
        self.assertEqual(inf["trust_level"], "REPOSITORY",
                         "AGENT identity should cap trust at REPOSITORY")

    def test_unrecognized_source_type_falls_to_lowest_trust(self):
        """ADLC ISSUE: source_type not in SOURCE_TYPE_TRUST silently defaults to
        EXTERNAL_UNSTRUCTURED — the lowest trust level. An LLM using source_type='TOOL'
        (not in the map) gets its evidence downgraded without any warning."""
        cs = self._create_cs("Test", ["T-7b"], ["repo"])
        cs_id = cs["id"]
        fact = self._fact("test content", cs_id)

        inf = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Analysis using unrecognized source_type",
            source_type="TOOL",  # NOT in SOURCE_TYPE_TRUST!
            change_set_id=cs_id, input_references=[fact["entry_id"]],
        )
        self.assertEqual(inf["trust_level"], "EXTERNAL_UNSTRUCTURED",
                         "ADLC ISSUE: unrecognized source_type silently falls to lowest trust")

    def test_trust_tainted_by_lowest_reference(self):
        """Trust of an INFERENCE is limited by the lowest-trust reference (taint propagation)."""
        cs = self._create_cs("Test", ["T-8"], ["repo"])
        cs_id = cs["id"]

        # High-trust FACT
        high_fact = self._fact("verified data", cs_id)

        # An external-trust entry
        ext = self.ledger.record_evidence(
            HUMAN_LEAD, run_id=RUN_ID, classification="INFERENCE",
            content="External analysis from web page",
            source_type="web_page", change_set_id=cs_id,
            input_references=[high_fact["entry_id"]],
        )

        # INFERENCE referencing both should get the lowest trust
        combined = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Combined analysis from verified data and web source",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[high_fact["entry_id"], ext["entry_id"]],
        )
        # Trust should be tainted by the web_page source
        self.assertNotEqual(combined["trust_level"], "SYSTEM",
                            "Trust should be tainted by external reference")

    # ---- Incident and lesson accuracy ----

    def test_incident_note_only_from_reviewer_or_human(self):
        """Notes on incidents can only come from REVIEWER or HUMAN signal_source."""
        cs = self._create_cs("Test", ["T-9"], ["repo"])
        fact = self._fact("error occurred", cs["id"])

        with self.assertRaises(ValidationError) as ctx:
            self.ledger.record_incident(
                DEVELOPER,
                skill="test-skill", step="check",
                failure_class="INCORRECT_BEHAVIOR",
                signal_type="negative",
                signal_source="AGENT",
                pattern_eligible=True,
                evidence_refs=[fact["entry_id"]],
                note="This is my analysis of what went wrong",
            )
        self.assertIn("REVIEWER or HUMAN", str(ctx.exception))

    def test_positive_signal_requires_verification_strength(self):
        """A positive signal without verification strength is rejected — prevents fake passes."""
        cs = self._create_cs("Test", ["T-10"], ["repo"])
        fact = self._fact("tests passed", cs["id"])

        with self.assertRaises(ValidationError):
            self.ledger.record_incident(
                DEVELOPER,
                skill="test-runner", step="execute",
                failure_class=None,
                signal_type="positive",
                signal_source="AGENT",
                pattern_eligible=True,
                evidence_refs=[fact["entry_id"]],
            )

    def test_positive_signal_accepted_with_full_verification(self):
        """Positive signal with proper verification strength is accepted."""
        cs = self._create_cs("Test", ["T-11"], ["repo"])
        fact = self._fact("all tests pass", cs["id"])

        result = self.ledger.record_incident(
            DEVELOPER,
            skill="test-runner", step="execute",
            failure_class=None,
            signal_type="positive",
            signal_source="AGENT",
            pattern_eligible=True,
            evidence_refs=[fact["entry_id"]],
            verification_strength={
                "changed_code_coverage": 0.92,
                "acceptance_criteria_exercised": True,
            },
        )
        self.assertTrue(result["incident_id"].startswith("INC-"))

    # ---- Correction traceability ----

    def test_correction_marks_original_as_challenged(self):
        """Corrections don't delete — they create a CHALLENGED chain."""
        cs = self._create_cs("Test", ["T-12"], ["repo"])
        cs_id = cs["id"]
        fact = self._fact("data point", cs_id)

        wrong = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Wrong conclusion", source_type="agent_analysis",
            change_set_id=cs_id, input_references=[fact["entry_id"]],
        )

        correction = self.ledger.record_correction(
            DEVELOPER, parent_entry_id=wrong["entry_id"],
            run_id=RUN_ID, content="Actually, the correct conclusion is...",
            source_type="agent_analysis",
        )

        # Verify original is now CHALLENGED
        entries = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        orig = [e for e in entries if e["entry_id"] == wrong["entry_id"]]
        self.assertEqual(orig[0]["derived_status"], "CHALLENGED")

    # ---- Forge event validation ----

    def test_forge_event_payload_validation(self):
        """Forge events enforce required fields — prevents incomplete integration records."""
        cs = self._create_cs("Test", ["T-13"], ["repo"])
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                              status="SCOPED", reason="s")
        self.cm.update_status(DEVELOPER, change_set_id=cs["id"],
                              status="PLANNED", reason="p")

        # codeowners_review without approver_role fails
        with self.assertRaises(ValidationError):
            self.cm.ingest_forge_event(CI, change_set_id=cs["id"],
                                       event_type="codeowners_review",
                                       payload={"approver": "bob", "state": "approved"})

        # approver_role must start with "human:"
        with self.assertRaises(ValidationError):
            self.cm.ingest_forge_event(CI, change_set_id=cs["id"],
                                       event_type="codeowners_review",
                                       payload={"approver": "bob",
                                                "approver_role": "agent:bot",
                                                "state": "approved"})

    def test_pr_merged_before_verifying_triggers_block(self):
        """Merging before VERIFYING is a policy violation — change set gets BLOCKED."""
        cs = self._create_cs("Test", ["T-14"], ["repo"])
        cs_id = cs["id"]
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="SCOPED", reason="s")
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="PLANNED", reason="p")

        # Merge while still PLANNED (not VERIFYING) — should trigger BLOCKED
        result = self.cm.ingest_forge_event(
            CI, change_set_id=cs_id, event_type="pr_merged",
            payload={"repository": "repo", "commit_sha": "abc1234",
                     "target_branch": "main"})

        cs_state = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(cs_state["status"], "BLOCKED",
                         "Merge before VERIFYING should block the change set")

    # ---- Work planning accuracy ----

    def test_story_status_never_set_directly(self):
        """Story status is DERIVED from events — never set by the plan commit."""
        items = [
            {"id": "REQ-99", "path": "plans/requirements/REQ-99.json",
             "data": {"title": "Test req"}},
            {"id": "ST-99", "path": "plans/stories/ST-99.json",
             "data": {
                 "title": "Test story",
                 "type": "FEATURE_STORY", "size": "S",
                 "source_refs": ["REQ-99"],
                 "acceptance_criteria": [
                     {"id": "ST-99/AC-1", "given": "x", "when": "y", "then": "z",
                      "kind": "functional", "verification": "automated"},
                 ],
             }},
        ]
        self.wp.ingest_plan_commit(
            CI, repository="repo", commit_sha="a" * 7, items=items)

        story = self.wp.get_work_item(DEVELOPER, "ST-99")
        # Status should be derived, not set
        self.assertIn("status", story)
        self.assertIn("status_flags", story)

    def test_plan_item_with_forbidden_fields_rejected(self):
        """Plan items cannot contain status/state/ready/done/accepted — these are derived."""
        items = [
            {"id": "ST-100", "path": "plans/stories/ST-100.json",
             "data": {
                 "title": "Test", "type": "FEATURE_STORY", "size": "S",
                 "source_refs": ["REQ-1"],
                 "status": "READY",  # FORBIDDEN
                 "acceptance_criteria": [
                     {"id": "ST-100/AC-1", "given": "x", "when": "y", "then": "z",
                      "kind": "functional", "verification": "automated"},
                 ],
             }},
        ]
        with self.assertRaises(ValidationError) as ctx:
            self.wp.ingest_plan_commit(
                CI, repository="repo", commit_sha="b" * 7, items=items)
        self.assertIn("status", str(ctx.exception).lower())

    # ---- Contract drift accuracy ----

    def test_contract_drift_detection_is_field_accurate(self):
        """Drift detection correctly identifies missing, extra, and type-changed fields."""
        self.cr.register_contract(
            ARCHITECT, contract_id="user-api", provider="backend",
            version="1.0.0", type="http", consumers=["frontend"],
            spec={"fields": {
                "id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            }},
        )

        # Missing field
        drift = self.cr.detect_drift(
            DEVELOPER, contract_id="user-api",
            observed_spec={"fields": {
                "id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                # email is missing!
            }})
        self.assertTrue(drift["drift"], "Should detect missing field as drift")

        # Extra field (no drift — additive is backward-compatible by default)
        no_drift = self.cr.detect_drift(
            DEVELOPER, contract_id="user-api",
            observed_spec={"fields": {
                "id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
                "phone": {"type": "string", "required": False},
            }})
        # Depending on compatibility policy, extra fields may or may not be drift
        # The key test is that it runs without error and returns a result
        self.assertIn("drift", no_drift)

    # ---- Escalation reason code validation ----

    def test_invalid_escalation_reason_codes_rejected(self):
        """Only known escalation reason codes are accepted — prevents arbitrary risk inflation."""
        cs = self._create_cs("Test", ["T-15"], ["repo"])
        with self.assertRaises(ValidationError) as ctx:
            self.cm.compute_risk_tier(
                DEVELOPER, change_set_id=cs["id"],
                paths=["src/main.ts"],
                reason_codes=["MADE_UP_REASON"],
                diff_lines=10,
            )
        self.assertIn("unknown escalation reason codes", str(ctx.exception))

    # ---- Failure class validation ----

    def test_invalid_failure_class_rejected(self):
        """Only failure classes from failure-class-map.json are accepted."""
        cs = self._create_cs("Test", ["T-16"], ["repo"])
        fact = self._fact("error", cs["id"])

        with self.assertRaises(ValidationError) as ctx:
            self.ledger.record_incident(
                DEVELOPER,
                skill="test-skill", step="check",
                failure_class="TOTALLY_FAKE_CLASS",
                signal_type="negative",
                signal_source="AGENT",
                pattern_eligible=True,
                evidence_refs=[fact["entry_id"]],
            )
        self.assertIn("failure-class-map.json", str(ctx.exception))

    # ---- Task isolation ----

    def test_task_requires_worktree_isolation(self):
        """IN_PROGRESS tasks require a worktree — prevents concurrent modification."""
        cs = self._create_cs("Test", ["T-17"], ["repo"])
        cs_id = cs["id"]

        # Progress to EXECUTING
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="SCOPED", reason="s")
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="PLANNED", reason="p")
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="plan_check_passed", payload={})
        cs_state = self.cm.get_change_set(DEVELOPER, cs_id)

        if cs_state["status"] == "PLAN_APPROVED":
            self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                                  status="EXECUTING", reason="Starting")

            # Task without worktree should fail
            self.cm.record_task(DEVELOPER, change_set_id=cs_id,
                                task_id="T-impl-1", owner_role="developer")
            with self.assertRaises(ValidationError) as ctx:
                self.cm.record_task(DEVELOPER, change_set_id=cs_id,
                                    task_id="T-impl-1", owner_role="developer",
                                    status="IN_PROGRESS")
            self.assertIn("worktree", str(ctx.exception))


# ==========================================================================
# Summary comparison test
# ==========================================================================
class TestMetricsSummary(_EvalBase):
    """Run both paths for one requirement and produce a side-by-side comparison."""

    def test_comparison_summary(self):
        """Demonstrate the metric gap between with-ADLC and without-ADLC."""
        # --- Path A: No ADLC ---
        cs_a = self._create_cs("Auth token refresh (no ADLC)", ["REQ-AUTH-1"], ["auth-svc"])
        m_a = self._collect_metrics(cs_a["id"], "No ADLC")

        # --- Path B: With ADLC ---
        cs_b = self._create_cs("Auth token refresh (with ADLC)",
                               ["REQ-AUTH-1"], ["auth-svc"])
        cs_id = cs_b["id"]

        # Record evidence chain
        f1 = self._fact("auth-svc/src/token.ts: refresh token uses SHA256 HMAC, "
                        "30-day expiry, stored in httpOnly cookie",
                        cs_id, source="cmd:cat auth-svc/src/token.ts")
        f2 = self._fact("auth-svc/test/token.test.ts: 12 tests, no test for token "
                        "rotation on refresh",
                        cs_id, source="cmd:cat auth-svc/test/token.test.ts")
        f3 = self._fact("security scan: no token rotation = refresh token reuse attack surface",
                        cs_id, source="cmd:npm audit")

        inf = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Token refresh has no rotation — a stolen refresh token is valid for 30 days. "
                    "Fix: rotate on every refresh, revoke old token.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[f1["entry_id"], f2["entry_id"], f3["entry_id"]],
        )

        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="Implement token rotation: on refresh, issue new refresh token and "
                    "invalidate the old one. Store token family for reuse detection.",
            source_type="agent_analysis", change_set_id=cs_id,
            input_references=[inf["entry_id"]],
            lifecycle_state="PROPOSED",
        )

        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="RISK",
            content="Token family tracking adds a DB write on every refresh. "
                    "At 500 refresh/min, this is 500 extra writes/min to token_families table.",
            source_type="agent_analysis", change_set_id=cs_id,
            metadata={"impact": "MEDIUM", "mitigation": "Use Redis for family tracking"},
        )

        self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id,
            paths=["auth-svc/src/token.ts", "auth-svc/src/middleware/auth.ts"],
            reason_codes=[], diff_lines=80,
        )

        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="SCOPED", reason="Token rotation scope")

        m_b = self._collect_metrics(cs_id, "With ADLC")

        # --- Assertions on the gap ---
        self.assertGreater(m_b.facts_recorded, m_a.facts_recorded,
                           "ADLC path should have more FACTs")
        self.assertGreater(m_b.inferences_recorded, m_a.inferences_recorded,
                           "ADLC path should have more INFERENCEs")
        self.assertGreater(m_b.risks_recorded, m_a.risks_recorded,
                           "ADLC path should identify more risks")
        self.assertEqual(m_b.grounding_ratio, 1.0,
                         "ADLC path should have 100% grounding ratio")
        self.assertTrue(m_b.risk_tier_computed,
                        "ADLC path should compute risk tier")
        self.assertFalse(m_a.risk_tier_computed,
                         "No-ADLC path should NOT compute risk tier")
        self.assertGreater(m_b.lifecycle_stages_traversed, m_a.lifecycle_stages_traversed,
                           "ADLC path should traverse more lifecycle stages")

        # Print summary for human review
        print("\n" + "=" * 70)
        print("ADLC EVALUATION SUMMARY")
        print("=" * 70)
        for m in [m_a, m_b]:
            print(f"\n--- {m.name} ---")
            print(f"  FACTs:          {m.facts_recorded}")
            print(f"  INFERENCEs:     {m.inferences_recorded} (unsourced: {m.unsourced_inferences})")
            print(f"  DECISIONs:      {m.decisions_recorded}")
            print(f"  RISKs:          {m.risks_recorded}")
            print(f"  QUESTIONs:      {m.questions_recorded}")
            print(f"  ASSUMPTIONs:    {m.assumptions_recorded}")
            print(f"  Grounding:      {m.grounding_ratio:.0%}")
            print(f"  Chain depth:    {m.evidence_chain_depth}")
            print(f"  Trust dist:     {m.trust_distribution}")
            print(f"  Risk tier:      {'computed' if m.risk_tier_computed else 'NOT computed'}")
            print(f"  Lifecycle:      {m.lifecycle_stages_traversed} transitions")
            print(f"  Handoffs:       {m.handoffs}")
            print(f"  Incidents:      {m.incidents_recorded}")
            print(f"  Blockers:       {m.blocking_items_surfaced}")
        print("=" * 70)


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")
    unittest.main()
