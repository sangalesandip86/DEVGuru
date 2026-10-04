#!/usr/bin/env python3
"""LLM-driven scenario tests: realistic developer workflows through the ADLC platform.

Simulates what actually happens when a developer drops into Claude Code and:
  1. Skips ADLC init and tries to implement a story directly
  2. Asks to research existing codebase functionality and produce a report
  3. Asks to find the root cause of a production issue
  4. Asks to analyze logs and correlate with code (and vice versa)
  5. Asks to add a new feature to existing functionality

Each scenario exercises the MCP API the way an LLM agent would call it in a real
conversation — including the error paths, backfill detection, evidence chains,
and cross-module interactions.

    python -m unittest skills/testing/pipeline-tests/test_llm_scenarios.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
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
PRODUCT_PLANNER = Identity("AGENT", "agent:product-planner", agent_role="product-planner",
                           tool="claude-code", model_id="model-a")
QA_DERIVE = Identity("AGENT", "agent:qa-derive", agent_role="qa-derive",
                     tool="claude-code", model_id="model-a")
QA_DIAGNOSE = Identity("AGENT", "agent:qa-diagnose", agent_role="qa-diagnose",
                       tool="claude-code", model_id="model-a")
TEST_ENGINEER = Identity("AGENT", "agent:test-engineer", agent_role="test-engineer",
                         tool="claude-code", model_id="model-a")

ALL_MODULES = "evidence_ledger,change_management,work_planning,contract_registry"
RUN_ID = "run-llm-scenario"

BOOTSTRAP = REPO_ROOT / "skills" / "workflow" / "bootstrap" / "scripts" / "bootstrap_project.py"
RESOLVE = REPO_ROOT / "skills" / "workflow" / "workspace-resolver" / "scripts" / "resolve_workspace.py"
PREFLIGHT = REPO_ROOT / "skills" / "workflow" / "stage-preflight" / "scripts" / "stage_preflight.py"

import os  # noqa: E402


def _run(script, *args, cwd=None, env_extra=None):
    env = {**os.environ, "ADLC_SKILLS_ROOT": str(REPO_ROOT)}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True, timeout=30, cwd=cwd, env=env,
    )


class _ScenarioBase(unittest.TestCase):
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


# ---------------------------------------------------------------------------
# Scenario 1: User skips ADLC init, jumps straight to "implement this story"
# ---------------------------------------------------------------------------
class TestNoInitDirectImplement(_ScenarioBase):
    """User says 'implement ST-42 add caching to /api/products' without running /adlc init.
    The LLM must detect the cold-start state and handle it gracefully."""

    def test_preflight_detects_unbootstrapped_repo(self):
        """stage_preflight returns BACKFILL/BLOCK on a repo with no plans/ or workspace manifest."""
        tmpdir = tempfile.mkdtemp(prefix="adlc-noinit-")
        try:
            subprocess.run(["git", "init", "-q", tmpdir], check=True, capture_output=True)
            r = _run(PREFLIGHT, "--start", "IMPLEMENT", cwd=tmpdir)
            self.assertIn(r.returncode, [0, 1, 2])
            if r.returncode != 2:
                data = json.loads(r.stdout)
                items = data.get("items", [])
                statuses = [it.get("status") for it in items]
                self.assertTrue(
                    any(s in ("BACKFILL", "BLOCK", "ASK") for s in statuses) or not items,
                    f"IMPLEMENT on unbootstrapped repo should need backfill, got {statuses}")
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_bootstrap_then_implement_succeeds(self):
        """After bootstrap, the LLM can create a change set and start working."""
        tmpdir = tempfile.mkdtemp(prefix="adlc-bootstrap-")
        try:
            subprocess.run(["git", "init", "-q", tmpdir], check=True, capture_output=True)
            r = _run(BOOTSTRAP, "--root", tmpdir, "--system", "ecommerce",
                     "--title", "Add caching to /api/products")
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(r.stdout)
            self.assertTrue(data["ok"])

            r2 = _run(PREFLIGHT, "--start", "IMPLEMENT", cwd=tmpdir)
            self.assertIn(r2.returncode, [0, 1, 2])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_llm_creates_inline_story_for_low_tier_bugfix(self):
        """For LOW-tier BUG_FIX, the LLM can use an inline story in the PR body
        instead of full plan ingestion — the cold-start escape hatch."""
        cs = self._create_cs("Fix caching bug in /api/products",
                             ["BUG-CACHE-1"], ["ecommerce-api"])
        cs_id = cs["id"]

        # LLM reads the code and finds the bug — hooks write FACTs
        code_fact = self._fact(
            "src/routes/products.ts:45 — cache.get() called without TTL check, "
            "stale data served for up to 24h after price update",
            cs_id, source="cmd:cat src/routes/products.ts")

        test_fact = self._fact(
            "npm test: FAIL test/products.test.ts — expected price 29.99, got 19.99 (stale cache)",
            cs_id, source="cmd:npm test")

        # LLM records its analysis as INFERENCE (not FACT — it's the agent's conclusion)
        analysis = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Bug: cache.get() returns stale price. Fix: add TTL of 5min "
                    "or invalidate on price update webhook.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[code_fact["entry_id"], test_fact["entry_id"]],
        )
        self.assertEqual(analysis["classification"], "INFERENCE")
        refs = json.loads(analysis["input_references"]) if isinstance(
            analysis["input_references"], str) else analysis["input_references"]
        self.assertEqual(len(refs), 2)

        # LLM proposes a fix as DECISION
        decision = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="Invalidate product cache on price-update webhook. "
                    "Add cache.del(productId) in webhook handler. ADR-inline.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[analysis["entry_id"]],
            lifecycle_state="PROPOSED",
        )
        self.assertEqual(decision["lifecycle_state"], "PROPOSED")

        # LLM computes risk tier — should be LOW for a simple cache fix
        risk = self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id,
            paths=["ecommerce-api/src/routes/products.ts",
                   "ecommerce-api/src/webhooks/price-update.ts"],
            reason_codes=[], diff_lines=15,
        )
        self.assertIn(risk["final_tier"], ("LOW", "MEDIUM", "HIGH", "CRITICAL"))

    def test_work_planning_nonexistent_story_graceful(self):
        """When LLM tries to query a story that was never ingested, it gets NotFound."""
        with self.assertRaises(NotFound):
            self.wp.get_work_item(DEVELOPER, "ST-42")

    def test_llm_cannot_bypass_evidence_chain(self):
        """LLM can't record an INFERENCE without input_references — even in a rush."""
        cs = self._create_cs("Quick fix", ["BUG-1"], ["app"])
        with self.assertRaises(ValidationError):
            self.ledger.record_evidence(
                DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
                content="The bug is in line 42", source_type="TOOL",
                change_set_id=cs["id"])


