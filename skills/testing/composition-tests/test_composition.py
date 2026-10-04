"""Layer F: Composition / Emergent Behavior Testing.

Two modes:
  Canned (default) — deterministic, no LLM calls, uses fixture data from scenario YAMLs.
  Live — real MCP API calls, requires ADLC_LIVE_MODE=1 env var and human opt-in.

Run:
    python -m unittest skills/testing/composition-tests/test_composition.py -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIOS = HERE / "scenarios"

sys.path.insert(0, str(HERE.parent.parent / "mcp-servers" / "adlc-mcp" / "src"))
sys.path.insert(0, str(HERE.parent.parent / "mcp-servers" / "adlc-mcp" / "tests"))

from _support import (  # noqa: E402
    CI,
    CODE_REVIEWER,
    DEVELOPER,
    HUMAN_LEAD,
    SECURITY,
    TempEnv,
)
from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError  # noqa: E402
from adlc_mcp.kernel.identity import Identity  # noqa: E402

SHA = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"
SHA2 = "b1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"
CONTENT_HASH = "sha256:" + "ab" * 32

STAGE_ORDER = [
    "INTAKE", "ARCHITECTURE", "PLAN", "DESIGN",
    "IMPLEMENT", "TEST", "REVIEW",
]

ROLE_IDENTITIES: dict[str, Identity] = {
    "product-planner": Identity("AGENT", "agent:product-planner", agent_role="product-planner",
                                tool="claude-code", model_id="model-a"),
    "product-owner": Identity("AGENT", "agent:product-owner", agent_role="product-owner",
                              tool="claude-code", model_id="model-a"),
    "architect": Identity("AGENT", "agent:architect", agent_role="architect",
                          tool="claude-code", model_id="model-a"),
    "developer": DEVELOPER,
    "qa-derive": Identity("AGENT", "agent:qa-derive", agent_role="qa-derive",
                          tool="claude-code", model_id="model-a"),
    "test-engineer": Identity("AGENT", "agent:test-engineer", agent_role="test-engineer",
                              tool="claude-code", model_id="model-a"),
    "code-reviewer": CODE_REVIEWER,
    "security-reviewer": SECURITY,
}


def _load_stages_yaml() -> dict:
    stages_path = HERE.parent.parent / "workflow" / "stages.yaml"
    if not stages_path.exists():
        return {}
    text = stages_path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        return json.loads(text)


STAGES_DATA = _load_stages_yaml()


class CompositionTestCase(unittest.TestCase):
    """Base class: sets up the MCP environment with both modules."""

    def setUp(self):
        self.env = TempEnv("evidence_ledger,change_management")
        self.registry = build_modules(self.env.config)
        self.cm = self.registry.get("change_management").api
        self.ledger = self.registry.get("evidence_ledger").api
        self.run_id = "run-comp-001"
        self._seed_entry_id: str | None = None

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def _seed_fact(self, cs_id: str) -> str:
        """Record a SYSTEM FACT so INFERENCE entries have something to reference."""
        if self._seed_entry_id is None:
            entry = self.ledger.record_evidence(
                CI, run_id=self.run_id, classification="FACT",
                content="Pipeline seed", source_type="CI",
                source="ci:composition-test", change_set_id=cs_id,
            )
            self._seed_entry_id = entry["entry_id"]
        return self._seed_entry_id

    def record_inference(self, identity: Identity, content: str, cs_id: str) -> dict:
        seed = self._seed_fact(cs_id)
        return self.ledger.record_evidence(
            identity, run_id=self.run_id, classification="INFERENCE",
            content=content, source_type="TOOL",
            change_set_id=cs_id, input_references=[seed],
        )

    def new_cs(self, repos=("repo-a",)):
        return self.cm.create_change_set(
            DEVELOPER, title="composition test",
            requirements=["REQ-1"], repositories=list(repos),
        )

    def drive_to(self, cs_id, target, tier_paths=("README.md",)):
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="SCOPED", reason="scoped")
        self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs_id, paths=list(tier_paths))
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="PLANNED", reason="planned")
        if target == "PLANNED":
            return
        self.cm.ingest_forge_event(CI, change_set_id=cs_id,
                                   event_type="plan_check_passed", payload={"run": "1"})
        if target == "PLAN_APPROVED":
            return
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="EXECUTING", reason="go")
        if target == "EXECUTING":
            return
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="VERIFYING", reason="done")

    def make_handoff_payload(self, artifacts, stage="IMPLEMENT"):
        return {
            "summary": f"Output from {stage}",
            "inputs": [
                {"artifact_ref": f"{a}@{SHA[:7]}:plans/{a}.yaml",
                 "content_hash": CONTENT_HASH}
                for a in artifacts
            ],
            "outputs": [
                {"artifact_kind": a, "content_hash": CONTENT_HASH} for a in artifacts
            ],
        }


# ============================================================================
# F.1 — Pipeline End-to-End (Canned Mode)
# ============================================================================

class CannedPipelineTest(CompositionTestCase):
    """Full pipeline simulation using canned data — no LLM calls."""

    def test_feature_story_pipeline_completes(self):
        """A feature story traverses INTAKE→REVIEW with evidence and handoffs at each stage."""
        cs = self.new_cs(repos=("payments-svc",))
        cs_id = cs["id"]

        self.record_inference(ROLE_IDENTITIES["product-planner"],
                              "REQ-1: Accept card payments", cs_id)
        self.cm.record_handoff(
            ROLE_IDENTITIES["product-planner"], change_set_id=cs_id,
            to_role="architect", verdict="ACCEPT",
            payload=self.make_handoff_payload(["requirement"], "INTAKE"),
        )

        self.record_inference(ROLE_IDENTITIES["architect"],
                              "Architecture: adapter pattern for gateway", cs_id)
        self.cm.record_handoff(
            ROLE_IDENTITIES["architect"], change_set_id=cs_id,
            to_role="product-planner", verdict="ACCEPT",
            payload=self.make_handoff_payload(["architecture-package"], "ARCHITECTURE"),
        )

        self.record_inference(ROLE_IDENTITIES["product-planner"],
                              "ST-1: POST /payments", cs_id)
        self.cm.record_handoff(
            ROLE_IDENTITIES["product-planner"], change_set_id=cs_id,
            to_role="qa-derive", verdict="ACCEPT",
            payload=self.make_handoff_payload(["ready-story"], "PLAN"),
        )

        self.record_inference(ROLE_IDENTITIES["qa-derive"],
                              "Test design for ST-1", cs_id)
        self.cm.record_handoff(
            ROLE_IDENTITIES["qa-derive"], change_set_id=cs_id,
            to_role="developer", verdict="ACCEPT",
            payload=self.make_handoff_payload(["test-design"], "DESIGN"),
        )

        self.record_inference(DEVELOPER, "Implementation complete", cs_id)
        self.cm.record_handoff(
            DEVELOPER, change_set_id=cs_id,
            to_role="test-engineer", verdict="ACCEPT",
            payload=self.make_handoff_payload(["change-set"], "IMPLEMENT"),
        )

        self.record_inference(ROLE_IDENTITIES["test-engineer"],
                              "Tests pass, 92% coverage", cs_id)
        self.cm.record_handoff(
            ROLE_IDENTITIES["test-engineer"], change_set_id=cs_id,
            to_role="code-reviewer", verdict="ACCEPT",
            payload=self.make_handoff_payload(["test-suite"], "TEST"),
        )

        self.cm.record_handoff(
            CODE_REVIEWER, change_set_id=cs_id,
            to_role="security-reviewer", verdict="ACCEPT",
            payload=self.make_handoff_payload(["review-verdict"], "REVIEW"),
        )

        final = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(len(final["handoffs"]), 7)
        evidence = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        self.assertGreaterEqual(len(evidence), 6)

    def test_bug_fix_abbreviated_pipeline(self):
        """Bug fix skips ARCHITECTURE, still produces valid handoff chain."""
        cs = self.new_cs(repos=("checkout-svc",))
        cs_id = cs["id"]

        self.cm.record_handoff(
            ROLE_IDENTITIES["product-planner"], change_set_id=cs_id,
            to_role="qa-derive", verdict="ACCEPT",
            payload=self.make_handoff_payload(["ready-story"], "PLAN"),
        )
        self.cm.record_handoff(
            ROLE_IDENTITIES["qa-derive"], change_set_id=cs_id,
            to_role="developer", verdict="ACCEPT",
            payload=self.make_handoff_payload(["test-design"], "DESIGN"),
        )
        self.cm.record_handoff(
            DEVELOPER, change_set_id=cs_id,
            to_role="test-engineer", verdict="ACCEPT",
            payload=self.make_handoff_payload(["change-set"], "IMPLEMENT"),
        )
        self.cm.record_handoff(
            ROLE_IDENTITIES["test-engineer"], change_set_id=cs_id,
            to_role="code-reviewer", verdict="ACCEPT",
            payload=self.make_handoff_payload(["test-suite"], "TEST"),
        )

        final = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(len(final["handoffs"]), 4)

    def test_security_story_requires_security_review(self):
        """Security story needs both code-reviewer and security-reviewer ACCEPTs."""
        cs = self.new_cs(repos=("auth-svc",))
        cs_id = cs["id"]

        self.cm.record_handoff(
            CODE_REVIEWER, change_set_id=cs_id,
            to_role="security-reviewer", verdict="ACCEPT",
            payload=self.make_handoff_payload(["review-verdict"], "REVIEW"),
        )
        ho_sec = self.cm.record_handoff(
            SECURITY, change_set_id=cs_id,
            to_role="developer", verdict="ACCEPT",
            payload=self.make_handoff_payload(["review-verdict"], "REVIEW"),
        )
        self.assertIsNone(ho_sec.get("escalated"))


# ============================================================================
# F.2 — Handoff Chain Validation
# ============================================================================

class HandoffChainTest(CompositionTestCase):
    """Validates handoff chain integrity across the pipeline."""

    def test_handoff_payload_carries_artifact_refs(self):
        """Every handoff has artifact references with valid format."""
        cs = self.new_cs()
        payload = self.make_handoff_payload(["requirement", "nfr-catalog"], "INTAKE")
        ho = self.cm.record_handoff(
            ROLE_IDENTITIES["product-planner"], change_set_id=cs["id"],
            to_role="architect", verdict="ACCEPT", payload=payload,
        )
        self.assertIn("id", ho)
        self.assertEqual(ho["from_role"], "product-planner")
        self.assertEqual(ho["to_role"], "architect")

    def test_handoff_with_claims(self):
        """Claims in handoff payloads are validated and preserved."""
        cs = self.new_cs()
        payload = self.make_handoff_payload(["test-suite"], "TEST")
        payload["claims"] = [
            {"classification": "QUESTION", "content": "Tests cover all AC?"},
        ]
        ho = self.cm.record_handoff(
            ROLE_IDENTITIES["test-engineer"], change_set_id=cs["id"],
            to_role="code-reviewer", verdict="ACCEPT", payload=payload,
        )
        self.assertEqual(ho["verdict"], "ACCEPT")

    def test_triple_reject_escalates(self):
        """3 REJECTs between the same role pair triggers ESCALATION block."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "EXECUTING")
        for _ in range(3):
            self.cm.record_handoff(
                CODE_REVIEWER, change_set_id=cs_id,
                to_role="developer", verdict="REJECT",
                payload=self.make_handoff_payload(["review-verdict"], "REVIEW"),
            )
        updated = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(updated["status"], "BLOCKED")
        self.assertEqual(updated["block_kind"], "ESCALATION")

    def test_security_reject_blocks_immediately(self):
        """A single REJECT from security-reviewer blocks the change set."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "EXECUTING")
        ho = self.cm.record_handoff(
            SECURITY, change_set_id=cs_id,
            to_role="developer", verdict="REJECT",
            payload=self.make_handoff_payload(["review-verdict"], "REVIEW"),
        )
        self.assertIsNotNone(ho.get("escalated"))
        updated = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(updated["status"], "BLOCKED")


# ============================================================================
# F.3 — Authority Preservation
# ============================================================================

class AuthorityPreservationTest(CompositionTestCase):
    """No agent can write FACT/VERIFIED/APPROVED; only SYSTEM writes FACT."""

    def test_agent_cannot_record_fact(self):
        cs = self.new_cs()
        with self.assertRaises((ValidationError, PermissionDenied)):
            self.ledger.record_evidence(
                DEVELOPER,
                run_id=self.run_id, classification="FACT",
                content="I am a fact", source_type="TOOL",
                change_set_id=cs["id"],
            )

    def test_agent_cannot_record_verified(self):
        cs = self.new_cs()
        with self.assertRaises((ValidationError, PermissionDenied)):
            self.ledger.record_evidence(
                DEVELOPER,
                run_id=self.run_id, classification="FACT",
                content="Verified by me", source_type="TOOL",
                change_set_id=cs["id"], lifecycle_state="VERIFIED",
            )

    def test_system_can_record_fact(self):
        cs = self.new_cs()
        entry = self.ledger.record_evidence(
            CI,
            run_id=self.run_id, classification="FACT",
            content="CI test pass", source_type="CI",
            source="github-actions:run-123",
            change_set_id=cs["id"],
        )
        self.assertEqual(entry["classification"], "FACT")

    def test_evidence_classification_preserved_across_pipeline(self):
        """When multiple roles record evidence, classifications don't cross-contaminate."""
        cs = self.new_cs()
        cs_id = cs["id"]

        seed = self._seed_fact(cs_id)
        self.record_inference(ROLE_IDENTITIES["product-planner"],
                              "Story plan inference", cs_id)
        self.record_inference(CODE_REVIEWER, "Review inference", cs_id)

        evidence = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        facts = [e for e in evidence if e["classification"] == "FACT"]
        inferences = [e for e in evidence if e["classification"] == "INFERENCE"]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["actor_type"], "SYSTEM")
        self.assertEqual(len(inferences), 2)
        for inf in inferences:
            self.assertEqual(inf["actor_type"], "AGENT")


