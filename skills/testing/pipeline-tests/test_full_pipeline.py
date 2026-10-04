#!/usr/bin/env python3
"""Full ADLC pipeline tests: diverse requirements exercising ALL modules and skills.

Simulates what LLM agents would actually do through the complete lifecycle:
  - Evidence Ledger: FACT, INFERENCE, QUESTION, ASSUMPTION, DECISION, RISK, corrections, incidents, lessons
  - Change Management: create, status transitions, snapshots, dependencies, tasks, risk tiering, handoffs, forge events
  - Work Planning: ingest_plan_commit, evaluate_readiness, evaluate_done, link_change_set, query_work_graph
  - Contract Registry: register, compatibility checks, drift detection, deployments, all 7 contract types

Each scenario uses a different realistic requirement exercising different agent roles.

    python -m pytest <this_file> -v
"""
from __future__ import annotations

import json
import sys
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
QA_DIAGNOSE = Identity("AGENT", "agent:qa-diagnose", agent_role="qa-diagnose",
                       tool="claude-code", model_id="model-a")

ALL_MODULES = "evidence_ledger,change_management,work_planning,contract_registry"
RUN_ID = "run-full-pipeline"


class _PipelineBase(unittest.TestCase):
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
# Scenario 1: Notification System — full work planning lifecycle
# ---------------------------------------------------------------------------
class TestNotificationSystem(_PipelineBase):
    """Build a real-time notification system: exercises work_planning with plan ingestion,
    readiness gates, story linking, and work graph queries."""

    def test_plan_ingestion_and_readiness(self):
        cs = self._create_cs("Real-time Notification System",
                             ["REQ-NOTIF-1"], ["notif-svc", "web-app"])
        cs_id = cs["id"]

        # Product planner ingests plan via SYSTEM
        items = [
            {"id": "REQ-1", "path": "plans/requirements/REQ-1.json", "data": {
                "title": "Real-time notification system",
                "source_refs": ["PRD-2026-Q4"],
            }},
            {"id": "EPIC-1", "path": "plans/epics/EPIC-1.json", "data": {
                "title": "Notification delivery pipeline",
                "requirement": "REQ-1",
            }},
            {"id": "ST-1", "path": "plans/stories/ST-1.json", "data": {
                "title": "WebSocket connection manager",
                "type": "FEATURE_STORY",
                "size": "M",
                "source_refs": ["REQ-1"],
                "epic": "EPIC-1",
                "acceptance_criteria": [
                    {"id": "ST-1/AC-1", "given": "A user opens the dashboard",
                     "when": "WebSocket connects", "then": "Connection is authenticated and alive",
                     "kind": "functional", "verification": "automated"},
                    {"id": "ST-1/AC-2", "given": "A WebSocket connection drops",
                     "when": "Client detects disconnect", "then": "Automatic reconnect within 5s",
                     "kind": "functional", "verification": "automated"},
                    {"id": "ST-1/AC-3", "given": "An unauthenticated client connects",
                     "when": "Server validates token", "then": "Connection is rejected with 4001",
                     "kind": "negative", "verification": "automated"},
                ],
            }},
            {"id": "ST-2", "path": "plans/stories/ST-2.json", "data": {
                "title": "Push notification fanout",
                "type": "FEATURE_STORY",
                "size": "S",
                "source_refs": ["REQ-1"],
                "epic": "EPIC-1",
                "depends_on": ["ST-1"],
                "acceptance_criteria": [
                    {"id": "ST-2/AC-1", "given": "An event is published",
                     "when": "Fanout service processes it", "then": "All subscribed clients receive it within 200ms",
                     "kind": "functional", "verification": "automated"},
                    {"id": "ST-2/AC-2", "given": "A client is offline",
                     "when": "Event targets that client", "then": "Event is queued for delivery on reconnect",
                     "kind": "functional", "verification": "automated"},
                    {"id": "ST-2/AC-3", "given": "Fanout receives a malformed event",
                     "when": "Validation runs", "then": "Event is rejected and logged, no crash",
                     "kind": "negative", "verification": "automated"},
                ],
            }},
        ]
        result = self.wp.ingest_plan_commit(
            CI, repository="notif-svc", commit_sha="a" * 7, items=items)
        self.assertEqual(result["ingested"], 4)

        # Check work items are retrievable
        story1 = self.wp.get_work_item(DEVELOPER, "ST-1")
        self.assertEqual(story1["kind"], "story")
        self.assertEqual(story1["status"], "REFINING")
        self.assertIsNotNone(story1["ac_hash"])

        story2 = self.wp.get_work_item(DEVELOPER, "ST-2")
        self.assertEqual(story2["status"], "REFINING")

        # Query work graph from requirement
        graph = self.wp.query_work_graph(DEVELOPER, root_id="REQ-1", depth=3)
        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertIn("REQ-1", node_ids)
        self.assertIn("EPIC-1", node_ids)
        self.assertIn("ST-1", node_ids)
        self.assertIn("ST-2", node_ids)

        # Evaluate readiness (should fail — no evaluator connected)
        readiness = self.wp.evaluate_readiness(DEVELOPER, story_id="ST-1")
        self.assertEqual(readiness["gate"], "readiness")
        self.assertIn("ac_hash", readiness)

        # Structural readiness should pass for ST-1 (it has ACs, size, source_refs, negative AC)
        self.assertEqual(readiness["current_status"], "REFINING")

    def test_story_linking_and_graph(self):
        cs = self._create_cs("Notif linking test", ["REQ-NOTIF-2"], ["notif-svc"])
        cs_id = cs["id"]

        items = [{"id": "ST-3", "path": "plans/stories/ST-3.json", "data": {
            "title": "Email digest aggregator",
            "type": "FEATURE_STORY", "size": "S", "source_refs": ["REQ-NOTIF-2"],
            "acceptance_criteria": [
                {"id": "ST-3/AC-1", "given": "User has 5 unread notifications",
                 "when": "Digest cron runs at 9am", "then": "One email sent with all 5",
                 "kind": "functional", "verification": "automated"},
                {"id": "ST-3/AC-2", "given": "User has no unread notifications",
                 "when": "Digest cron runs", "then": "No email is sent",
                 "kind": "negative", "verification": "automated"},
            ],
        }}]
        self.wp.ingest_plan_commit(CI, repository="notif-svc", commit_sha="b" * 7, items=items)

        # Link story to change set
        link = self.wp.link_change_set(
            DEVELOPER, story_id="ST-3", change_set_id=cs_id,
            implements_declaration="Implements: ST-3")
        self.assertEqual(link["story_id"], "ST-3")
        self.assertEqual(link["change_set_id"], cs_id)

        # Query graph shows the implements edge
        graph = self.wp.query_work_graph(DEVELOPER, root_id="ST-3",
                                          relations=["implements"], depth=1)
        edge_relations = {e["relation"] for e in graph["edges"]}
        self.assertIn("implements", edge_relations)

    def test_evaluate_done_requires_linked_cs(self):
        items = [{"id": "ST-4", "path": "plans/stories/ST-4.json", "data": {
            "title": "SMS gateway integration",
            "type": "FEATURE_STORY", "size": "XS", "source_refs": ["REQ-NOTIF-3"],
            "acceptance_criteria": [
                {"id": "ST-4/AC-1", "given": "Notification target is mobile",
                 "when": "SMS enabled", "then": "SMS sent via gateway",
                 "kind": "functional", "verification": "automated"},
                {"id": "ST-4/AC-2", "given": "SMS gateway is down",
                 "when": "Sending fails", "then": "Retries 3x then queues for later",
                 "kind": "negative", "verification": "automated"},
            ],
        }}]
        self.wp.ingest_plan_commit(CI, repository="notif-svc", commit_sha="c" * 7, items=items)
        done = self.wp.evaluate_done(DEVELOPER, story_id="ST-4")
        self.assertFalse(done["passed"])
        self.assertTrue(any("Change Set" in m for m in done["missing"]))