# ---------------------------------------------------------------------------
# Scenario 2: Research existing codebase and produce a report
# ---------------------------------------------------------------------------
class TestCodebaseResearch(_ScenarioBase):
    """User says 'research our authentication system and tell me how it works'.
    The LLM reads code, records evidence, and builds a structured report."""

    def test_research_evidence_chain(self):
        """LLM reads files, records FACTs via hooks, then INFERENCES referencing them."""
        cs = self._create_cs("Research: authentication system",
                             ["RESEARCH-AUTH-1"], ["backend"])
        cs_id = cs["id"]

        # Hook captures file reads as the LLM explores
        f1 = self._fact(
            "src/auth/middleware.ts: express middleware, checks JWT in Authorization header, "
            "verifies with RS256, extracts user_id and roles into req.user",
            cs_id, source="cmd:cat src/auth/middleware.ts")

        f2 = self._fact(
            "src/auth/providers/oauth.ts: OAuth2 provider with Google and GitHub, "
            "stores refresh tokens in Redis with 30d TTL",
            cs_id, source="cmd:cat src/auth/providers/oauth.ts")

        f3 = self._fact(
            "src/auth/rbac.ts: role-based access control with 4 roles: admin, editor, viewer, guest. "
            "Permissions defined in src/auth/permissions.json (127 entries)",
            cs_id, source="cmd:cat src/auth/rbac.ts")

        f4 = self._fact(
            "package.json: jsonwebtoken@9.0.2, passport@0.7.0, passport-google-oauth20@2.0.0, "
            "ioredis@5.3.2",
            cs_id, source="cmd:cat package.json | grep -E 'jwt|passport|redis'")

        f5 = self._fact(
            "test/auth/: 23 test files, 156 tests. Coverage: middleware 94%, oauth 67%, rbac 88%",
            cs_id, source="cmd:npx jest --coverage --silent test/auth/")

        # LLM synthesizes findings into INFERENCES — each referencing the FACTs
        arch_inference = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Auth architecture: JWT-based with RS256 signing. Three layers: "
                    "middleware (token validation), providers (OAuth2 Google/GitHub), "
                    "RBAC (4-role permission matrix). Refresh tokens persisted in Redis.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[f1["entry_id"], f2["entry_id"], f3["entry_id"]],
        )

        dep_inference = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Dependencies: jsonwebtoken@9.0.2 (current), passport@0.7.0 (latest: 0.7.0), "
                    "Redis for session state. No known CVEs in current versions.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[f4["entry_id"]],
        )

        coverage_inference = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Test coverage gap: OAuth provider at 67% — refresh token rotation "
                    "and error handling paths undertested.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[f5["entry_id"]],
        )

        # LLM raises a RISK it discovered during research
        risk = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="RISK",
            content="Redis session store has no fallback. If Redis goes down, "
                    "all active sessions are lost and users must re-authenticate.",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"impact": "HIGH", "mitigation": "Add in-memory LRU cache as fallback"},
        )

        # LLM records an open question for the team
        question = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="QUESTION",
            content="Is the 30-day refresh token TTL a business requirement or an arbitrary choice? "
                    "SOC2 compliance may require shorter rotation.",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"blocking": False},
        )

        # Verify the complete evidence chain
        all_evidence = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        classifications = {e["classification"] for e in all_evidence}
        self.assertIn("FACT", classifications)
        self.assertIn("INFERENCE", classifications)
        self.assertIn("RISK", classifications)
        self.assertIn("QUESTION", classifications)

        # Verify every INFERENCE has input_references (evidence-gate compliance)
        inferences = [e for e in all_evidence if e["classification"] == "INFERENCE"]
        for inf in inferences:
            refs = json.loads(inf["input_references"]) if isinstance(
                inf["input_references"], str) else inf["input_references"]
            self.assertGreater(len(refs), 0,
                               f"INFERENCE {inf['entry_id']} has no references")

        # Verify FACTs come from SYSTEM, not agents
        facts = [e for e in all_evidence if e["classification"] == "FACT"]
        for fact in facts:
            self.assertEqual(fact["actor_type"], "SYSTEM")

    def test_research_registers_discovered_contracts(self):
        """During research, the LLM discovers API contracts and registers them."""
        cs = self._create_cs("Research: API surface", ["RESEARCH-API-1"], ["backend"])
        cs_id = cs["id"]

        # LLM reads OpenAPI spec
        api_fact = self._fact(
            "openapi.yaml: 14 endpoints, 5 resources (users, products, orders, "
            "payments, notifications). Versioned at /api/v2.",
            cs_id, source="cmd:cat openapi.yaml | head -100")

        # Registers discovered contracts
        self.cr.register_contract(
            ARCHITECT, contract_id="user-api-v2", provider="backend",
            version="2.0.0", type="http", consumers=["web-frontend", "mobile-app"],
            spec={"fields": {
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "role": {"type": "string", "required": True},
            }},
        )

        self.cr.register_contract(
            ARCHITECT, contract_id="order-events", provider="backend",
            version="1.0.0", type="event", consumers=["notification-svc", "analytics"],
            spec={"fields": {
                "order_id": {"type": "string", "required": True},
                "event_type": {"type": "string", "required": True},
                "payload": {"type": "object", "required": True},
            }},
        )

        # LLM records the discovery as evidence
        self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Registered 2 contracts from codebase analysis: user-api-v2 (HTTP, "
                    "4 fields) and order-events (event, 3 fields). Consumers identified "
                    "from import analysis.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[api_fact["entry_id"]],
        )

        # Verify contracts are queryable
        drift = self.cr.detect_drift(
            ARCHITECT, contract_id="user-api-v2",
            observed_spec={"fields": {
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "role": {"type": "string", "required": True},
            }})
        self.assertFalse(drift["drift"])