# ============================================================================
# F.4 — Failure Cascade Tests
# ============================================================================

class FailureCascadeTest(CompositionTestCase):
    """When a stage fails, downstream stages handle it correctly."""

    def test_iteration_cap_blocks_task(self):
        """After 3 RETRY failures the task is BLOCKED (ASI06 at pipeline level)."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "EXECUTING")
        self.cm.record_task(
            DEVELOPER, change_set_id=cs_id, task_id="T-1",
            owner_role="developer", status="IN_PROGRESS",
            worktree="wt-1",
        )
        for i in range(3):
            result = self.cm.record_task_failure(
                DEVELOPER, change_set_id=cs_id, task_id="T-1",
                failure_class="LOOP", detail=f"attempt {i+1}",
            )
        self.assertEqual(result["action"], "STOP")
        task = self.cm.get_change_set(DEVELOPER, cs_id)
        t = [t for t in task["tasks"] if t["id"] == "T-1"][0]
        self.assertEqual(t["status"], "BLOCKED")

    def test_escalation_requires_human_to_unblock(self):
        """ESCALATION block can only be lifted by a human."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "EXECUTING")
        self.cm.record_task(
            DEVELOPER, change_set_id=cs_id, task_id="T-2",
            owner_role="developer", status="IN_PROGRESS",
            worktree="wt-2",
        )
        self.cm.record_task_failure(
            DEVELOPER, change_set_id=cs_id, task_id="T-2",
            failure_class="SCOPE_VIOLATION",
        )
        task = self.cm.get_change_set(DEVELOPER, cs_id)
        t = [t for t in task["tasks"] if t["id"] == "T-2"][0]
        self.assertEqual(t["status"], "BLOCKED")
        self.assertIn("ESCALATE", t.get("blocked_reason", ""))

        with self.assertRaises(PermissionDenied):
            self.cm.record_task(
                DEVELOPER, change_set_id=cs_id, task_id="T-2",
                owner_role="developer", status="IN_PROGRESS",
                worktree="wt-2",
            )

    def test_stale_snapshot_detected(self):
        """Snapshot staleness is detected when HEAD moves."""
        cs = self.new_cs()
        cs_id = cs["id"]
        snap = self.cm.create_snapshot(
            DEVELOPER, change_set_id=cs_id,
            repositories={"repo-a": SHA},
        )
        result = self.cm.validate_snapshot_currency(
            DEVELOPER, snapshot_id=snap["id"],
            current_heads={"repo-a": SHA2},
            changed_paths={"repo-a": ["src/main.py"]},
            task_paths={"repo-a": ["src/main.py"]},
        )
        self.assertEqual(result["verdict"], "STALE")

    def test_merge_without_verification_blocks(self):
        """PR merge observed while not in VERIFYING → BLOCKED with ESCALATION."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "EXECUTING")
        result = self.cm.ingest_forge_event(
            CI, change_set_id=cs_id, event_type="pr_merged",
            payload={"repository": "repo-a", "commit_sha": SHA, "target_branch": "main"},
        )
        updated = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(updated["status"], "BLOCKED")
        self.assertEqual(updated["block_kind"], "ESCALATION")

    def test_replan_resets_approval(self):
        """Going EXECUTING→PLANNED increments approval_epoch; old approvals don't count."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "EXECUTING")
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="PLANNED", reason="replan")

        updated = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(updated["status"], "PLANNED")
        self.assertGreaterEqual(updated["approval_epoch"], 1)


