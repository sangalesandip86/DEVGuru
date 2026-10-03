"""MCP tool registration for Change Management (plan §6 Server 2).

Role-appropriate surface: ``ingest_forge_event`` is registered only for SYSTEM sessions and
``override_risk_tier`` only for HUMAN sessions. The API re-checks both regardless.
"""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.mcp_compat import register_tool


def register_tools(server: Any, api: Any, identity: Identity) -> list[str]:
    def create_change_set(
        title: str,
        requirements: list[str],
        repositories: list[str],
        contracts: list[str] | None = None,
        environments: list[str] | None = None,
        system: str | None = None,
        initiative: str | None = None,
        parent_id: str | None = None,
        depends_on: list[str] | None = None,
        release_environment: str = "production",
        story_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a Change Set in DRAFT (multi-repo / parallel work; single-repo work is issue + PR)."""
        return api.create_change_set(
            identity, title=title, requirements=requirements, repositories=repositories, contracts=contracts,
            environments=environments, system=system, initiative=initiative, parent_id=parent_id,
            depends_on=depends_on, release_environment=release_environment, story_refs=story_refs,
        )

    def get_change_set(change_set_id: str) -> dict[str, Any]:
        """Read a Change Set with tasks[], checkpoints, snapshot, dependencies, risk and status history."""
        return api.get_change_set(identity, change_set_id)

    def update_status(change_set_id: str, status: str, reason: str, block_kind: str | None = None) -> dict[str, Any]:
        """Transition status per the lifecycle. PLAN_APPROVED/INTEGRATED/RELEASED/ROLLED_BACK are rejected —
        they come only from observed forge events. BLOCKED needs block_kind (GATE_FAILED|DEPENDENCY_UNMET|ESCALATION)."""
        return api.update_status(identity, change_set_id=change_set_id, status=status, reason=reason,
                                 block_kind=block_kind)

    def ingest_forge_event(change_set_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """SYSTEM-only: record an observed forge/CI event and apply the resulting transition."""
        return api.ingest_forge_event(identity, change_set_id=change_set_id, event_type=event_type, payload=payload)

    def create_snapshot(
        change_set_id: str,
        repositories: dict[str, str],
        contracts: dict[str, str] | None = None,
        environments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Pin commit SHAs (every repo), contract versions and environment state."""
        return api.create_snapshot(identity, change_set_id=change_set_id, repositories=repositories,
                                   contracts=contracts, environments=environments)

    def validate_snapshot_currency(
        snapshot_id: str,
        current_heads: dict[str, str],
        changed_paths: dict[str, list[str]] | None = None,
        task_paths: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """Report staleness: path overlap plus always-overlap path classes. Unknown → STALE."""
        return api.validate_snapshot_currency(identity, snapshot_id=snapshot_id, current_heads=current_heads,
                                              changed_paths=changed_paths, task_paths=task_paths)

    def record_dependency(
        change_set_id: str,
        source: str,
        target: str,
        type: str,
        confidence: float,
        evidence_level: str,
        resolved: bool = False,
    ) -> dict[str, Any]:
        """Record a discovered dependency (evidence_level DECLARED|STATIC|OBSERVED). Default UNRESOLVED."""
        return api.record_dependency(identity, change_set_id=change_set_id, source=source, target=target, type=type,
                                     confidence=confidence, evidence_level=evidence_level, resolved=resolved)

    def compute_risk_tier(
        change_set_id: str,
        paths: list[str],
        reason_codes: list[str] | None = None,
        assessed_tiers: list[str] | None = None,
        tier_floor: str | None = None,
        diff_lines: int | None = None,
    ) -> dict[str, Any]:
        """Compute the tier: path tiers, higher-wins on disagreement, +1 level for named reason codes,
        HIGH when uncomputable, never lower than before. Flags decomposition above the diff-size cap."""
        return api.compute_risk_tier(identity, change_set_id=change_set_id, paths=paths, reason_codes=reason_codes,
                                     assessed_tiers=assessed_tiers, tier_floor=tier_floor, diff_lines=diff_lines)

    def override_risk_tier(change_set_id: str, tier: str, reason: str) -> dict[str, Any]:
        """HUMAN-only: override the tier. Every downgrade is logged."""
        return api.override_risk_tier(identity, change_set_id=change_set_id, tier=tier, reason=reason)

    def record_handoff(
        change_set_id: str,
        to_role: str,
        payload: dict[str, Any],
        verdict: str | None = None,
        domain: str | None = None,
    ) -> dict[str, Any]:
        """Store a typed handoff. from_role comes from the credential. inputs[].artifact_ref = repo@sha:path."""
        return api.record_handoff(identity, change_set_id=change_set_id, to_role=to_role, payload=payload,
                                  verdict=verdict, domain_name=domain)

    def record_task(
        change_set_id: str,
        task_id: str,
        owner_role: str,
        depends_on: list[str] | None = None,
        worktree: str | None = None,
        status: str = "PENDING",
        ac_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create/update a task in the Change Set's tasks[]. A running task needs its own worktree."""
        return api.record_task(identity, change_set_id=change_set_id, task_id=task_id, owner_role=owner_role,
                               depends_on=depends_on, worktree=worktree, status=status, ac_refs=ac_refs)

    def checkpoint_task(change_set_id: str, task_id: str, commit_sha: str, ledger_cursor: str,
                        snapshot_id: str) -> dict[str, Any]:
        """Checkpoint a task (commit_sha, ledger_cursor, snapshot_id) for resumability."""
        return api.checkpoint_task(identity, change_set_id=change_set_id, task_id=task_id, commit_sha=commit_sha,
                                   ledger_cursor=ledger_cursor, snapshot_id=snapshot_id)

    def record_task_failure(change_set_id: str, task_id: str, failure_class: str, detail: str = "") -> dict[str, Any]:
        """Apply the per-failure-class retry policy and return the action (RETRY|STOP|ESCALATE|REPLAN|RESUME)."""
        return api.record_task_failure(identity, change_set_id=change_set_id, task_id=task_id,
                                       failure_class=failure_class, detail=detail)

    tools = [create_change_set, get_change_set, update_status, create_snapshot, validate_snapshot_currency,
             record_dependency, compute_risk_tier, record_handoff, record_task, checkpoint_task, record_task_failure]
    if identity.is_system:
        tools.append(ingest_forge_event)
    if identity.is_human:
        tools.append(override_risk_tier)
    return [register_tool(server, fn) for fn in tools]