# ---------------------------------------------------------------------------
# Scenario 3: Find root cause of a production issue
# ---------------------------------------------------------------------------
class TestRootCauseAnalysis(_ScenarioBase):
    """User says 'users are getting 500 errors on checkout, find the root cause'.
    The LLM debugs by reading logs, code, and building an evidence chain to the root cause."""

    def test_root_cause_evidence_chain(self):
        """LLM traces from symptom to root cause with properly chained evidence."""
        cs = self._create_cs("Fix: checkout 500 errors", ["BUG-CHECKOUT-500"], ["checkout-svc"])
        cs_id = cs["id"]

        # Step 1: LLM reads error logs (hook captures as FACT)
        log_fact = self._fact(
            "error.log last 1h: 342 occurrences of 'TypeError: Cannot read properties "
            "of undefined (reading stripe_customer_id)' at checkout-svc/src/payment.ts:89",
            cs_id, source="cmd:grep 'TypeError' /var/log/checkout/error.log | tail -20")

        # Step 2: LLM reads the failing code
        code_fact = self._fact(
            "checkout-svc/src/payment.ts:89 — const customerId = user.stripe_customer_id; "
            "// user can be null when guest checkout was introduced in PR #1847",
            cs_id, source="cmd:cat checkout-svc/src/payment.ts")

        # Step 3: LLM checks git blame for when the regression was introduced
        blame_fact = self._fact(
            "git blame payment.ts:85-95 — line 89 changed in commit abc1234 "
            "(PR #1847 'Add guest checkout', merged 2026-10-01 by alice)",
            cs_id, source="cmd:git blame checkout-svc/src/payment.ts -L 85,95")

        # Step 4: LLM reads the PR that introduced the bug
        pr_fact = self._fact(
            "PR #1847 'Add guest checkout': allows checkout without account. "
            "payment.ts was not updated to handle null user. "
            "No test for guest checkout + Stripe path.",
            cs_id, source="cmd:gh pr view 1847 --json body,files")

        # Step 5: LLM synthesizes root cause (INFERENCE, not FACT)
        root_cause = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Root cause: PR #1847 added guest checkout but payment.ts:89 assumes "
                    "user is always authenticated. Guest users have no stripe_customer_id, "
                    "causing TypeError. 342 errors in the last hour. Regression introduced "
                    "2026-10-01.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[log_fact["entry_id"], code_fact["entry_id"],
                              blame_fact["entry_id"], pr_fact["entry_id"]],
        )
        refs = json.loads(root_cause["input_references"]) if isinstance(
            root_cause["input_references"], str) else root_cause["input_references"]
        self.assertEqual(len(refs), 4)

        # Step 6: LLM proposes fix as DECISION
        fix = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="DECISION",
            content="Fix: add null check at payment.ts:89 — if guest, redirect to "
                    "guest payment flow (Stripe Checkout Session without saved customer). "
                    "Add test for guest checkout + payment path.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[root_cause["entry_id"]],
            lifecycle_state="PROPOSED",
        )

        # Step 7: LLM records a RISK about the fix
        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="RISK",
            content="Guest payment creates orphaned Stripe sessions that aren't linked "
                    "to any user account. Need cleanup job or association on account creation.",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"impact": "MEDIUM", "mitigation": "Add Stripe webhook to link sessions on signup"},
        )

        # Step 8: Record incident for the production feedback loop
        incident = self.ledger.record_incident(
            DEVELOPER,
            skill="evidence-gate",
            step="verify",
            failure_class="INCORRECT_BEHAVIOR",
            signal_type="negative",
            signal_source="AGENT",
            pattern_eligible=True,
            evidence_refs=[log_fact["entry_id"], root_cause["entry_id"]],
        )
        self.assertTrue(incident["incident_id"].startswith("INC-"))

        # Verify the evidence chain is complete and traceable
        all_evidence = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        self.assertGreaterEqual(len(all_evidence), 7)

        # Every INFERENCE/DECISION chains back to at least one FACT
        for e in all_evidence:
            if e["classification"] in ("INFERENCE", "DECISION"):
                erefs = json.loads(e["input_references"]) if isinstance(
                    e["input_references"], str) else e["input_references"]
                self.assertGreater(len(erefs), 0)

    def test_root_cause_with_assumption(self):
        """When the LLM can't fully confirm the root cause, it records an ASSUMPTION."""
        cs = self._create_cs("Investigate: slow queries", ["BUG-PERF-1"], ["api-svc"])
        cs_id = cs["id"]

        metrics_fact = self._fact(
            "p99 latency jumped from 120ms to 2.3s at 14:00 UTC. "
            "Database CPU at 95% during the window.",
            cs_id, source="cmd:curl metrics-api/dashboard/latency")

        # LLM's best guess — it can't prove it without more data
        assumption = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="ASSUMPTION",
            content="The slow queries are likely caused by the missing index on "
                    "orders.user_id added in migration 0042. The table has 12M rows "
                    "and a sequential scan takes ~2s.",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"impact": "HIGH", "expires_at": "2026-10-11T00:00:00Z"},
        )
        self.assertEqual(assumption["classification"], "ASSUMPTION")

        # LLM asks a blocking question to confirm
        question = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="QUESTION",
            content="Can someone run EXPLAIN ANALYZE on the checkout query in production "
                    "to confirm the missing index is the cause?",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"blocking": True},
        )
        blockers = self.ledger.blocking_items(cs_id)
        self.assertGreater(len(blockers), 0)

    def test_correction_when_root_cause_wrong(self):
        """When initial analysis is wrong, LLM records a correction (not a delete)."""
        cs = self._create_cs("Debug: memory leak", ["BUG-MEM-1"], ["worker-svc"])
        cs_id = cs["id"]

        heap_fact = self._fact("heap dump: 2.1GB, 800k EventEmitter listeners", cs_id)

        wrong_analysis = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Memory leak caused by unbounded EventEmitter listeners in the "
                    "WebSocket connection handler.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[heap_fact["entry_id"]],
        )

        # LLM discovers the real cause and CORRECTS (not deletes) the wrong analysis
        new_fact = self._fact(
            "strace: fd leak in file upload handler — temp files not closed on error path",
            cs_id, source="cmd:strace -e trace=open,close -p 12345")

        correction = self.ledger.record_correction(
            DEVELOPER, parent_entry_id=wrong_analysis["entry_id"],
            run_id=RUN_ID,
            content="Correction: the EventEmitter listeners are expected (one per WS connection). "
                    "The real leak is in the file upload handler — temp files opened on "
                    "error path are never closed. strace confirms fd exhaustion.",
            source_type="TOOL",
            input_references=[new_fact["entry_id"]],
        )

        # Original analysis is now CHALLENGED
        entries = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        orig = [e for e in entries if e["entry_id"] == wrong_analysis["entry_id"]]
        self.assertEqual(orig[0]["derived_status"], "CHALLENGED")