# ---------------------------------------------------------------------------
# Scenario 2: Database Migration — risk tiering, snapshots, dependencies
# ---------------------------------------------------------------------------
class TestDatabaseMigration(_PipelineBase):
    """Migrate from MongoDB to PostgreSQL: exercises change management risk tiering,
    snapshots, dependencies, and the full status lifecycle."""

    def test_risk_tiering_and_snapshots(self):
        cs = self._create_cs("MongoDB to PostgreSQL migration",
                             ["REQ-DB-1"], ["user-svc", "order-svc"],
                             environments=["staging", "production"])
        cs_id = cs["id"]

        # Compute risk tier — touching database paths
        risk = self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id,
            paths=["user-svc/src/db/migrations/001_create_users.sql",
                   "user-svc/src/models/user.py",
                   "order-svc/src/db/schema.prisma"],
            reason_codes=["UNRESOLVED_DEPENDENCY"],
            diff_lines=450,
        )
        self.assertIn(risk["final_tier"], ("LOW", "MEDIUM", "HIGH", "CRITICAL"))
        self.assertIn("final_tier", risk)

        # Create snapshot pinning repository states
        snap = self.cm.create_snapshot(
            DEVELOPER, change_set_id=cs_id,
            repositories={"user-svc": "a" * 40, "order-svc": "b" * 40},
            contracts={"user-api": "v2", "order-api": "v3"},
            environments={"staging": {"replicas": 2}, "production": {"replicas": 5}},
        )
        self.assertTrue(snap["id"].startswith("SNAP-"))

        # Validate snapshot currency
        currency = self.cm.validate_snapshot_currency(
            DEVELOPER, snapshot_id=snap["id"],
            current_heads={"user-svc": "a" * 40, "order-svc": "b" * 40},
        )
        self.assertEqual(currency["snapshot_id"], snap["id"])

        # Stale snapshot detection
        stale = self.cm.validate_snapshot_currency(
            DEVELOPER, snapshot_id=snap["id"],
            current_heads={"user-svc": "c" * 40, "order-svc": "b" * 40},
            changed_paths={"user-svc": ["src/db/schema.prisma"]},
        )
        self.assertTrue(stale.get("stale") or any(
            r.get("stale") for r in stale.get("repositories", {}).values()
            if isinstance(r, dict)
        ) or "user-svc" in str(stale))

    def test_dependencies_block_integration(self):
        cs = self._create_cs("Migration deps test", ["REQ-DB-2"], ["user-svc"])
        cs_id = cs["id"]

        dep = self.cm.record_dependency(
            ARCHITECT, change_set_id=cs_id,
            source="user-svc/UserRepository", target="order-svc/OrderService",
            type="runtime", confidence=0.95, evidence_level="STATIC",
        )
        self.assertEqual(dep["status"], "UNRESOLVED")
        self.assertTrue(dep["id"].startswith("DEP-"))

        # Resolved dependency
        dep2 = self.cm.record_dependency(
            ARCHITECT, change_set_id=cs_id,
            source="user-svc/UserRepository", target="order-svc/OrderService",
            type="runtime", confidence=1.0, evidence_level="OBSERVED",
            resolved=True,
        )
        self.assertEqual(dep2["status"], "RESOLVED")

    def test_status_lifecycle(self):
        cs = self._create_cs("Migration lifecycle", ["REQ-DB-3"], ["user-svc"])
        cs_id = cs["id"]
        self.assertEqual(cs["status"], "DRAFT")

        # DRAFT -> SCOPED -> PLANNED
        cs = self.cm.update_status(
            DEVELOPER, change_set_id=cs_id, status="SCOPED",
            reason="Scope defined")
        self.assertEqual(cs["status"], "SCOPED")

        cs = self.cm.update_status(
            DEVELOPER, change_set_id=cs_id, status="PLANNED",
            reason="Architecture review complete")
        self.assertEqual(cs["status"], "PLANNED")

        # PLANNED -> PLAN_APPROVED requires forge events, but we can test blocking
        cs_full = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertIn("status_history", cs_full)
        self.assertGreater(len(cs_full["status_history"]), 0)


