"""MCP tool registration for the Event Journal. Actor identity comes from the session credential."""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.mcp_compat import register_tool


def register_tools(server: Any, api: Any, identity: Identity) -> list[str]:
    def append_journal(run_id: str, event_type: str, payload: dict[str, Any] | None = None,
                       change_set_id: str = "", visibility: str = "INTERNAL") -> dict[str, Any]:
        """Append a hash-chained event (e.g. task.start, stage.enter) to the run's journal."""
        return api.append_journal(identity, run_id=run_id, event_type=event_type, payload=payload,
                                  change_set_id=change_set_id, visibility=visibility)

    def fold_state(run_id: str) -> dict[str, Any]:
        """Reconstruct the run's work state (sessions with liveness, tasks, stage, decisions, intents, halt)."""
        return api.fold_state(run_id)

    def query_journal(run_id: str | None = None, change_set_id: str | None = None, event_type: str | None = None,
                      since: str | None = None, until: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Query journal entries by run, change set, event type and ISO time range."""
        return api.query_journal(run_id=run_id, change_set_id=change_set_id, event_type=event_type,
                                 since=since, until=until, limit=limit)

    def heartbeat(run_id: str, agent_role: str | None = None) -> dict[str, Any]:
        """Record a session.heartbeat so other sessions can see this one is alive."""
        return api.heartbeat(identity, run_id=run_id, agent_role=agent_role)

    annotations = {"query_journal": {"readOnlyHint": True}, "fold_state": {"readOnlyHint": True}}
    return [register_tool(server, fn, annotations.get(fn.__name__) or {"destructiveHint": False})
            for fn in (append_journal, fold_state, query_journal, heartbeat)]