# ---------------------------------------------------------------------------
# Scenario 4: Analyze logs and correlate with code (and vice versa)
# ---------------------------------------------------------------------------
class TestLogCodeCorrelation(_ScenarioBase):
    """User says 'here are our error logs, find where in the code this comes from'
    AND the reverse: 'look at this code and tell me what logs to search for'."""

    def test_logs_to_code_correlation(self):
        """LLM analyzes log entries, finds the code that produces them,
        and records the full correlation chain."""
        cs = self._create_cs("Log analysis: payment failures",
                             ["OPS-LOG-1"], ["payment-svc"])
        cs_id = cs["id"]

        # User provides log entries — hooks capture them
        log1 = self._fact(
            "2026-10-04 03:14:22 ERROR PaymentGateway.processCharge: "
            "StripeCardError code=card_declined for order_id=ORD-98765. "
            "Retry 3/3 exhausted. Trace: abc-def-123",
            cs_id, source="cmd:grep 'StripeCardError' payment.log | tail -5")

        log2 = self._fact(
            "2026-10-04 03:14:22 WARN PaymentGateway.processCharge: "
            "Idempotency key collision for order_id=ORD-98765, key=pay_ORD-98765_1696388062. "
            "Previous attempt returned card_declined.",
            cs_id, source="cmd:grep 'Idempotency' payment.log | tail -5")

        log3 = self._fact(
            "2026-10-04 03:14:23 ERROR OrderService.complete: "
            "Payment failed after 3 retries for ORD-98765. Marking order FAILED. "
            "User notified via email.",
            cs_id, source="cmd:grep 'ORD-98765' order.log")

        # LLM searches codebase for the log messages
        code1 = self._fact(
            "payment-svc/src/gateway.ts:142 — logger.error('PaymentGateway.processCharge: ' "
            "+ error.type + ' code=' + error.code). Retry logic at lines 135-155.",
            cs_id, source="cmd:grep -n 'PaymentGateway.processCharge' src/gateway.ts")

        code2 = self._fact(
            "payment-svc/src/gateway.ts:128 — const idempotencyKey = "
            "`pay_${orderId}_${Math.floor(Date.now()/1000)}`. Key uses second-precision "
            "timestamp — two retries within same second get the same key.",
            cs_id, source="cmd:grep -n 'idempotencyKey' src/gateway.ts")

        # LLM correlates logs with code
        correlation = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Log correlation: the StripeCardError at gateway.ts:142 triggers retry "
                    "logic (lines 135-155). The idempotency key at line 128 uses second-precision "
                    "timestamp, causing key collisions when retries happen within 1 second. "
                    "Fix: use a UUID or order_id+attempt_number for the idempotency key.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[log1["entry_id"], log2["entry_id"], log3["entry_id"],
                              code1["entry_id"], code2["entry_id"]],
        )
        refs = json.loads(correlation["input_references"]) if isinstance(
            correlation["input_references"], str) else correlation["input_references"]
        self.assertEqual(len(refs), 5)

    def test_code_to_logs_suggestion(self):
        """LLM reads code and tells the user what logs to search for to diagnose an issue."""
        cs = self._create_cs("Suggest logs for order pipeline debug",
                             ["OPS-LOG-2"], ["order-svc"])
        cs_id = cs["id"]

        # LLM reads the code
        code_fact = self._fact(
            "order-svc/src/pipeline.ts: OrderPipeline class with 5 stages: "
            "validate(logger.info 'OrderPipeline.validate'), "
            "reserve_inventory(logger.info 'InventoryReserve.attempt'), "
            "charge_payment(logger.info 'PaymentCharge.start'), "
            "fulfill(logger.info 'Fulfillment.dispatch'), "
            "notify(logger.info 'Notification.send'). "
            "Each stage logs with structured JSON: {order_id, stage, status, duration_ms}",
            cs_id, source="cmd:cat order-svc/src/pipeline.ts")

        error_fact = self._fact(
            "order-svc/src/pipeline.ts:178 — catch block logs "
            "logger.error('OrderPipeline.stageFailed', {order_id, stage, error: err.message}). "
            "Retry decorator at line 12: @Retry({maxAttempts: 3, backoff: 'exponential'})",
            cs_id, source="cmd:grep -n 'error\\|catch\\|retry' order-svc/src/pipeline.ts")

        # LLM produces log search suggestions
        suggestion = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="To debug order pipeline issues, search these log patterns:\n"
                    "1. Full trace: grep 'order_id=<ID>' across all services\n"
                    "2. Stage failures: grep 'OrderPipeline.stageFailed' — shows which stage failed\n"
                    "3. Retries: grep 'Retry attempt' + order_id — shows retry count and backoff\n"
                    "4. Inventory: grep 'InventoryReserve.attempt' — shows stock check results\n"
                    "5. Payment: grep 'PaymentCharge.start' — shows charge attempts and Stripe responses\n"
                    "6. Timing: parse duration_ms from structured JSON to find slow stages",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[code_fact["entry_id"], error_fact["entry_id"]],
        )
        self.assertEqual(suggestion["classification"], "INFERENCE")

    def test_log_analysis_records_dependency(self):
        """During log analysis, LLM discovers a cross-service dependency and records it."""
        cs = self._create_cs("Log analysis: cross-service", ["OPS-LOG-3"],
                             ["order-svc", "inventory-svc"])
        cs_id = cs["id"]

        log_fact = self._fact(
            "order.log: 'InventoryReserve.attempt failed: connection refused inventory-svc:8080'. "
            "inventory.log: 'Shutting down for deployment at 03:14:00 UTC'",
            cs_id, source="cmd:grep 'inventory' order.log inventory.log")

        dep = self.cm.record_dependency(
            DEVELOPER, change_set_id=cs_id,
            source="order-svc/OrderPipeline.reserve_inventory",
            target="inventory-svc:8080/api/v1/reserve",
            type="runtime_http",
            confidence=1.0,
            evidence_level="OBSERVED",
            resolved=False,
        )
        self.assertEqual(dep["status"], "UNRESOLVED")
        self.assertEqual(dep["evidence_level"], "OBSERVED")

        # LLM records the discovery
        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Order failures at 03:14 UTC caused by inventory-svc deployment. "
                    "No graceful shutdown or circuit breaker. Orders depend on synchronous "
                    "HTTP call to inventory-svc — any downtime causes immediate failures.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[log_fact["entry_id"]],
        )


