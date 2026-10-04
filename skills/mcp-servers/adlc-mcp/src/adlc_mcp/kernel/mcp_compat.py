"""Thin compatibility layer over the optional MCP SDK, so modules never import it directly.

``register_tool`` maps platform errors (AdlcError) to the SDK's ToolError so the *reason* for a
refusal — e.g. "AGENT callers cannot write FACT entries" — reaches the agent instead of a generic
"error executing tool". Works with mcp>=2 (MCPServer), mcp 1.x (FastMCP) and the test recorder.
"""
from __future__ import annotations

import functools
from typing import Any, Callable

from .errors import AdlcError


def _tool_error_type() -> type[Exception] | None:
    for path in ("mcp.server.mcpserver.exceptions", "mcp.server.fastmcp.exceptions"):
        try:
            module = __import__(path, fromlist=["ToolError"])
            return module.ToolError
        except ImportError:
            continue
    return None


TOOL_ANNOTATIONS: dict[str, dict[str, bool]] = {
    "query_evidence":           {"readOnlyHint": True},
    "query_incidents":          {"readOnlyHint": True},
    "query_lessons":            {"readOnlyHint": True},
    "get_change_set":           {"readOnlyHint": True},
    "validate_snapshot_currency": {"readOnlyHint": True},
    "compute_risk_tier":        {"readOnlyHint": True},
    "check_compatibility":      {"readOnlyHint": True},
    "detect_drift":             {"readOnlyHint": True},
    "work_graph":               {"readOnlyHint": True},
    "evaluate_story":           {"readOnlyHint": True},
    "record_evidence":          {"destructiveHint": False},
    "record_correction":        {"destructiveHint": False},
    "record_incident":          {"destructiveHint": False},
    "record_lesson":            {"destructiveHint": False},
    "record_handoff":           {"destructiveHint": False},
    "record_task":              {"destructiveHint": False},
    "record_dependency":        {"destructiveHint": False},
    "create_change_set":        {"destructiveHint": False},
    "create_snapshot":          {"destructiveHint": False},
    "update_status":            {"destructiveHint": False},
    "override_risk_tier":       {"destructiveHint": False},
    "checkpoint_task":          {"destructiveHint": False},
    "record_task_failure":      {"destructiveHint": False},
    "ingest_forge_event":       {"destructiveHint": False},
    "register_contract":        {"destructiveHint": False},
    "ingest_work_event":        {"destructiveHint": False},
    "link_pr":                  {"destructiveHint": False},
}


def register_tool(server: Any, fn: Callable[..., Any], annotations: dict[str, bool] | None = None) -> str:
    tool_error = _tool_error_type()

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except AdlcError as exc:
            if tool_error is None:
                raise
            raise tool_error(f"{type(exc).__name__}: {exc}") from exc

    hints = annotations or TOOL_ANNOTATIONS.get(fn.__name__)
    kwargs: dict[str, Any] = {"name": fn.__name__, "description": fn.__doc__}
    if hints:
        kwargs["annotations"] = hints
    try:
        server.tool(**kwargs)(wrapper)
    except TypeError:
        server.tool(name=fn.__name__, description=fn.__doc__)(wrapper)
    return fn.__name__
