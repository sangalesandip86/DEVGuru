"""Server-side role→tool permissions (finding B5: register_tools must not register everything).

Loaded from ``role_tool_permissions.json`` (the single source of truth).
Only ``mcp:adlc.*`` tools are scoped here; file tools (read/edit/search) are
enforced client-side by managed settings. SYSTEM and HUMAN identities bypass filtering.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .identity import Identity

_JSON = Path(__file__).with_name("role_tool_permissions.json")
_DATA = json.loads(_JSON.read_text(encoding="utf-8"))

ROLE_TOOLS: dict[str, frozenset[str]] = {
    role: frozenset(tools) for role, tools in _DATA["roles"].items()
}

_EMPTY: frozenset[str] = frozenset()


def allowed_tools(identity: "Identity") -> frozenset[str] | None:
    """Return the set of allowed MCP tool names for this identity, or None for unrestricted."""
    if not identity.is_agent:
        return None
    return ROLE_TOOLS.get(identity.agent_role or "", _EMPTY)