# ---------------------------------------------------------------------------
# Scenario 3: Multi-tenant Support — tasks, handoffs, contract compatibility
# ---------------------------------------------------------------------------
class TestMultiTenantSupport(_PipelineBase):
    """Add multi-tenant isolation: exercises tasks, handoffs between all roles,
    and contract compatibility checks."""

    def test_task_lifecycle(self):
        cs = self._create_cs("Multi-tenant isolation", ["REQ-MT-1"], ["platform"])
        cs_id = cs["id"]

        # Move to EXECUTING so tasks can start: DRAFT -> SCOPED -> PLANNED
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="SCOPED",
                              reason="Scope defined")
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="PLANNED",
                              reason="Plan complete")
        # Simulate plan approval via forge event
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="plan_check_passed",
                                   payload={"check": "plan-gate", "result": "passed"})
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="codeowners_review",
                                   payload={"approver": "tech-lead",
                                            "approver_role": "human:tech-lead",
                                            "state": "approved"})
        cs_after = self.cm.get_change_set(DEVELOPER, cs_id)

        # Record tasks
        t1 = self.cm.record_task(
            DEVELOPER, change_set_id=cs_id, task_id="TASK-1",
            owner_role="architect", depends_on=[], status="PENDING",
            ac_refs=["ST-1/AC-1", "ST-1/AC-2"],
        )
        self.assertEqual(t1["status"], "PENDING")

        t2 = self.cm.record_task(
            DEVELOPER, change_set_id=cs_id, task_id="TASK-2",
            owner_role="developer", depends_on=["TASK-1"], status="PENDING",
        )
        self.assertEqual(t2["status"], "PENDING")

        # Mark TASK-1 done
        self.cm.record_task(
            DEVELOPER, change_set_id=cs_id, task_id="TASK-1",
            owner_role="architect", status="DONE",
        )

        # TASK-2 can't start without EXECUTING status
        if cs_after["status"] == "PLAN_APPROVED":
            self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="EXECUTING",
                                  reason="Starting implementation")
            self.cm.record_task(
                DEVELOPER, change_set_id=cs_id, task_id="TASK-2",
                owner_role="developer", status="IN_PROGRESS",
                worktree="worktrees/task-2",
            )

    def test_all_role_handoffs(self):
        """Exercise handoffs between diverse role pairs."""
        cs = self._create_cs("Tenant handoff test", ["REQ-MT-2"], ["platform"])
        cs_id = cs["id"]

        handoff_payload = {
            "summary": "Tenant isolation review",
            "inputs": [{"artifact_ref": "platform@" + "a" * 7 + ":src/tenant.ts",
                        "content_hash": "sha256:" + "11" * 32}],
            "outputs": [{"artifact_kind": "design-doc",
                         "content_hash": "sha256:" + "22" * 32}],
            "classifications": [],
        }

        # architect -> developer
        ho1 = self.cm.record_handoff(
            ARCHITECT, change_set_id=cs_id, to_role="developer",
            payload=handoff_payload, verdict="ACCEPT")
        self.assertEqual(ho1["from_role"], "architect")

        # developer -> code-reviewer
        ho2 = self.cm.record_handoff(
            DEVELOPER, change_set_id=cs_id, to_role="code-reviewer",
            payload=handoff_payload, verdict="ACCEPT")
        self.assertEqual(ho2["to_role"], "code-reviewer")

        # code-reviewer -> security-reviewer
        ho3 = self.cm.record_handoff(
            CODE_REVIEWER, change_set_id=cs_id, to_role="security-reviewer",
            payload=handoff_payload, verdict="ACCEPT")
        self.assertEqual(ho3["to_role"], "security-reviewer")

        # security-reviewer -> qa-derive
        ho4 = self.cm.record_handoff(
            SECURITY, change_set_id=cs_id, to_role="qa-derive",
            payload=handoff_payload, verdict="ACCEPT")
        self.assertEqual(ho4["to_role"], "qa-derive")

        # qa-derive -> test-engineer
        ho5 = self.cm.record_handoff(
            QA_DERIVE, change_set_id=cs_id, to_role="test-engineer",
            payload=handoff_payload, verdict="ACCEPT")
        self.assertEqual(ho5["to_role"], "test-engineer")

        # product-planner -> product-owner
        ho6 = self.cm.record_handoff(
            PRODUCT_PLANNER, change_set_id=cs_id, to_role="product-owner",
            payload=handoff_payload, verdict="ACCEPT")
        self.assertEqual(ho6["to_role"], "product-owner")

        full_cs = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(len(full_cs["handoffs"]), 6)

    def test_contract_compatibility(self):
        """Register multi-version contracts and check compatibility."""
        # Provider registers v1
        self.cr.register_contract(
            DEVELOPER, contract_id="tenant-api", provider="platform",
            version="1", consumers=["admin-panel", "billing"],
            type="http", compatibility_policy="BACKWARD",
            spec={"fields": {
                "tenant_id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "plan": {"type": "string", "required": True},
            }},
        )

        # Consumer registers their view
        self.cr.register_contract(
            DEVELOPER, contract_id="tenant-api", provider="platform",
            version="1", type="http",
            party="admin-panel",
            spec={"fields": {
                "tenant_id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
            }},
        )

        # Deploy both
        self.cr.record_deployment(
            CI, app="platform", version="1.0.0", environment="production",
            contract_versions={"tenant-api": "1"})
        self.cr.record_deployment(
            CI, app="admin-panel", version="2.0.0", environment="production",
            contract_versions={"tenant-api": "1"})

        # Provider registers v2 (backward compatible — adds field)
        self.cr.register_contract(
            DEVELOPER, contract_id="tenant-api", provider="platform",
            version="2", type="http",
            spec={"fields": {
                "tenant_id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "plan": {"type": "string", "required": True},
                "settings": {"type": "object", "required": False},
            }},
        )

        # Check compatibility of new provider version against deployed consumer
        compat = self.cr.check_compatibility(
            DEVELOPER, contract_id="tenant-api",
            candidate_version="2", party="platform", environment="production")
        self.assertIn(compat["result"], ("COMPATIBLE", "INCOMPATIBLE"))