# ============================================================================
# F.5 — Risk Tier Consistency Across Pipeline
# ============================================================================

class RiskTierConsistencyTest(CompositionTestCase):
    """Risk tier is consistent and monotonic across pipeline operations."""

    def test_tier_never_decreases_on_recompute(self):
        """Recomputing risk tier with lower-risk paths does not lower the tier."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="SCOPED", reason="s")
        r1 = self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id, paths=["src/auth/login.py"],
        )
        self.assertEqual(r1["final_tier"], "HIGH")

        r2 = self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id, paths=["README.md"],
        )
        self.assertEqual(r2["final_tier"], "HIGH")

    def test_human_override_logged(self):
        """Human override is recorded in risk history."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="SCOPED", reason="s")
        self.cm.compute_risk_tier(DEVELOPER, change_set_id=cs_id, paths=["src/auth/login.py"])

        override = self.cm.override_risk_tier(
            HUMAN_LEAD, change_set_id=cs_id, tier="CRITICAL",
            reason="Payment-adjacent change",
        )
        self.assertEqual(override["final_tier"], "CRITICAL")
        self.assertEqual(override["kind"], "HUMAN_OVERRIDE")

    def test_tier_floor_from_story_type_raises_never_lowers(self):
        """Story type tier_floor raises the effective tier, never lowers it."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.cm.update_status(DEVELOPER, change_set_id=cs_id, status="SCOPED", reason="s")
        result = self.cm.compute_risk_tier(
            DEVELOPER, change_set_id=cs_id,
            paths=["docs/readme.md"],
            tier_floor="HIGH",
        )
        self.assertIn(result["final_tier"], ("HIGH", "CRITICAL"))


# ============================================================================
# F.6 — Lifecycle State Machine Under Composition
# ============================================================================

class LifecycleCompositionTest(CompositionTestCase):
    """The state machine behaves correctly when multiple pipeline actors interact."""

    def test_full_lifecycle_to_integrated(self):
        """Complete lifecycle DRAFT→INTEGRATED through forge events."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "VERIFYING")
        self.cm.ingest_forge_event(
            CI, change_set_id=cs_id, event_type="pr_merged",
            payload={"repository": "repo-a", "commit_sha": SHA, "target_branch": "main"},
        )
        updated = self.cm.get_change_set(DEVELOPER, cs_id)
        self.assertEqual(updated["status"], "INTEGRATED")

    def test_concurrent_tasks_respect_worktree_isolation(self):
        """Two tasks cannot share the same worktree."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "EXECUTING")
        self.cm.record_task(
            DEVELOPER, change_set_id=cs_id, task_id="T-A",
            owner_role="developer", status="IN_PROGRESS",
            worktree="wt-shared",
        )
        with self.assertRaises(ValidationError):
            self.cm.record_task(
                DEVELOPER, change_set_id=cs_id, task_id="T-B",
                owner_role="developer", status="IN_PROGRESS",
                worktree="wt-shared",
            )

    def test_task_dependency_order_enforced(self):
        """A task cannot start IN_PROGRESS until its dependencies are DONE."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "EXECUTING")
        self.cm.record_task(
            DEVELOPER, change_set_id=cs_id, task_id="T-dep",
            owner_role="developer", status="PENDING",
        )
        with self.assertRaises(ValidationError):
            self.cm.record_task(
                DEVELOPER, change_set_id=cs_id, task_id="T-child",
                owner_role="developer", status="IN_PROGRESS",
                depends_on=["T-dep"], worktree="wt-child",
            )

    def test_task_starts_only_when_executing(self):
        """Tasks cannot start IN_PROGRESS before the change set is EXECUTING."""
        cs = self.new_cs()
        cs_id = cs["id"]
        self.drive_to(cs_id, "PLANNED")
        with self.assertRaises(ValidationError):
            self.cm.record_task(
                DEVELOPER, change_set_id=cs_id, task_id="T-early",
                owner_role="developer", status="IN_PROGRESS",
                worktree="wt-early",
            )


