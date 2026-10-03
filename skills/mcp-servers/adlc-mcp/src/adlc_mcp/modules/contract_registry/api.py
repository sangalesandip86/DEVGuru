"""Contract Registry — public surface. The ONLY file other code may import from this module.

Plan §6 Server 3, §4.6. ``record_deployment`` is SYSTEM-only (fed by CI). Compatibility is
checked against versions actually recorded as deployed; anything unknown is INCOMPATIBLE.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Protocol

from adlc_mcp.kernel import db
from adlc_mcp.kernel.config import Config
from adlc_mcp.kernel.errors import NotFound, ValidationError
from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.util import now_iso

from . import domain
from .store import ContractStore

NAME = "contract_registry"


class ContractRegistryApi(Protocol):
    def register_contract(self, identity: Identity, **kwargs: Any) -> dict[str, Any]: ...
    def check_compatibility(self, identity: Identity, **kwargs: Any) -> dict[str, Any]: ...
    def detect_drift(self, identity: Identity, **kwargs: Any) -> dict[str, Any]: ...
    def record_deployment(self, identity: Identity, **kwargs: Any) -> dict[str, Any]: ...


class ContractRegistry:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._store = ContractStore(conn)

    def migrate(self) -> list[str]:
        return self._store.migrate()

    def register_contract(
        self,
        identity: Identity,
        *,
        contract_id: str,
        provider: str,
        version: str,
        spec: dict[str, Any],
        type: str,
        consumers: list[str] | None = None,
        compatibility_policy: str = "BACKWARD",
        party: str | None = None,
    ) -> dict[str, Any]:
        """Register a contract, or a new version of one party's view of it (provider or a consumer)."""
        if type not in domain.CONTRACT_TYPES:
            raise ValidationError(f"type must be one of {domain.CONTRACT_TYPES}")
        if compatibility_policy not in domain.POLICIES:
            raise ValidationError(f"compatibility_policy must be one of {domain.POLICIES}")
        domain.normalize(spec)  # validates
        party = party or provider
        existing = self._store.get_contract(contract_id)
        if existing is None:
            self._store.insert_contract({
                "contract_id": contract_id, "provider": provider, "consumers": sorted(set(consumers or [])),
                "type": type, "compatibility_policy": compatibility_policy,
                "registered_by": f"{identity.actor_type}:{identity.actor_id}", "created_at": now_iso(),
            })
        else:
            if existing["provider"] != provider or existing["type"] != type:
                raise ValidationError("provider and type of an existing contract cannot change; register a new contract")
            merged = sorted(set(existing["consumers"]) | set(consumers or []))
            if merged != existing["consumers"]:
                self._store.set_consumers(contract_id, merged)
        contract = self._store.get_contract(contract_id)
        if party != provider and party not in contract["consumers"]:
            raise ValidationError(f"party {party!r} is neither the provider nor a declared consumer")
        if self._store.get_version(contract_id, version, party):
            raise ValidationError(f"{contract_id}@{version} for {party} already registered; versions are immutable")
        self._store.insert_version({
            "contract_id": contract_id, "version": version, "party": party, "spec": spec,
            "registered_by": f"{identity.actor_type}:{identity.actor_id}", "created_at": now_iso(),
        })
        return {"contract": contract, "registered_version": version, "party": party}

    def record_deployment(
        self, identity: Identity, *, app: str, version: str, environment: str, contract_versions: dict[str, str]
    ) -> dict[str, Any]:
        """SYSTEM-only (CI): which app version, using which contract versions, is deployed where."""
        identity.require("SYSTEM", action="record_deployment")
        for cid in contract_versions:
            if self._store.get_contract(cid) is None:
                raise NotFound(f"contract {cid} not registered")
        return self._store.append_deployment({
            "app": app, "version": version, "environment": environment, "contract_versions": contract_versions,
            "recorded_by": identity.actor_id, "timestamp": now_iso(),
        })

    def check_compatibility(
        self, identity: Identity, *, contract_id: str, candidate_version: str, party: str, environment: str
    ) -> dict[str, Any]:
        contract = self._require(contract_id)
        reasons: list[str] = []
        checks: list[dict[str, Any]] = []
        candidate = self._store.get_version(contract_id, candidate_version, party)
        if candidate is None:
            reasons.append(f"candidate {contract_id}@{candidate_version} for {party} is not registered")
        elif party == contract["provider"]:
            # New producer → every currently deployed consumer.
            for consumer in contract["consumers"]:
                spec, why = self._deployed_spec(contract_id, consumer, environment)
                if spec is None:
                    reasons.append(why)
                    continue
                issues = domain.pair_issues(candidate["spec"], spec["spec"])
                checks.append({"direction": "new provider → deployed consumer", "counterpart": consumer,
                               "counterpart_version": spec["version"], "issues": issues})
        elif party in contract["consumers"]:
            provider = contract["provider"]
            if contract["type"] == "event":
                # Old producer → new consumer: retained events from every provider version ever deployed here.
                versions = []
                for dep in self._store.deployment_history(provider, environment):
                    v = dep["contract_versions"].get(contract_id)
                    if v and v not in versions:
                        versions.append(v)
                if not versions:
                    reasons.append(f"no recorded deployment of provider {provider} in {environment} (unknown → INCOMPATIBLE)")
                for v in versions:
                    spec = self._store.get_version(contract_id, v, provider)
                    if spec is None:
                        reasons.append(f"provider spec {contract_id}@{v} not registered")
                        continue
                    checks.append({"direction": "retained events (old provider) → new consumer", "counterpart": provider,
                                   "counterpart_version": v,
                                   "issues": domain.pair_issues(spec["spec"], candidate["spec"])})
            else:
                spec, why = self._deployed_spec(contract_id, provider, environment)
                if spec is None:
                    reasons.append(why)
                else:
                    checks.append({"direction": "deployed provider → new consumer", "counterpart": provider,
                                   "counterpart_version": spec["version"],
                                   "issues": domain.pair_issues(spec["spec"], candidate["spec"])})
        else:
            reasons.append(f"{party!r} is neither provider nor consumer of {contract_id}")
        compatible = not reasons and all(not c["issues"] for c in checks)
        result = {
            "contract_id": contract_id, "candidate_version": candidate_version, "party": party,
            "environment": environment, "result": "COMPATIBLE" if compatible else "INCOMPATIBLE",
            # VERIFIED is set by the server from this deterministic check — never by the caller.
            "verification": "VERIFIED" if compatible else "NOT_VERIFIED",
            "reasons": reasons, "checks": checks,
        }
        recorded = self._store.append_result({
            "kind": "compatibility", "contract_id": contract_id,
            "request": {"candidate_version": candidate_version, "party": party, "environment": environment},
            "result": result, "actor_type": identity.actor_type, "actor_id": identity.actor_id, "timestamp": now_iso(),
        })
        result["result_seq"] = recorded["seq"]
        return result

    def detect_drift(
        self,
        identity: Identity,
        *,
        contract_id: str,
        observed_spec: dict[str, Any],
        environment: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Compare the provider's declared contract (explicit version, else deployed, else latest) to observation."""
        contract = self._require(contract_id)
        provider = contract["provider"]
        if version:
            declared = self._store.get_version(contract_id, version, provider)
        elif environment:
            declared, _ = self._deployed_spec(contract_id, provider, environment)
        else:
            declared = self._store.latest_version(contract_id, provider)
        if declared is None:
            raise NotFound("no declared provider version to compare against")
        report = domain.drift(declared["spec"], observed_spec)
        report.update(contract_id=contract_id, declared_version=declared["version"], environment=environment)
        self._store.append_result({
            "kind": "drift", "contract_id": contract_id,
            "request": {"environment": environment, "version": declared["version"]}, "result": report,
            "actor_type": identity.actor_type, "actor_id": identity.actor_id, "timestamp": now_iso(),
        })
        return report

    def verify(self) -> list[dict[str, Any]]:
        return self._store.verify()

    def _deployed_spec(self, contract_id: str, app: str, environment: str):
        dep = self._store.current_deployment(app, environment)
        if dep is None:
            return None, f"no recorded deployment of {app} in {environment} (unknown → INCOMPATIBLE)"
        v = dep["contract_versions"].get(contract_id)
        if v is None:
            return None, f"deployment of {app}@{dep['version']} in {environment} does not record a {contract_id} version"
        spec = self._store.get_version(contract_id, v, app)
        if spec is None:
            return None, f"{app}'s spec for {contract_id}@{v} is not registered"
        return spec, None

    def _require(self, contract_id: str) -> dict[str, Any]:
        c = self._store.get_contract(contract_id)
        if c is None:
            raise NotFound(f"contract {contract_id} not found")
        return c


class ContractRegistryModule:
    name = NAME

    def __init__(self, config: Config) -> None:
        self._conn = db.connect(config.db_path(NAME))
        self._api = ContractRegistry(self._conn)

    def migrate(self, conn: sqlite3.Connection | None = None) -> None:
        self._api.migrate()

    def register_tools(self, server: Any, identity: Identity) -> list[str]:
        from .tools import register_tools

        return register_tools(server, self._api, identity)

    @property
    def api(self) -> ContractRegistry:
        return self._api

    def close(self) -> None:
        self._conn.close()


def create_module(config: Config) -> ContractRegistryModule:
    module = ContractRegistryModule(config)
    module.migrate()
    return module