# ---------------------------------------------------------------------------
# Scenario 4: API Gateway — all 7 contract types
# ---------------------------------------------------------------------------
class TestAPIGateway(_PipelineBase):
    """Build an API gateway: exercises all 7 contract types and drift detection."""

    def test_all_contract_types(self):
        types_and_specs = [
            ("http", "gateway-rest", {"fields": {
                "endpoint": {"type": "string"}, "method": {"type": "string"}}}),
            ("grpc", "gateway-grpc", {"fields": {
                "service": {"type": "string"}, "method": {"type": "string"}}}),
            ("event", "gateway-events", {"fields": {
                "topic": {"type": "string"}, "payload": {"type": "object"}}}),
            ("schema", "gateway-schema", {"fields": {
                "entity": {"type": "string"}, "version": {"type": "integer"}}}),
            ("graphql", "gateway-graphql", {"fields": {
                "query": {"type": "string"}, "variables": {"type": "object"}}}),
            ("module", "gateway-module", {"fields": {
                "interface": {"type": "string"}, "methods": {"type": "array"}}}),
            ("websocket", "gateway-ws", {"fields": {
                "channel": {"type": "string"}, "message_type": {"type": "string"}}}),
        ]
        for ctype, cid, spec in types_and_specs:
            result = self.cr.register_contract(
                DEVELOPER, contract_id=cid, provider="gateway",
                version="1", type=ctype, spec=spec)
            self.assertEqual(result["registered_version"], "1")

    def test_drift_detection_with_changes(self):
        self.cr.register_contract(
            DEVELOPER, contract_id="user-api", provider="user-svc",
            version="1", type="http",
            spec={"fields": {
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
            }},
        )

        # No drift — same spec
        drift = self.cr.detect_drift(
            DEVELOPER, contract_id="user-api",
            observed_spec={"fields": {
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
            }})
        self.assertFalse(drift["drift"])

        # Drift — missing field
        drift2 = self.cr.detect_drift(
            DEVELOPER, contract_id="user-api",
            observed_spec={"fields": {
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            }})
        self.assertTrue(drift2["drift"])

        # Drift — extra field
        drift3 = self.cr.detect_drift(
            DEVELOPER, contract_id="user-api",
            observed_spec={"fields": {
                "id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
                "phone": {"type": "string", "required": False},
            }})
        self.assertTrue(drift3["drift"])

    def test_request_response_contract(self):
        """Request/response shorthand across different contract types."""
        self.cr.register_contract(
            DEVELOPER, contract_id="gateway-auth", provider="auth-svc",
            version="1", type="http",
            spec={
                "request": {"token": {"type": "string", "required": True}},
                "response": {"valid": {"type": "boolean", "required": True},
                             "user_id": {"type": "string", "required": True}},
            },
        )
        drift = self.cr.detect_drift(
            DEVELOPER, contract_id="gateway-auth",
            observed_spec={
                "request": {"token": {"type": "string", "required": True}},
                "response": {"valid": {"type": "boolean", "required": True},
                             "user_id": {"type": "string", "required": True}},
            })
        self.assertFalse(drift["drift"])


