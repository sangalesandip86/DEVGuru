"""MCP tool registration for Work Planning (plan v3.1 §6 Module 4).

There is no tool that sets a story status. Ingestion tools are registered only for SYSTEM
sessions (the CI plan-projection job); the API re-checks regardless.
"""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.mcp_compat import register_tool


def register_tools(server: Any, api: Any, identity: Identity) -> list[str]:
    def get_work_item(item_id: str) -> dict[str, Any]:
        """Read a requirement, epic, feature, story or milestone (as of the last ingested plan commit)
        with its derived status."""
        return api.get_work_item(identity, item_id)

    def query_work_graph(root_id: str, relations: list[str] | None = None, depth: int = 3) -> dict[str, Any]:
        """Traverse scope/time/depends_on relations and Story ↔ Change Set (implements) links."""
        return api.query_work_graph(identity, root_id=root_id, relations=relations, depth=depth)

    def evaluate_readiness(story_id: str) -> dict[str, Any]:
        """Dry-run the Definition of Ready; returns missing evidence item by item. Never changes status."""
        return api.evaluate_readiness(identity, story_id=story_id)

    def evaluate_done(story_id: str) -> dict[str, Any]:
        """Dry-run the Definition of Done; returns missing evidence item by item. Never changes status."""
        return api.evaluate_done(identity, story_id=story_id)

    def link_change_set(story_id: str, change_set_id: str, implements_declaration: str) -> dict[str, Any]:
        """Record a Story ↔ Change Set link, validated against the PR body's `Implements: ST-n` line."""
        return api.link_change_set(identity, story_id=story_id, change_set_id=change_set_id,
                                   implements_declaration=implements_declaration)

    def ingest_plan_commit(repository: str, commit_sha: str, items: list[dict[str, Any]],
                           full_snapshot: bool = True) -> dict[str, Any]:
        """SYSTEM-only: ingest a merged plan commit ([{id, path, data}]); recompute AC hashes and statuses."""
        return api.ingest_plan_commit(identity, repository=repository, commit_sha=commit_sha, items=items,
                                      full_snapshot=full_snapshot)

    def ingest_work_event(story_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """SYSTEM-only: record an observed readiness_gate / completion_gate / pr_opened / po_acceptance /
        cancelled / split event."""
        return api.ingest_work_event(identity, story_id=story_id, event_type=event_type, payload=payload)

    tools = [get_work_item, query_work_graph, evaluate_readiness, evaluate_done, link_change_set]
    if identity.is_system:
        tools += [ingest_plan_commit, ingest_work_event]
    return [register_tool(server, fn) for fn in tools]
