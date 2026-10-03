"""Structural compatibility and drift rules (plan §4.6). Pure functions.

Spec format (each party registers *its own view* of the contract):

    {"payloads": {
        "<name>": {"direction": "provider_to_consumer" | "consumer_to_provider",
                   "fields": {"<field>": {"type": "string", "required": true}, ...}}}}

Shorthand ``{"fields": {...}}`` means one provider_to_consumer payload named ``default``.

For a payload flowing sender → receiver, the pair is compatible when every field the
receiver requires is guaranteed (present and required) by the sender with the same type.
Anything that cannot be evaluated is INCOMPATIBLE (§5.3) — never "assume fine".
"""
from __future__ import annotations

from typing import Any

from adlc_mcp.kernel.errors import ValidationError

CONTRACT_TYPES = ("http", "grpc", "event", "schema")
POLICIES = ("BACKWARD", "FORWARD", "FULL", "NONE")
DIRECTIONS = ("provider_to_consumer", "consumer_to_provider")


def normalize(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(spec, dict):
        raise ValidationError("spec must be an object")
    if "payloads" in spec:
        payloads = spec["payloads"]
    elif "fields" in spec:
        payloads = {"default": {"direction": "provider_to_consumer", "fields": spec["fields"]}}
    else:
        raise ValidationError("spec needs 'payloads' or 'fields'")
    out = {}
    for name, p in payloads.items():
        direction = p.get("direction", "provider_to_consumer")
        if direction not in DIRECTIONS:
            raise ValidationError(f"payload {name}: direction must be one of {DIRECTIONS}")
        fields = p.get("fields")
        if not isinstance(fields, dict):
            raise ValidationError(f"payload {name}: fields must be an object")
        for fname, f in fields.items():
            if not isinstance(f, dict) or "type" not in f:
                raise ValidationError(f"payload {name}.{fname}: needs a type")
        out[name] = {"direction": direction, "fields": fields}
    return out


def _flow_issues(sender: dict[str, Any], receiver: dict[str, Any], label: str) -> list[str]:
    issues = []
    for fname, f in receiver.items():
        if not f.get("required", False):
            continue
        s = sender.get(fname)
        if s is None:
            issues.append(f"{label}: receiver requires '{fname}', sender does not provide it")
        elif not s.get("required", False):
            issues.append(f"{label}: receiver requires '{fname}', sender marks it optional")
        elif s.get("type") != f.get("type"):
            issues.append(f"{label}: '{fname}' type {s.get('type')} (sender) vs {f.get('type')} (receiver)")
    return issues


def pair_issues(provider_spec: dict[str, Any], consumer_spec: dict[str, Any]) -> list[str]:
    """Issues when ``provider_spec`` (sender of provider_to_consumer payloads) talks to ``consumer_spec``."""
    prov, cons = normalize(provider_spec), normalize(consumer_spec)
    issues = []
    for name, cp in cons.items():
        pp = prov.get(name)
        if pp is None:
            issues.append(f"payload '{name}' used by consumer is absent from provider")
            continue
        if cp["direction"] == "provider_to_consumer":
            issues += _flow_issues(pp["fields"], cp["fields"], f"{name} (provider→consumer)")
        else:
            issues += _flow_issues(cp["fields"], pp["fields"], f"{name} (consumer→provider)")
    for name, pp in prov.items():
        if name not in cons and pp["direction"] == "consumer_to_provider" and any(
                f.get("required") for f in pp["fields"].values()):
            issues.append(f"provider requires request payload '{name}' the consumer never sends")
    return issues


def drift(declared: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    d, o = normalize(declared), normalize(observed)
    report: dict[str, Any] = {"missing_payloads": sorted(set(d) - set(o)),
                              "undeclared_payloads": sorted(set(o) - set(d)), "payloads": {}}
    for name in set(d) & set(o):
        df, of = d[name]["fields"], o[name]["fields"]
        entry = {
            "missing_in_observed": sorted(k for k in df if k not in of and df[k].get("required")),
            "undeclared_in_observed": sorted(k for k in of if k not in df),
            "type_mismatch": sorted(k for k in df if k in of and df[k].get("type") != of[k].get("type")),
        }
        if any(entry.values()):
            report["payloads"][name] = entry
    report["drift"] = bool(report["missing_payloads"] or report["undeclared_payloads"] or report["payloads"])
    return report
