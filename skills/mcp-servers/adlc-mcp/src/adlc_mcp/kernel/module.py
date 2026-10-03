"""The contract every module implements, so the composition root can host it in-process
or a standalone process can host it alone (the extraction path)."""
from __future__ import annotations

import sqlite3
from typing import Any, Protocol, runtime_checkable

from .identity import Identity


@runtime_checkable
class Module(Protocol):
    name: str

    def migrate(self, conn: sqlite3.Connection) -> None:
        """Create/upgrade this module's own tables in its own database file."""

    def register_tools(self, server: Any, identity: Identity) -> list[str]:
        """Register this module's MCP tools for ``identity``; return the tool names registered.

        Register only the tools the identity may call (role-appropriate tool surface). The
        module's API re-checks authorization regardless — registration is not the control.
        """

    @property
    def api(self) -> Any:
        """The module's public facade (the object other modules reach through a port)."""

    def close(self) -> None: ...


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}

    def add(self, module: Module) -> None:
        if module.name in self._modules:
            raise ValueError(f"module already registered: {module.name}")
        self._modules[module.name] = module

    def get(self, name: str) -> Module:
        return self._modules[name]

    def __contains__(self, name: str) -> bool:
        return name in self._modules

    def __iter__(self):
        return iter(self._modules.values())

    def names(self) -> list[str]:
        return list(self._modules)

    def close(self) -> None:
        for m in self._modules.values():
            m.close()
