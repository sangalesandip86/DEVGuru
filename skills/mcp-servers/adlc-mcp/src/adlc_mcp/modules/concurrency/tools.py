"""MCP tool registration for Concurrency Primitives."""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.mcp_compat import register_tool


def register_tools(server: Any, api: Any, identity: Identity) -> list[str]:
    def claim_task(task_id: str) -> dict[str, Any]:
        """Acquire exclusive ownership of a task (OS-level mutex). Returns holder info if already claimed."""
        return api.claim_task(identity, task_id=task_id)

    def release_task(task_id: str) -> dict[str, Any]:
        """Release a previously acquired task claim."""
        return api.release_task(identity, task_id=task_id)

    def declare_file_intent(files: list[str], ttl_minutes: int = 30,
                            change_set_id: str = "") -> dict[str, Any]:
        """Declare intent to modify files (advisory, not blocking). Other agents see the intent via check_conflicts."""
        return api.declare_file_intent(identity, files=files,
                                       ttl_minutes=ttl_minutes, change_set_id=change_set_id)

    def check_conflicts(planned_files: list[str]) -> dict[str, Any]:
        """Predict file and directory conflicts between planned modifications and active intents."""
        return api.check_conflicts(identity, planned_files=planned_files)

    def send_coordination_message(to_actor: str, content: str,
                                  change_set_id: str = "", intent_id: str = "") -> dict[str, Any]:
        """Send a coordination message to another agent about a conflict or intent."""
        return api.send_coordination_message(
            identity, to_actor=to_actor, content=content,
            change_set_id=change_set_id, intent_id=intent_id)

    annotations = {
        "check_conflicts": {"readOnlyHint": True},
    }
    return [register_tool(server, fn, annotations.get(fn.__name__) or {"destructiveHint": False})
            for fn in (claim_task, release_task, declare_file_intent, check_conflicts,
                       send_coordination_message)]