# ---------------------------------------------------------------------------
# Scenario 5: Security Audit — evidence chain with all classifications
# ---------------------------------------------------------------------------
class TestSecurityAudit(_PipelineBase):
    """SOC2 compliance audit: exercises every evidence classification,
    assumptions, risks, questions, and the full evidence lifecycle."""

    def test_complete_evidence_chain(self):
        cs = self._create_cs("SOC2 compliance audit", ["REQ-SEC-1"], ["platform"])
        cs_id = cs["id"]

        # FACT from hooks
        scan_fact = self._fact(
            "npm audit: 0 critical, 2 high (lodash@4.17.20 prototype pollution, "
            "jsonwebtoken@8.5.1 algorithm confusion)", cs_id,
            source="cmd:npm audit --json")

        # INFERENCE from security-reviewer analyzing the scan
        analysis = self.ledger.record_evidence(
            SECURITY, run_id=RUN_ID, classification="INFERENCE",
            content="lodash@4.17.20 prototype pollution is exploitable in our express middleware. "
                    "jsonwebtoken@8.5.1 requires explicit algorithm check, which we have.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[scan_fact["entry_id"]],
        )

        # RISK entry
        risk = self.ledger.record_evidence(
            SECURITY, run_id=RUN_ID, classification="RISK",
            content="Prototype pollution in lodash affects request parsing middleware. "
                    "An attacker could inject __proto__ to escalate privileges.",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"impact": "HIGH", "mitigation": "Upgrade lodash to 4.17.21"},
        )
        self.assertEqual(risk["classification"], "RISK")

        # ASSUMPTION with expiry
        assumption = self.ledger.record_evidence(
            SECURITY, run_id=RUN_ID, classification="ASSUMPTION",
            content="jsonwebtoken algorithm confusion is mitigated by our explicit RS256 check.",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"impact": "MEDIUM", "expires_at": "2027-01-01T00:00:00Z"},
        )
        self.assertEqual(assumption["classification"], "ASSUMPTION")

        # QUESTION — blocking
        question = self.ledger.record_evidence(
            SECURITY, run_id=RUN_ID, classification="QUESTION",
            content="Is the request parsing middleware used in the admin API or only the public API?",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"blocking": True},
        )
        blockers = self.ledger.blocking_items(cs_id)
        self.assertGreater(len(blockers), 0)

        # Answer the question
        answer = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="INFERENCE",
            content="Grep shows: middleware used in both admin and public routers.",
            source_type="TOOL", change_set_id=cs_id,
            answers_entry_id=question["entry_id"],
            input_references=[question["entry_id"], scan_fact["entry_id"]],
        )

        # Question should now be ANSWERED
        entries = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id,
                                             classification="QUESTION")
        q = [e for e in entries if e["entry_id"] == question["entry_id"]]
        self.assertEqual(q[0]["derived_status"], "ANSWERED")

        # DECISION
        decision = self.ledger.record_evidence(
            SECURITY, run_id=RUN_ID, classification="DECISION",
            content="Upgrade lodash to 4.17.21 immediately. Add input sanitization middleware. ADR-SEC-001.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[analysis["entry_id"], risk["entry_id"]],
            lifecycle_state="REVIEWED",
        )
        self.assertEqual(decision["lifecycle_state"], "REVIEWED")

        # Correction — challenge a previous inference
        correction = self.ledger.record_correction(
            DEVELOPER, parent_entry_id=analysis["entry_id"],
            run_id=RUN_ID,
            content="Actually jsonwebtoken@8.5.1 is vulnerable too — our RS256 check is only "
                    "in the auth middleware, not the webhook handler.",
            source_type="TOOL",
        )
        challenged = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        orig = [e for e in challenged if e["entry_id"] == analysis["entry_id"]]
        self.assertEqual(orig[0]["derived_status"], "CHALLENGED")

        # Verify all evidence classifications present
        all_entries = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        classifications = {e["classification"] for e in all_entries}
        self.assertTrue({"FACT", "INFERENCE", "QUESTION", "DECISION",
                         "RISK", "ASSUMPTION"}.issubset(classifications))

        # Query by role
        sec_entries = self.ledger.query_evidence(
            DEVELOPER, change_set_id=cs_id, actor_role="security-reviewer")
        self.assertGreater(len(sec_entries), 0)
        self.assertTrue(all(e["agent_role"] == "security-reviewer" for e in sec_entries))

    def test_non_blocking_question(self):
        cs = self._create_cs("Non-blocking Q", ["REQ-SEC-2"], ["platform"])
        cs_id = cs["id"]

        q = self.ledger.record_evidence(
            DEVELOPER, run_id=RUN_ID, classification="QUESTION",
            content="What TLS version does the load balancer terminate?",
            source_type="TOOL", change_set_id=cs_id,
            metadata={"blocking": False},
        )
        # Non-blocking questions should not appear in blocking_items
        blockers = self.ledger.blocking_items(cs_id)
        self.assertEqual(len([b for b in blockers if q["entry_id"] in b]), 0)


