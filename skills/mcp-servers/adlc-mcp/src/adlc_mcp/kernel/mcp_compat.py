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


def register_tool(server: Any, fn: Callable[..., Any]) -> str:
    tool_error = _tool_error_type()

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except AdlcError as exc:
            if tool_error is None:
                raise
            raise tool_error(f"{type(exc).__name__}: {exc}") from exc

    server.tool(name=fn.__name__, description=fn.__doc__)(wrapper)
    return fn.__name__
