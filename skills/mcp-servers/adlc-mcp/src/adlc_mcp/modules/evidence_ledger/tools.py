"""MCP tool registration for the Evidence Ledger (plan §6 Server 1).

The session identity is bound here; no tool takes actor_type / actor_id / agent_role / trust_level.
"""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.mcp_compat import register_tool


def register_tools(server: Any, ledger: Any, identity: Identity) -> list[str]:
    def record_evidence(
        run_id: str,
        classification: str,
        content: str,
        source_type: str,
        source: str | None = None,
        change_set_id: str | None = None,
        input_references: list[str] | None = None,
        output_references: list[str] | None = None,
        decision_ids: list[str] | None = None,
        lifecycle_state: str | None = None,
        snapshot_id: str | None = None,
        signal_source: str | None = None,
        metadata: dict[str, Any] | None = None,
        model_id: str | None = None,
        answers_entry_id: str | None = None,
    ) -> dict[str, Any]:
        """Append an evidence entry. Identity and trust_level are derived server-side.

        AGENT callers cannot write FACT (hooks do) and cannot set VERIFIED or APPROVED.
        QUESTION needs metadata.blocking; ASSUMPTION needs metadata.impact and metadata.expires_at.
        """
        return ledger.record_evidence(
            identity, run_id=run_id, classification=classification, content=content, source_type=source_type,
            source=source, change_set_id=change_set_id, input_references=input_references,
            output_references=output_references, decision_ids=decision_ids, lifecycle_state=lifecycle_state,
            snapshot_id=snapshot_id, signal_source=signal_source, metadata=metadata, model_id=model_id,
            answers_entry_id=answers_entry_id,
        )

    def query_evidence(
        change_set_id: str | None = None,
        actor_role: str | None = None,
        classification: str | None = None,
        trust_level: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read evidence entries (newest first) with derived OPEN/ANSWERED/EXPIRED/CHALLENGED status."""
        return ledger.query_evidence(
            identity, change_set_id=change_set_id, actor_role=actor_role, classification=classification,
            trust_level=trust_level, limit=limit,
        )

    def record_incident(
        skill: str,
        step: str,
        signal_type: str,
        signal_source: str,
        pattern_eligible: bool,
        evidence_refs: list[str],
        failure_class: str | None = None,
        verification_strength: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Record a self-improvement signal: skill/step/failure_class plus pointers to ledger entries.

        No use-case text. `note` (≤280 chars, one line) is only for judgment-only failures and is written
        by the reviewer or human who caught the failure, never by the agent role that failed.
        """
        return ledger.record_incident(
            identity, skill=skill, step=step, signal_type=signal_type, signal_source=signal_source,
            pattern_eligible=pattern_eligible, evidence_refs=evidence_refs, failure_class=failure_class,
            verification_strength=verification_strength, note=note,
        )

    def query_incidents(
        skill: str | None = None,
        step: str | None = None,
        failure_class: str | None = None,
        signal_type: str | None = None,
        signal_source: str | None = None,
        pattern_eligible_only: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read incidents as pointers and classes — never evidence content."""
        return ledger.query_incidents(
            identity, skill=skill, step=step, failure_class=failure_class, signal_type=signal_type,
            signal_source=signal_source, pattern_eligible_only=pattern_eligible_only, limit=limit,
        )

    def record_lesson(
        sanitization_result: dict[str, Any],
        scope: str = "PROJECT",
        skill: str | None = None,
        step: str | None = None,
        failure_class: str | None = None,
        occurrences: dict[str, int] | None = None,
        what_failed: str | None = None,
        advice: str | None = None,
        check: str | None = None,
        remedy_kind: str | None = None,
        reproduction_ref: str | None = None,
        incident_refs: list[str] | None = None,
        parent_lesson_id: str | None = None,
        approval_entry_id: str | None = None,
    ) -> dict[str, Any]:
        """Record a sanitized lesson for an incident cluster (scope PROJECT). Requires
        sanitization_result {passed: true, checker_version, checked_at}. Promotion to ORG (non-agent only)
        passes parent_lesson_id + approval_entry_id of a HUMAN APPROVED entry referencing the lesson."""
        fields = {k: v for k, v in {
            "sanitization_result": sanitization_result, "scope": scope, "skill": skill, "step": step,
            "failure_class": failure_class, "occurrences": occurrences, "what_failed": what_failed,
            "advice": advice, "check": check, "remedy_kind": remedy_kind, "reproduction_ref": reproduction_ref,
            "incident_refs": incident_refs, "parent_lesson_id": parent_lesson_id,
            "approval_entry_id": approval_entry_id,
        }.items() if v is not None}
        return ledger.record_lesson(identity, **fields)

    def query_lessons(
        skill: str | None = None,
        failure_class: str | None = None,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read lessons (with last_fired) filtered by skill, failure_class and scope."""
        return ledger.query_lessons(identity, skill=skill, failure_class=failure_class, scope=scope, limit=limit)

    def record_correction(
        parent_entry_id: str,
        run_id: str,
        content: str,
        source_type: str,
        source: str | None = None,
        classification: str = "INFERENCE",
        input_references: list[str] | None = None,
        signal_source: str | None = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        """Challenge a past entry by appending a new CHALLENGED entry — the original is never edited."""
        return ledger.record_correction(
            identity, parent_entry_id=parent_entry_id, run_id=run_id, content=content, source_type=source_type,
            source=source, classification=classification, input_references=input_references,
            signal_source=signal_source, model_id=model_id,
        )

    tools = [record_evidence, query_evidence, record_incident, query_incidents, record_correction,
             record_lesson, query_lessons]
    return [register_tool(server, fn) for fn in tools]