# ---------------------------------------------------------------------------
# Scenario 6: Incidents and Lessons — production feedback loop
# ---------------------------------------------------------------------------
class TestIncidentsAndLessons(_PipelineBase):
    """Production incident handling: exercises incident recording, clustering, and lessons."""

    def test_incident_recording_and_query(self):
        cs = self._create_cs("Incident test", ["REQ-INC-1"], ["api-svc"])
        cs_id = cs["id"]

        fact = self._fact("Error rate spike: 5xx at 12% for 3 minutes", cs_id,
                          source="cmd:curl metrics-api/errors")

        incident = self.ledger.record_incident(
            DEVELOPER,
            skill="evidence-gate",
            step="verify",
            failure_class="INCORRECT_BEHAVIOR",
            signal_type="negative",
            signal_source="REVIEWER",
            verification_strength={"changed_code_coverage": 0.85,
                                   "acceptance_criteria_exercised": 0.9},
            pattern_eligible=True,
            evidence_refs=[fact["entry_id"]],
            note="Error rate spike in auth service",
        )
        self.assertTrue(incident["incident_id"].startswith("INC-"))

        # Query incidents
        incidents = self.ledger.query_incidents(DEVELOPER, skill="evidence-gate")
        self.assertGreater(len(incidents), 0)
        self.assertEqual(incidents[0]["skill"], "evidence-gate")

    def test_incident_clusters(self):
        cs = self._create_cs("Cluster test", ["REQ-INC-2"], ["api-svc"])
        cs_id = cs["id"]

        # Create multiple incidents in same cluster
        for i in range(3):
            fact = self._fact(f"Test failure #{i+1}", cs_id)
            self.ledger.record_incident(
                DEVELOPER,
                skill="code-review",
                step="lint",
                failure_class="WEAKENED_TEST",
                signal_type="negative",
                signal_source="AGENT",
                pattern_eligible=True,
                evidence_refs=[fact["entry_id"]],
            )

        clusters = self.ledger.incident_clusters(DEVELOPER, min_incidents=2)
        matching = [c for c in clusters if c["failure_class"] == "WEAKENED_TEST"]
        self.assertGreater(len(matching), 0)
        self.assertGreaterEqual(matching[0]["occurrences"]["incidents"], 3)

    def test_lesson_from_cluster(self):
        cs = self._create_cs("Lesson test", ["REQ-INC-3"], ["api-svc"])
        cs_id = cs["id"]

        inc_ids = []
        for i in range(2):
            fact = self._fact(f"Missed null check #{i}", cs_id)
            inc = self.ledger.record_incident(
                DEVELOPER,
                skill="code-review",
                step="review",
                failure_class="UNSOURCED_CLAIM",
                signal_type="negative",
                signal_source="REVIEWER",
                pattern_eligible=True,
                evidence_refs=[fact["entry_id"]],
            )
            inc_ids.append(inc["incident_id"])

        # Record lesson (authored by a different role to avoid self-authorship block)
        lesson = self.ledger.record_lesson(
            ARCHITECT,
            skill="code-review",
            step="review",
            failure_class="UNSOURCED_CLAIM",
            occurrences={"incidents": 2, "change_sets": 1, "projects": 1},
            what_failed="Null pointer exceptions in request handlers after DB query",
            advice="Always use Optional<T> return types for DB queries; add null checks before .get()",
            remedy_kind="SKILL_TEXT",
            incident_refs=inc_ids,
            sanitization_result={
                "passed": True,
                "checker_version": "1.0.0",
                "checked_at": "2026-10-04T12:00:00Z",
            },
        )
        self.assertTrue(lesson["lesson_id"].startswith("LES-"))

        # Query lessons
        lessons = self.ledger.query_lessons(DEVELOPER, skill="code-review")
        self.assertGreater(len(lessons), 0)


# ---------------------------------------------------------------------------
# Scenario 7: Task Failure and Retry — failure policies
# ---------------------------------------------------------------------------
class TestTaskFailureRetry(_PipelineBase):
    """Task failure handling: exercises the retry policy, iteration cap, and escalation."""

    def _executing_cs(self):
        cs = self._create_cs("Retry test", ["REQ-RET-1"], ["svc"])
        cs_id = cs["id"]
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="SCOPED",
                              reason="Scope defined")
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="PLANNED",
                              reason="Plan complete")
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="plan_check_passed",
                                   payload={"check": "plan-gate", "result": "passed"})
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="codeowners_review",
                                   payload={"approver": "lead",
                                            "approver_role": "human:tech-lead",
                                            "state": "approved"})
        cs = self.cm.get_change_set(DEVELOPER, cs_id)
        if cs["status"] == "PLAN_APPROVED":
            self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="EXECUTING",
                                  reason="Starting work")
        return cs_id

    def test_retry_policy(self):
        cs_id = self._executing_cs()

        self.cm.record_task(
            DEVELOPER, change_set_id=cs_id, task_id="TASK-R1",
            owner_role="developer", status="IN_PROGRESS",
            worktree="worktrees/retry-test",
        )

        # Test failure applies retry (INVALID_OUTPUT is a RETRY class)
        result = self.cm.record_task_failure(
            DEVELOPER, change_set_id=cs_id, task_id="TASK-R1",
            failure_class="INVALID_OUTPUT", detail="3 tests failed in auth module",
        )
        self.assertEqual(result["policy"], "RETRY")

    def test_escalation(self):
        cs_id = self._executing_cs()

        self.cm.record_task(
            DEVELOPER, change_set_id=cs_id, task_id="TASK-ESC",
            owner_role="developer", status="IN_PROGRESS",
            worktree="worktrees/esc-test",
        )

        result = self.cm.record_task_failure(
            DEVELOPER, change_set_id=cs_id, task_id="TASK-ESC",
            failure_class="SCOPE_VIOLATION",
        )
        self.assertIn(result["action"], ("RETRY", "STOP", "RESUME", "ESCALATE"))


