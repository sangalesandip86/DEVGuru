"""MCP tool registration for the Contract Registry (plan §6 Server 3).

``record_deployment`` is registered only for SYSTEM (CI) sessions; the API re-checks it.
"""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.mcp_compat import register_tool


def register_tools(server: Any, api: Any, identity: Identity) -> list[str]:
    def register_contract(
        contract_id: str,
        provider: str,
        version: str,
        spec: dict[str, Any],
        type: str,
        consumers: list[str] | None = None,
        compatibility_policy: str = "BACKWARD",
        party: str | None = None,
    ) -> dict[str, Any]:
        """Register a contract (type http|grpc|event|schema) or a new immutable version of one party's view."""
        return api.register_contract(identity, contract_id=contract_id, provider=provider, version=version,
                                     spec=spec, type=type, consumers=consumers,
                                     compatibility_policy=compatibility_policy, party=party)

    def check_compatibility(contract_id: str, candidate_version: str, party: str, environment: str) -> dict[str, Any]:
        """Check a candidate version against versions actually recorded as deployed in `environment`
        (both directions for event contracts). Unknown → INCOMPATIBLE."""
        return api.check_compatibility(identity, contract_id=contract_id, candidate_version=candidate_version,
                                       party=party, environment=environment)

    def detect_drift(contract_id: str, observed_spec: dict[str, Any], environment: str | None = None,
                     version: str | None = None) -> dict[str, Any]:
        """Compare the declared contract against observed reality."""
        return api.detect_drift(identity, contract_id=contract_id, observed_spec=observed_spec,
                                environment=environment, version=version)

    def record_deployment(app: str, version: str, environment: str, contract_versions: dict[str, str]) -> dict[str, Any]:
        """SYSTEM-only (CI): record which app version and contract versions are deployed where."""
        return api.record_deployment(identity, app=app, version=version, environment=environment,
                                     contract_versions=contract_versions)

    tools = [register_contract, check_compatibility, detect_drift]
    if identity.is_system:
        tools.append(record_deployment)
    return [register_tool(server, fn) for fn in tools]