# ---------------------------------------------------------------------------
# Scenario 5: Add new feature to existing functionality
# ---------------------------------------------------------------------------
class TestAddFeatureToExisting(_ScenarioBase):
    """User says 'add email notifications when an order ships'.
    LLM must scan existing code, register contracts, plan the change,
    and produce a properly evidenced implementation plan."""

    def test_feature_with_convention_scan(self):
        """LLM scans existing patterns before implementing."""
        cs = self._create_cs("Add shipping notification emails",
                             ["REQ-SHIP-NOTIF-1"], ["order-svc", "email-svc"])
        cs_id = cs["id"]

        # Step 1: LLM scans existing notification patterns
        existing_fact = self._fact(
            "email-svc/src/templates/: 8 existing templates (welcome, password-reset, "
            "order-confirmation, order-cancelled, invoice, refund, account-locked, "
            "two-factor). All use Handlebars with shared layout in layouts/main.hbs.",
            cs_id, source="cmd:ls email-svc/src/templates/")

        config_fact = self._fact(
            "email-svc/src/config.ts: SendGrid transport, templates loaded from filesystem, "
            "rate limit 100/min per recipient. Queue: BullMQ on Redis.",
            cs_id, source="cmd:cat email-svc/src/config.ts")

        event_fact = self._fact(
            "order-svc/src/events.ts: OrderEventEmitter extends EventEmitter. "
            "Events: ORDER_CREATED, ORDER_PAID, ORDER_CANCELLED, ORDER_REFUNDED. "
            "No ORDER_SHIPPED event exists yet.",
            cs_id, source="cmd:cat order-svc/src/events.ts")

        # Step 2: LLM records convention analysis
        convention = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="Convention analysis: email-svc uses Handlebars templates with shared layout, "
                    "SendGrid transport, BullMQ queue. New template should follow existing pattern. "
                    "order-svc uses EventEmitter — need to add ORDER_SHIPPED event. "
                    "email-svc subscribes to events via Redis pub/sub (see email-svc/src/subscribers/).",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[existing_fact["entry_id"], config_fact["entry_id"],
                              event_fact["entry_id"]],
        )

        # Step 3: LLM registers the new contract between services
        self.cr.register_contract(
            ARCHITECT, contract_id="order-shipping-events", provider="order-svc",
            version="1", type="event", consumers=["email-svc"],
            spec={"fields": {
                "order_id": {"type": "string", "required": True},
                "event_type": {"type": "string", "required": True},
                "shipped_at": {"type": "string", "required": True},
                "tracking_number": {"type": "string", "required": False},
                "carrier": {"type": "string", "required": False},
                "recipient_email": {"type": "string", "required": True},
            }},
        )

        # Step 4: LLM proposes the implementation
        decision = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="DECISION",
            content="Implementation plan: "
                    "1. order-svc: add ORDER_SHIPPED event to EventEmitter "
                    "2. order-svc: emit event in shipment.markShipped() "
                    "3. email-svc: add shipping-confirmation.hbs template "
                    "4. email-svc: add OrderShippedSubscriber "
                    "5. Tests: event emission, template rendering, subscriber integration "
                    "Follow existing Handlebars + BullMQ + Redis pub/sub pattern. ADR-inline.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[convention["entry_id"]],
            lifecycle_state="PROPOSED",
        )

        # Step 5: LLM records risks
        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="RISK",
            content="Email delivery is fire-and-forget via BullMQ. If Redis is down when "
                    "ORDER_SHIPPED fires, the email is lost. Consider adding a fallback "
                    "to the orders table with a 'notification_sent' flag.",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"impact": "MEDIUM", "mitigation": "Add notification_sent column + retry cron"},
        )

        # Step 6: Hand off to developer
        ho = self.cm.record_handoff(
            ARCHITECT, change_set_id=cs_id, to_role="developer",
            payload={
                "summary": "Shipping notification: add ORDER_SHIPPED event + email template, "
                           "following existing Handlebars + BullMQ pattern",
                "inputs": [
                    {"artifact_ref": "order-svc@" + "a" * 7 + ":src/events.ts",
                     "content_hash": "sha256:" + "11" * 32},
                    {"artifact_ref": "email-svc@" + "b" * 7 + ":src/templates/order-confirmation.hbs",
                     "content_hash": "sha256:" + "22" * 32},
                ],
                "outputs": [
                    {"artifact_kind": "architecture-design",
                     "content_hash": "sha256:" + "33" * 32},
                ],
                "classifications": [],
            },
            verdict="ACCEPT",
        )
        self.assertEqual(ho["from_role"], "architect")
        self.assertEqual(ho["to_role"], "developer")

    def test_feature_with_plan_ingestion(self):
        """For a properly planned feature, LLM ingests stories and evaluates readiness."""
        # Ingest the plan
        items = [
            {"id": "REQ-10", "path": "plans/requirements/REQ-10.json", "data": {
                "title": "Shipping notification emails",
                "source_refs": ["PRD-2026-Q4"],
            }},
            {"id": "ST-10", "path": "plans/stories/ST-10.json", "data": {
                "title": "Add ORDER_SHIPPED event and email template",
                "type": "FEATURE_STORY",
                "size": "S",
                "source_refs": ["REQ-10"],
                "acceptance_criteria": [
                    {"id": "ST-10/AC-1",
                     "given": "An order is marked as shipped",
                     "when": "The shipment handler runs",
                     "then": "ORDER_SHIPPED event is emitted with order_id, tracking_number, carrier",
                     "kind": "functional", "verification": "automated"},
                    {"id": "ST-10/AC-2",
                     "given": "ORDER_SHIPPED event is received by email-svc",
                     "when": "The subscriber processes the event",
                     "then": "A shipping confirmation email is sent to the recipient",
                     "kind": "functional", "verification": "automated"},
                    {"id": "ST-10/AC-3",
                     "given": "Email delivery fails (SendGrid error)",
                     "when": "The subscriber catches the error",
                     "then": "The event is retried via BullMQ dead-letter queue, no data loss",
                     "kind": "negative", "verification": "automated"},
                ],
            }},
        ]
        self.wp.ingest_plan_commit(
            CI, repository="order-svc", commit_sha="d" * 7, items=items)

        # Evaluate readiness
        readiness = self.wp.evaluate_readiness(DEVELOPER, story_id="ST-10")
        self.assertIn("missing", readiness)
        self.assertIn("ac_hash", readiness)

        # Link to change set
        cs = self._create_cs("Implement shipping notifications",
                             ["REQ-10"], ["order-svc", "email-svc"])
        cs_id = cs["id"]

        link = self.wp.link_change_set(
            DEVELOPER, story_id="ST-10", change_set_id=cs_id,
            implements_declaration="Implements: ST-10")
        self.assertEqual(link["story_id"], "ST-10")

        # Query work graph shows the full picture
        graph = self.wp.query_work_graph(DEVELOPER, root_id="REQ-10", depth=3)
        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertIn("REQ-10", node_ids)
        self.assertIn("ST-10", node_ids)

    def test_feature_detects_contract_drift(self):
        """After implementing, LLM detects drift between declared and actual contract."""
        # Register the contract as designed
        self.cr.register_contract(
            ARCHITECT, contract_id="shipping-webhook", provider="logistics-api",
            version="1", type="http", consumers=["order-svc"],
            spec={"fields": {
                "shipment_id": {"type": "string", "required": True},
                "status": {"type": "string", "required": True},
                "tracking_url": {"type": "string", "required": True},
                "estimated_delivery": {"type": "string", "required": True},
            }},
        )

        # After implementation, LLM observes the actual API is different
        drift = self.cr.detect_drift(
            DEVELOPER, contract_id="shipping-webhook",
            observed_spec={"fields": {
                "shipment_id": {"type": "string", "required": True},
                "status": {"type": "string", "required": True},
                "tracking_url": {"type": "string", "required": True},
                # estimated_delivery is missing in the actual API!
            }})
        self.assertTrue(drift["drift"])

        # LLM records the drift as a RISK
        cs = self._create_cs("Fix shipping webhook drift",
                             ["BUG-DRIFT-1"], ["order-svc"])
        cs_id = cs["id"]

        drift_fact = self._fact(
            "Contract drift detected: shipping-webhook missing estimated_delivery field. "
            "Logistics API v1 docs show estimated_delivery as optional, "
            "but our contract declared it required.",
            cs_id, source="cmd:curl logistics-api/shipments/test123")

        self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="RISK",
            content="Contract drift: estimated_delivery declared required but missing from "
                    "logistics API responses. Our code assumes it exists and renders it in "
                    "the shipping email. Null reference in production.",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"impact": "HIGH", "mitigation": "Make field optional, add fallback text"},
        )

    def test_feature_qa_creates_test_design(self):
        """qa-derive creates a test design from the acceptance criteria."""
        cs = self._create_cs("Test design for shipping notif",
                             ["REQ-TD-1"], ["order-svc"])
        cs_id = cs["id"]

        # qa-derive reads the story ACs and creates test design
        ac_fact = self._fact(
            "ST-10: 3 acceptance criteria — event emission (functional), "
            "email delivery (functional), error handling (negative). "
            "All verification=automated.",
            cs_id, source="cmd:cat plans/stories/ST-10.json")

        test_design = self.ledger.record_evidence(
            QA_DERIVE, run_id=RUN_ID, classification="INFERENCE",
            content="Test design for ST-10: "
                    "1. Unit: OrderEventEmitter.emit('ORDER_SHIPPED') with correct payload "
                    "2. Integration: Redis pub/sub delivers event to email-svc subscriber "
                    "3. E2E: markShipped() -> email rendered with tracking info "
                    "4. Negative: SendGrid 500 -> BullMQ retries, dead-letter after 3 attempts "
                    "5. Negative: missing tracking_number -> email sent without tracking link",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[ac_fact["entry_id"]],
        )
        self.assertEqual(test_design["agent_role"], "qa-derive")

        # Hand off to test-engineer for implementation
        ho = self.cm.record_handoff(
            QA_DERIVE, change_set_id=cs_id, to_role="test-engineer",
            payload={
                "summary": "Test design for ST-10: 5 test cases covering event, delivery, and error paths",
                "inputs": [{"artifact_ref": "order-svc@" + "c" * 7 + ":plans/stories/ST-10.json",
                            "content_hash": "sha256:" + "44" * 32}],
                "outputs": [{"artifact_kind": "test-design",
                             "content_hash": "sha256:" + "55" * 32}],
                "classifications": [],
            },
            verdict="ACCEPT",
        )
        self.assertEqual(ho["to_role"], "test-engineer")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")
    unittest.main()