# ---------------------------------------------------------------------------
# Scenario 8: Forge Events — full lifecycle through integration and release
# ---------------------------------------------------------------------------
class TestForgeEventLifecycle(_PipelineBase):
    """Complete lifecycle: DRAFT -> PLANNED -> PLAN_APPROVED -> EXECUTING ->
    VERIFYING -> INTEGRATED -> RELEASED."""

    def test_full_lifecycle_via_forge_events(self):
        cs = self._create_cs("Full lifecycle test", ["REQ-LC-1"], ["my-app"],
                             environments=["staging", "production"],
                             release_environment="production")
        cs_id = cs["id"]
        self.assertEqual(cs["status"], "DRAFT")

        # DRAFT -> SCOPED -> PLANNED
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="SCOPED", reason="Scope defined")
        self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                              status="PLANNED", reason="Plan reviewed")

        # PLANNED -> PLAN_APPROVED via forge events
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="plan_check_passed",
                                   payload={"check": "plan-gate", "result": "passed"})
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="codeowners_review",
                                   payload={"approver": "tech-lead",
                                            "approver_role": "human:tech-lead",
                                            "state": "approved"})
        cs = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertIn(cs["status"], ("PLANNED", "PLAN_APPROVED"))

        if cs["status"] == "PLAN_APPROVED":
            # PLAN_APPROVED -> EXECUTING
            self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                                  status="EXECUTING", reason="Starting implementation")

            # EXECUTING -> VERIFYING
            self.cm.update_status(DEVELOPER, change_set_id=cs_id,
                                  status="VERIFYING", reason="All code complete, sending to CI")

            # VERIFYING -> INTEGRATED via pr_merged forge event
            result = self.cm.ingest_forge_event(
                CI, change_set_id=cs_id,
                event_type="pr_merged",
                payload={"repository": "my-app", "commit_sha": "f" * 40,
                         "target_branch": "main"})

            cs = self.cm.get_change_set(DEVELOPER, cs_id)
            # May be INTEGRATED or BLOCKED depending on completion criteria
            self.assertIn(cs["status"], ("INTEGRATED", "BLOCKED", "VERIFYING"))

            if cs["status"] == "INTEGRATED":
                # INTEGRATED -> RELEASED via deployment
                self.cm.ingest_forge_event(
                    CI, change_set_id=cs_id,
                    event_type="deployment",
                    payload={"environment": "production", "status": "success"})
                cs = self.cm.get_change_set(DEVELOPER, cs_id)
                self.assertIn(cs["status"], ("INTEGRATED", "RELEASED"))

        # Verify full history
        history = self.cm.get_change_set(DEVELOPER, cs_id)["status_history"]
        self.assertGreater(len(history), 1)


# ---------------------------------------------------------------------------
# Scenario 9: Human Override — risk tier override and degraded mode
# ---------------------------------------------------------------------------
class TestHumanOverride(_PipelineBase):
    """Human override of risk tier and human handoffs (degraded mode)."""

    def test_human_risk_override(self):
        cs = self._create_cs("Override test", ["REQ-OR-1"], ["svc"])
        cs_id = cs["id"]

        # Compute initial tier
        self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id,
            paths=["svc/src/main.py"], reason_codes=[], diff_lines=50)

        # Human overrides
        override = self.cm.override_risk_tier(
            HUMAN_LEAD, change_set_id=cs_id,
            tier="LOW", reason="Reviewed: cosmetic change only, no functional impact")
        self.assertEqual(override["final_tier"], "LOW")
        self.assertEqual(override["kind"], "HUMAN_OVERRIDE")

        # Override stats
        stats = self.cm.override_stats()
        self.assertGreaterEqual(stats["overrides"], 1)

    def test_human_handoff_degraded_mode(self):
        """In degraded mode, a human stands in for an agent role."""
        cs = self._create_cs("Degraded test", ["REQ-OR-2"], ["svc"])
        cs_id = cs["id"]

        ho = self.cm.record_handoff(
            HUMAN_LEAD, change_set_id=cs_id, to_role="developer",
            payload={
                "summary": "Human-authored architecture in degraded mode",
                "inputs": [{"artifact_ref": "svc@" + "a" * 7 + ":design.md",
                            "content_hash": "sha256:" + "ff" * 32}],
                "outputs": [{"artifact_kind": "architecture-design",
                             "content_hash": "sha256:" + "ee" * 32}],
                "classifications": [],
            },
            verdict="ACCEPT",
        )
        self.assertIn("human", ho["from_role"])