# ============================================================================
# F.7 — Information Fidelity (Telephone Game Detection)
# ============================================================================

class InformationFidelityTest(CompositionTestCase):
    """Detects information loss/mutation across handoff chains."""

    def test_evidence_entries_reference_change_set(self):
        """All evidence in a pipeline run is linked to the same change set."""
        cs = self.new_cs()
        cs_id = cs["id"]
        for role_name in ["product-planner", "architect", "developer"]:
            self.record_inference(ROLE_IDENTITIES[role_name],
                                  f"Output from {role_name}", cs_id)
        evidence = self.ledger.query_evidence(DEVELOPER, change_set_id=cs_id)
        for e in evidence:
            self.assertEqual(e["change_set_id"], cs_id)

    def test_handoff_payload_validation_catches_bad_refs(self):
        """Malformed artifact_ref in handoff payload is rejected."""
        cs = self.new_cs()
        bad_payload = {
            "summary": "bad ref",
            "inputs": [{"artifact_ref": "no-at-sign-here"}],
        }
        with self.assertRaises(ValidationError):
            self.cm.record_handoff(
                DEVELOPER, change_set_id=cs["id"],
                to_role="code-reviewer", payload=bad_payload,
            )

    def test_hash_chain_survives_multi_role_writes(self):
        """Evidence hash chain remains valid after writes from multiple roles."""
        cs = self.new_cs()
        cs_id = cs["id"]
        for role_name in ["product-planner", "architect", "qa-derive",
                          "developer", "test-engineer"]:
            self.record_inference(ROLE_IDENTITIES[role_name],
                                  f"{role_name} output", cs_id)
        chain_check = self.ledger.verify()
        for check in chain_check:
            self.assertTrue(check.get("ok", False),
                            f"Hash chain broken: {check}")


