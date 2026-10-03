"""Composition root: the ONLY place that knows more than one module.

Builds the enabled modules (``ADLC_MODULES``), wires cross-module dependencies through
ports, and hosts every module's tools on one FastMCP server named ``adlc``.

Extraction recipe (docs/adr/0001-mcp-modular-monolith.md): to run a module as its own server,
start it with ``--modules <name>`` and replace the in-process adapter below with a remote
client implementing the same port. Tool names do not change.
"""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.config import Config
from adlc_mcp.kernel.identity import Identity, system_identity
from adlc_mcp.kernel.module import ModuleRegistry
from adlc_mcp.modules.change_management import api as change_management_api
from adlc_mcp.modules.contract_registry import api as contract_registry_api
from adlc_mcp.modules.evidence_ledger import api as evidence_ledger_api
from adlc_mcp.modules.work_planning import api as work_planning_api

SERVER_NAME = "adlc"


# --------------------------------------------------------------------------- in-process adapters
class LedgerEvidenceAdapter:
    """Satisfies change_management's EvidencePort with the in-process Evidence Ledger."""

    def __init__(self, ledger: evidence_ledger_api.EvidenceLedger) -> None:
        self._ledger = ledger
        self._identity = system_identity("server:change-management", tool="server")

    def blocking_items(self, change_set_id: str) -> list[str]:
        return self._ledger.blocking_items(change_set_id)

    def record_system_fact(self, change_set_id: str, content: str, source: str) -> None:
        self._ledger.record_evidence(
            self._identity, run_id=f"server:{change_set_id}", classification="FACT", content=content,
            source_type="forge_event" if "forge_event" in source else "hook_observation", source=source,
            change_set_id=change_set_id,
        )


class ChangeSetStatusAdapter:
    """Satisfies work_planning's ChangeSetStatusPort with the in-process Change Management module."""

    def __init__(self, change_management: change_management_api.ChangeManagement) -> None:
        self._cm = change_management

    def statuses(self, change_set_ids: list[str]) -> dict[str, str | None]:
        return self._cm.statuses(change_set_ids)


# --------------------------------------------------------------------------- composition
def _new_mcp_server() -> Any:
    """The official MCP SDK (optional extra: pip install .[mcp]). mcp>=2 renamed FastMCP to MCPServer;
    both expose the same ``tool(name=, description=)`` decorator and ``run()`` used here."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:
        from mcp.server.fastmcp import FastMCP as MCPServer
    return MCPServer(SERVER_NAME)


def build_modules(config: Config) -> ModuleRegistry:
    registry = ModuleRegistry()
    enabled = set(config.modules)
    ledger = None
    if "evidence_ledger" in enabled:
        module = evidence_ledger_api.create_module(config)
        registry.add(module)
        ledger = module.api
    cm = None
    if "change_management" in enabled:
        evidence = LedgerEvidenceAdapter(ledger) if ledger else None  # None → module's fail-safe NullEvidencePort
        module = change_management_api.create_module(config, evidence=evidence)
        registry.add(module)
        cm = module.api
    if "contract_registry" in enabled:
        registry.add(contract_registry_api.create_module(config))
    if "work_planning" in enabled:
        # EvaluatorPort: the planning-gates adapter is wired here once it exists; until then the
        # module's NullEvaluator fails safe (readiness/done cannot be confirmed).
        registry.add(work_planning_api.create_module(
            config, evaluator=None, change_sets=ChangeSetStatusAdapter(cm) if cm else None))
    return registry


def build_server(config: Config, identity: Identity, server: Any = None) -> tuple[Any, ModuleRegistry, list[str]]:
    """Build one MCP server hosting every enabled module's tools for ``identity``."""
    if server is None:
        server = _new_mcp_server()
    registry = build_modules(config)
    tools: list[str] = []
    for module in registry:
        tools += module.register_tools(server, identity)
    return server, registry, tools