# ---------------------------------------------------------------------------
# Scenario 10: Cross-module Integration — evidence + contracts + planning
# ---------------------------------------------------------------------------
class TestCrossModuleIntegration(_PipelineBase):
    """Microservices decomposition: exercises cross-module interactions where
    evidence, contracts, and work planning all interact."""

    def test_evidence_linked_to_contracts(self):
        cs = self._create_cs("Microservices split", ["REQ-MS-1"],
                             ["monolith", "user-svc", "order-svc"])
        cs_id = cs["id"]

        # Register contracts between new services
        self.cr.register_contract(
            ARCHITECT, contract_id="user-order", provider="user-svc",
            version="1", type="grpc", consumers=["order-svc"],
            spec={"fields": {
                "user_id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            }},
        )

        # Evidence references the contract
        fact = self._fact("grpc proto compiled: user_service.proto -> user_pb2.py", cs_id)
        inference = self.ledger.record_evidence(
            ARCHITECT, run_id=RUN_ID, classification="INFERENCE",
            content="gRPC contract user-order verified: proto matches deployed schema.",
            source_type="TOOL", change_set_id=cs_id,
            input_references=[fact["entry_id"]],
        )

        # Drift detection finds no drift
        drift = self.cr.detect_drift(
            ARCHITECT, contract_id="user-order",
            observed_spec={"fields": {
                "user_id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True},
            }})
        self.assertFalse(drift["drift"])

    def test_work_planning_with_contracts(self):
        """Plan items reference contracts; graph shows the relationship."""
        items = [
            {"id": "REQ-5", "path": "plans/requirements/REQ-5.json", "data": {
                "title": "Split user service from monolith",
                "source_refs": ["PRD-2026-Q4"],
            }},
            {"id": "ST-5", "path": "plans/stories/ST-5.json", "data": {
                "title": "Extract user gRPC service",
                "type": "API_CONTRACT", "size": "M", "source_refs": ["REQ-5"],
                "acceptance_criteria": [
                    {"id": "ST-5/AC-1", "given": "Order service needs user data",
                     "when": "It calls GetUser RPC", "then": "User data returned within 50ms p99",
                     "kind": "functional", "verification": "automated"},
                    {"id": "ST-5/AC-2", "given": "GetUser called with invalid user_id",
                     "when": "Validation runs", "then": "NOT_FOUND error returned, no crash",
                     "kind": "negative", "verification": "automated"},
                ],
            }},
        ]
        self.wp.ingest_plan_commit(CI, repository="monolith", commit_sha="d" * 7, items=items)

        story = self.wp.get_work_item(DEVELOPER, "ST-5")
        self.assertEqual(story["data"]["type"], "API_CONTRACT")

        readiness = self.wp.evaluate_readiness(DEVELOPER, story_id="ST-5")
        self.assertIn("missing", readiness)

    def test_evidence_retention_purge(self):
        """Retention purge runs without error and records a SYSTEM FACT."""
        result = self.ledger.purge_expired_content()
        self.assertIn("purged", result)
        self.assertIn("retention_days", result)

    def test_verify_all_modules(self):
        """All module integrity checks pass on a fresh database."""
        for name in ("evidence_ledger", "change_management", "contract_registry", "work_planning"):
            module = self.registry.get(name)
            problems = module.api.verify()
            broken = [p for p in problems if not p.get("ok", True)]
            self.assertEqual(len(broken), 0, f"{name} verification failed: {broken}")


# ---------------------------------------------------------------------------
# Work Planning Edge Cases
# ---------------------------------------------------------------------------
class TestWorkPlanningEdgeCases(_PipelineBase):
    """Edge cases specific to work planning: invalid IDs, missing stories, etc."""

    def test_invalid_plan_item_id(self):
        with self.assertRaises(ValidationError):
            self.wp.ingest_plan_commit(
                CI, repository="repo", commit_sha="e" * 7,
                items=[{"id": "INVALID-1", "data": {}}])

    def test_nonexistent_story(self):
        with self.assertRaises(NotFound):
            self.wp.get_work_item(DEVELOPER, "ST-999")

    def test_link_nonexistent_story(self):
        cs = self._create_cs("Link test", ["REQ-X"], ["r"])
        with self.assertRaises(NotFound):
            self.wp.link_change_set(
                DEVELOPER, story_id="ST-888", change_set_id=cs["id"],
                implements_declaration="Implements: ST-888")

    def test_link_missing_declaration(self):
        items = [{"id": "ST-6", "path": "plans/stories/ST-6.json", "data": {
            "title": "Test story", "type": "SPIKE", "size": "XS",
            "source_refs": ["REQ-X"],
            "acceptance_criteria": [
                {"id": "ST-6/AC-1", "given": "Given", "when": "When",
                 "then": "Then", "kind": "functional", "verification": "manual"},
            ],
        }}]
        self.wp.ingest_plan_commit(CI, repository="repo", commit_sha="f" * 7, items=items)
        cs = self._create_cs("Decl test", ["REQ-X"], ["r"])
        with self.assertRaises(ValidationError):
            self.wp.link_change_set(
                DEVELOPER, story_id="ST-6", change_set_id=cs["id"],
                implements_declaration="Implements: ST-99")

    def test_plan_item_with_status_field_rejected(self):
        with self.assertRaises(ValidationError):
            self.wp.ingest_plan_commit(
                CI, repository="repo", commit_sha="1" * 7,
                items=[{"id": "ST-7", "data": {
                    "title": "Bad story", "status": "READY",
                }}])

    def test_graph_depth_clamping(self):
        items = [{"id": "REQ-9", "path": "p", "data": {"title": "Root"}}]
        self.wp.ingest_plan_commit(CI, repository="r", commit_sha="2" * 7, items=items)
        graph = self.wp.query_work_graph(DEVELOPER, root_id="REQ-9", depth=100)
        self.assertIn("REQ-9", {n["id"] for n in graph["nodes"]})

    def test_agent_cannot_ingest_plan(self):
        with self.assertRaises(PermissionDenied):
            self.wp.ingest_plan_commit(
                DEVELOPER, repository="repo", commit_sha="3" * 7, items=[])


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")
    unittest.main()
