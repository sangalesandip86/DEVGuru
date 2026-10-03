#!/usr/bin/env python3
"""can-i-deploy: check a version against what is ACTUALLY deployed (plan §4.6, §6 record_deployment).

Never compares "latest against latest". For the application version being deployed to an
environment, every contract it takes part in is checked against the counterpart versions recorded
as deployed in that environment:

  app is PROVIDER  -> new producer vs each deployed consumer      (new producer -> old consumer)
  app is CONSUMER  -> deployed provider vs new consumer           (old producer -> new consumer)
  event contracts  -> additionally, as consumer, every provider version whose messages may still
                      be retained (`retained_versions` on the provider's deployment record)

A check is COMPATIBLE only if a verification record exists for that exact version pair with result
COMPATIBLE. Missing verification, missing deployment record, or an unknown result is INCOMPATIBLE
by default (§5.3), with reason_code COMPATIBILITY_UNKNOWN where the cause is missing evidence.

Input: a registry export (JSON), as produced by the contract_registry module of the adlc MCP server:
{
  "contracts": [{"id", "type": "http|grpc|graphql|event", "provider", "consumers": [...],
                 "verifications": [{"provider_version", "consumer", "consumer_version",
                                    "result": "COMPATIBLE|INCOMPATIBLE", "evidence"?}]}],
  "deployments": [{"application", "version", "environment", "retained_versions"?: [...]}]
}

Exit codes: 0 deployable, 1 not deployable, 2 usage/input error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def deployed(deployments: list[dict], app: str, env: str) -> dict | None:
    """Latest record for app in env (records are appended in order; last wins)."""
    found = None
    for d in deployments:
        if d.get("application") == app and d.get("environment") == env:
            found = d
    return found


def verification(contract: dict, provider_version: str, consumer: str, consumer_version: str) -> dict | None:
    found = None
    for v in contract.get("verifications", []):
        if (v.get("provider_version"), v.get("consumer"), v.get("consumer_version")) == \
                (provider_version, consumer, consumer_version):
            found = v  # last record wins (re-verification)
    return found


def check_pair(contract: dict, provider_version: str | None, consumer: str,
               consumer_version: str | None, direction: str) -> dict:
    base = {"contract": contract["id"], "type": contract.get("type", "http"), "direction": direction,
            "provider": contract["provider"], "provider_version": provider_version,
            "consumer": consumer, "consumer_version": consumer_version}
    if provider_version is None or consumer_version is None:
        missing = contract["provider"] if provider_version is None else consumer
        return {**base, "result": "INCOMPATIBLE", "reason_code": "COMPATIBILITY_UNKNOWN",
                "reason": f"no deployment record for {missing}; incompatible by default"}
    v = verification(contract, provider_version, consumer, consumer_version)
    if v is None:
        return {**base, "result": "INCOMPATIBLE", "reason_code": "COMPATIBILITY_UNKNOWN",
                "reason": "no verification for this exact version pair; incompatible by default"}
    if v.get("result") == "COMPATIBLE":
        return {**base, "result": "COMPATIBLE", "evidence": v.get("evidence")}
    return {**base, "result": "INCOMPATIBLE", "reason": f"verification result {v.get('result')!r}",
            "evidence": v.get("evidence")}


def can_i_deploy(registry: dict, app: str, version: str, env: str) -> dict:
    deployments = registry.get("deployments", [])
    checks = []
    for c in registry.get("contracts", []):
        is_event = c.get("type") == "event"
        if c.get("provider") == app:
            for consumer in c.get("consumers", []):
                rec = deployed(deployments, consumer, env)
                checks.append(check_pair(c, version, consumer, rec and rec["version"],
                                         "new-producer->old-consumer"))
        if app in c.get("consumers", []):
            rec = deployed(deployments, c["provider"], env)
            checks.append(check_pair(c, rec and rec["version"], app, version,
                                     "old-producer->new-consumer"))
            if is_event and rec:
                for retained in rec.get("retained_versions", []):
                    if retained != rec["version"]:
                        checks.append(check_pair(c, retained, app, version,
                                                 "retained-producer->new-consumer"))
    ok = all(ch["result"] == "COMPATIBLE" for ch in checks)
    return {
        "application": app, "version": version, "environment": env,
        "can_deploy": ok,
        "result": "COMPATIBLE" if ok else "INCOMPATIBLE",
        "checks": checks,
        "reason_codes": sorted({ch["reason_code"] for ch in checks if ch.get("reason_code")}),
        "note": "No contracts found for this application." if not checks else None,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check compatibility against recorded deployed versions.")
    ap.add_argument("--registry", type=Path, required=True, help="registry export JSON")
    ap.add_argument("--application", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--environment", required=True)
    args = ap.parse_args(argv)
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": f"cannot read registry: {exc}", "result": "INCOMPATIBLE",
                          "can_deploy": False}))
        return 2
    result = can_i_deploy(registry, args.application, args.version, args.environment)
    print(json.dumps(result, indent=2))
    return 0 if result["can_deploy"] else 1


if __name__ == "__main__":
    sys.exit(main())
