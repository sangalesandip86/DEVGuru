"""MCP tool registration for the Stage Transition Engine."""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.mcp_compat import register_tool


def register_tools(server: Any, api: Any, identity: Identity) -> list[str]:
    def get_transition_graph() -> dict[str, Any]:
        """Return the declarative stage transition graph (stages, allowed transitions, gates, side states)."""
        return api.get_transition_graph()

    def validate_transition(change_set_id: str, from_stage: str, to_stage: str,
                            actor_role: str, outputs: list[str] | None = None) -> dict[str, Any]:
        """Check if a proposed stage transition is allowed given current state, role, and outputs."""
        return api.validate_transition(
            change_set_id=change_set_id, from_stage=from_stage,
            to_stage=to_stage, actor_role=actor_role, outputs=outputs)

    def record_transition(change_set_id: str, from_stage: str, to_stage: str,
                          outputs: list[str] | None = None,
                          evidence_ids: list[str] | None = None) -> dict[str, Any]:
        """Record an executed stage transition with evidence. Invalid transitions are recorded as VIOLATION events."""
        return api.record_transition(
            identity, change_set_id=change_set_id, from_stage=from_stage,
            to_stage=to_stage, outputs=outputs, evidence_ids=evidence_ids)

    def get_current_stage(change_set_id: str) -> dict[str, Any]:
        """Return the current stage, allowed next transitions, required outputs, and gate status for a Change Set."""
        return api.get_current_stage(change_set_id=change_set_id)

    annotations = {
        "get_transition_graph": {"readOnlyHint": True},
        "validate_transition": {"readOnlyHint": True},
        "get_current_stage": {"readOnlyHint": True},
    }
    return [register_tool(server, fn, annotations.get(fn.__name__) or {"destructiveHint": False})
            for fn in (get_transition_graph, validate_transition, record_transition, get_current_stage)]
