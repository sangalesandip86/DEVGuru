"""MCP tool registration for the Parallel Execution Coordinator."""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.mcp_compat import register_tool


def register_tools(server: Any, api: Any, identity: Identity) -> list[str]:
    def create_parallel_plan(change_set_id: str, items: list[dict[str, Any]],
                             max_workers: int = 8) -> dict[str, Any]:
        """Decompose a Change Set into parallel work items with planned files and roles."""
        return api.create_parallel_plan(identity, change_set_id=change_set_id,
                                        items=items, max_workers=max_workers)

    def start_worker(item_id: str, worktree_path: str = "") -> dict[str, Any]:
        """Launch a worker for a pending work item in an isolated worktree."""
        return api.start_worker(identity, item_id=item_id, worktree_path=worktree_path)

    def get_worker_status(plan_id: str) -> dict[str, Any]:
        """Get status of all workers in a parallel plan (running, completed, total counts)."""
        return api.get_worker_status(plan_id=plan_id)

    def integrate_results(plan_id: str) -> dict[str, Any]:
        """Merge completed worker results. Returns ready=false if items are still running."""
        return api.integrate_results(identity, plan_id=plan_id)

    def stop_all_workers(plan_id: str) -> dict[str, Any]:
        """Emergency stop: halt all pending and running workers in a parallel plan."""
        return api.stop_all_workers(identity, plan_id=plan_id)

    annotations = {"get_worker_status": {"readOnlyHint": True}}
    return [register_tool(server, fn, annotations.get(fn.__name__) or {"destructiveHint": False})
            for fn in (create_parallel_plan, start_worker, get_worker_status,
                       integrate_results, stop_all_workers)]