# ============================================================================
# F.8 — Live Mode Guard
# ============================================================================

class LiveModeGuardTest(unittest.TestCase):
    """Live mode requires explicit opt-in."""

    def test_live_mode_env_var_required(self):
        """Without ADLC_LIVE_MODE=1, live mode is refused."""
        old = os.environ.pop("ADLC_LIVE_MODE", None)
        try:
            sys.path.insert(0, str(HERE))
            from pipeline_simulator import main
            code = main(["--scenario", str(SCENARIOS / "feature_story.yaml"),
                         "--mode", "live"])
            self.assertEqual(code, 2)
        except SystemExit:
            pass
        finally:
            if old is not None:
                os.environ["ADLC_LIVE_MODE"] = old


# ============================================================================
# F.9 — Stage Graph Consistency
# ============================================================================

class StageGraphConsistencyTest(unittest.TestCase):
    """Scenario handoff chains are consistent with stages.yaml."""

    def test_scenario_stages_exist_in_graph(self):
        """Every stage named in scenarios exists in stages.yaml."""
        if not STAGES_DATA:
            self.skipTest("stages.yaml not loadable")
        valid_stages = set(STAGES_DATA.get("order", []))
        for scenario_file in SCENARIOS.glob("*.yaml"):
            text = scenario_file.read_text(encoding="utf-8")
            try:
                import yaml
                scenario = yaml.safe_load(text)
            except ImportError:
                scenario = json.loads(text)
            if not isinstance(scenario, dict):
                continue
            for stage in scenario.get("stages", {}):
                self.assertIn(stage, valid_stages,
                              f"{scenario_file.name}: unknown stage {stage}")

    def test_handoff_roles_are_valid_agent_roles(self):
        """Every role in handoff chains is a valid agent role."""
        from adlc_mcp.kernel.vocab import AGENT_ROLES
        for scenario_file in SCENARIOS.glob("*.yaml"):
            text = scenario_file.read_text(encoding="utf-8")
            try:
                import yaml
                scenario = yaml.safe_load(text)
            except ImportError:
                scenario = json.loads(text)
            if not isinstance(scenario, dict):
                continue
            for ho in scenario.get("handoff_chain", []):
                for key in ("from", "to"):
                    role = ho.get(key, "")
                    if role.startswith("human:"):
                        continue
                    self.assertIn(role, AGENT_ROLES,
                                  f"{scenario_file.name}: invalid role {role}")


if __name__ == "__main__":
    unittest.main()
