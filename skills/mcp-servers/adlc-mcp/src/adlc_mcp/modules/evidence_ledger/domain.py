"""Evidence Ledger rules: trust derivation, authority, and per-classification requirements.

Plan refs: §4.3 (schema, identity-and-auth), §5.1 (taxonomy), §5.5 (REVIEWED/VERIFIED/APPROVED),
§4.2 (incidents, positive-signal quality gate, production feedback), ADR 0006 (signal-only
incidents, sanitized lessons).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from adlc_mcp.kernel.errors import PermissionDenied, ValidationError
from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.util import parse_iso
from adlc_mcp.kernel.vocab import CLASSIFICATIONS, LIFECYCLE_STATES, TOOLS, TRUST_LEVELS, lowest_trust

# source_type → trust level. The caller names *what kind of source* it read; the server
# decides how much that source is trusted. Unknown source types fail safe to EXTERNAL_UNSTRUCTURED.
#
# The first block is the contract with the enforcement fact-writer hooks
# (skills/enforcement/hooks/fact-writer-hooks): command/tool output and the hook's own
# observations are captured by the harness itself, so they are SYSTEM; a file's *content*
# is only as trusted as the repository it came from; fetched web content is untrusted.
SOURCE_TYPE_TRUST: dict[str, str] = {
    # fact-writer hook source types
    "file_read": "REPOSITORY",
    "command_output": "SYSTEM",
    "tool_output": "SYSTEM",
    "hook_observation": "SYSTEM",
    "external_fetch": "EXTERNAL_UNSTRUCTURED",
    "mcp_response": "EXTERNAL_STRUCTURED",
    # server / CI writers
    "platform_policy": "SYSTEM",
    "ci_result": "SYSTEM",
    "scanner_result": "SYSTEM",
    "forge_event": "SYSTEM",
    # human and organisational sources
    "org_policy": "ORGANIZATIONAL",
    "org_document": "ORGANIZATIONAL",
    "user_statement": "ORGANIZATIONAL",
    # repository content and agent analysis of it
    "repo_file": "REPOSITORY",
    "git_metadata": "REPOSITORY",
    "agents_md": "REPOSITORY",
    "agent_analysis": "REPOSITORY",
    # external
    "contract_spec": "EXTERNAL_STRUCTURED",
    "external_api": "EXTERNAL_STRUCTURED",
    "issue_text": "EXTERNAL_UNSTRUCTURED",
    "pr_comment": "EXTERNAL_UNSTRUCTURED",
    "web_page": "EXTERNAL_UNSTRUCTURED",
    "external_doc": "EXTERNAL_UNSTRUCTURED",
    "generated_log": "EXTERNAL_UNSTRUCTURED",
}
assert set(SOURCE_TYPE_TRUST.values()) <= set(TRUST_LEVELS)

# Who may write which lifecycle_state on a DECISION/PROPOSAL (§5.5).
LIFECYCLE_AUTHORITY = {
    "AGENT": {"DRAFT", "PROPOSED", "REVIEWED", "REJECTED"},
    "SYSTEM": {"DRAFT", "PROPOSED", "VERIFIED", "REJECTED"},
    "HUMAN": {"DRAFT", "PROPOSED", "REVIEWED", "APPROVED", "REJECTED"},
}
IMPACT_LEVELS = ("LOW", "MEDIUM", "HIGH")
SIGNAL_SOURCE_AUTHORITY = {
    "AGENT": {"AGENT", "REVIEWER"},
    "SYSTEM": {"AGENT", "REVIEWER", "PRODUCTION"},
    "HUMAN": {"HUMAN"},
}
SIGNAL_TYPES = ("negative", "positive", "unverified-positive", "efficiency", "production")
REMEDY_KINDS = ("GATE", "LINT", "SKILL_TEXT", "EXAMPLE")
LESSON_SCOPES = ("PROJECT", "ORG")
NOTE_MAX = 280

# ADR 0006 §1: an incident is a signal plus local pointers — nothing else.
INCIDENT_FIELDS = frozenset({
    "skill", "step", "failure_class", "signal_type", "signal_source", "verification_strength",
    "pattern_eligible", "evidence_refs", "note",
})
LESSON_FIELDS = frozenset({
    "skill", "step", "failure_class", "occurrences", "what_failed", "advice", "check", "remedy_kind",
    "reproduction_ref", "incident_refs", "sanitization_result", "scope", "parent_lesson_id",
    "approval_entry_id",
})
_FAILURE_CLASS = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
# Cheap deterministic guard against local pointers leaking into shareable lesson text. The full
# check (PII, secrets, project blocklist, verbatim overlap) is sanitize_check.py, attested by
# sanitization_result.
_LOCAL_POINTER = re.compile(r"\b(?:ENTRY|CS|INC|SNAP|TASK|FE|HO)-[0-9A-Za-z]+\b|@[0-9a-f]{7,40}:")


def derive_trust(source_type: str, referenced: list[dict[str, Any]]) -> str:
    """Trust = the lowest of the source's own level and every entry it was derived from (taint)."""
    own = SOURCE_TYPE_TRUST.get(source_type, "EXTERNAL_UNSTRUCTURED")
    return lowest_trust([own, *(e["trust_level"] for e in referenced)])


def resolve_tool(identity: Identity, tool: str | None) -> str:
    """The credential's tool wins; a SYSTEM writer (hook/CI) may name the tool it observed."""
    if identity.tool:
        if tool and tool != identity.tool:
            raise ValidationError(f"tool {tool!r} contradicts the authenticated credential ({identity.tool!r})")
        return identity.tool
    if identity.is_system and tool in TOOLS:
        return tool
    raise ValidationError("tool could not be derived from the credential")


def resolve_model(identity: Identity, model_id: str | None) -> str | None:
    if identity.model_id:
        if model_id and model_id != identity.model_id:
            raise ValidationError("model_id contradicts the authenticated credential")
        return identity.model_id
    if identity.is_agent and not model_id:
        raise ValidationError("model_id is required for AGENT entries")
    return model_id


def validate_entry(
    identity: Identity,
    *,
    classification: str,
    content: str,
    source: str | None,
    input_references: list[str] | None,
    referenced: list[dict[str, Any]],
    lifecycle_state: str | None,
    signal_source: str | None,
    metadata: dict[str, Any] | None,
) -> None:
    if classification not in CLASSIFICATIONS:
        raise ValidationError(f"classification must be one of {CLASSIFICATIONS}")
    if not content or not content.strip():
        raise ValidationError("content is required")

    if classification == "FACT":
        # FACTs come from hooks/CI (SYSTEM) or a human's own statement — never model self-report.
        if identity.is_agent:
            raise PermissionDenied(
                "AGENT callers cannot write FACT entries; FACTs are written by hooks from command output "
                "and file reads. Record an INFERENCE that references the FACT instead."
            )
        if not source:
            raise ValidationError("FACT entries require a source")

    if classification == "INFERENCE":
        if not input_references:
            raise ValidationError("INFERENCE entries require input_references")
    if input_references:
        missing = set(input_references) - {e["entry_id"] for e in referenced}
        if missing:
            raise ValidationError(f"input_references not found in ledger: {sorted(missing)}")

    if lifecycle_state is not None:
        if classification not in ("DECISION", "PROPOSAL"):
            raise ValidationError("lifecycle_state applies only to DECISION and PROPOSAL entries")
        if lifecycle_state not in LIFECYCLE_STATES:
            raise ValidationError(f"lifecycle_state must be one of {LIFECYCLE_STATES}")
        if lifecycle_state not in LIFECYCLE_AUTHORITY[identity.actor_type]:
            raise PermissionDenied(
                f"{identity.actor_type} callers cannot set lifecycle_state {lifecycle_state} "
                "(REVIEWED=agent judgment, VERIFIED=machine evidence via server, APPROVED=authenticated human)"
            )
        if lifecycle_state == "VERIFIED" and not source:
            raise ValidationError("VERIFIED requires the machine evidence source (CI run, scanner, test runner)")

    if signal_source is not None and signal_source not in SIGNAL_SOURCE_AUTHORITY[identity.actor_type]:
        raise PermissionDenied(f"{identity.actor_type} callers cannot claim signal_source {signal_source}")

    metadata = metadata or {}
    if classification == "QUESTION" and not isinstance(metadata.get("blocking"), bool):
        raise ValidationError("QUESTION entries require metadata.blocking (true/false)")
    if classification == "ASSUMPTION":
        if metadata.get("impact") not in IMPACT_LEVELS:
            raise ValidationError(f"ASSUMPTION entries require metadata.impact in {IMPACT_LEVELS}")
        try:
            parse_iso(metadata["expires_at"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("ASSUMPTION entries require metadata.expires_at (ISO 8601) — assumptions expire")


def reject_unknown_fields(fields: dict[str, Any], allowed: frozenset[str], what: str) -> None:
    extra = sorted(set(fields) - allowed)
    if extra:
        raise ValidationError(
            f"{what} does not accept {extra}: no free-text use-case content (prompt, files, context, "
            "hypothesis, ...) is recorded; evidence stays in the ledger and is referenced by entry_id (ADR 0006)"
        )


@lru_cache(maxsize=4)
def _taxonomy_from(path: str) -> frozenset[str]:
    found: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, str) and _FAILURE_CLASS.match(x):
            found.add(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(json.loads(Path(path).read_text(encoding="utf-8")))
    return frozenset(found)


def known_failure_classes(repo_root: Path | None) -> frozenset[str] | None:
    """Classes from failure-class-map.json ($ADLC_FAILURE_CLASS_MAP, else found under skills/self-improvement).

    None when no map exists yet, in which case only the class *format* is enforced.
    """
    override = os.environ.get("ADLC_FAILURE_CLASS_MAP")
    candidates = [Path(override)] if override else (
        sorted((repo_root / "skills" / "self-improvement").rglob("failure-class-map.json")) if repo_root else [])
    for c in candidates:
        if c.is_file():
            try:
                return _taxonomy_from(str(c))
            except (OSError, ValueError):
                return frozenset()          # unreadable map: nothing validates (fail closed)
    return None


def validate_failure_class(failure_class: str | None, known: frozenset[str] | None, *, required: bool) -> None:
    if failure_class is None:
        if required:
            raise ValidationError("failure_class is required (derived deterministically via failure-class-map.json)")
        return
    if not isinstance(failure_class, str) or not _FAILURE_CLASS.match(failure_class):
        raise ValidationError("failure_class must be an UPPER_SNAKE taxonomy class")
    if known is not None and failure_class not in known:
        raise ValidationError(f"failure_class {failure_class!r} is not in failure-class-map.json")


def failing_actors(evidence: list[dict[str, Any]]) -> dict[str, set[str]]:
    """The agents that produced the evidence an incident points at, i.e. the ones that failed.

    Roles and actor_ids (one credential per role session, so actor_id identifies the run's session)."""
    agents = [e for e in evidence if e.get("actor_type") == "AGENT"]
    return {"roles": {e["agent_role"] for e in agents if e.get("agent_role")},
            "actor_ids": {e["actor_id"] for e in agents},
            "run_ids": {e["run_id"] for e in agents}}


def check_not_self_authored(identity: Identity, failed: dict[str, set[str]], what: str) -> None:
    if identity.is_agent and (identity.agent_role in failed["roles"] or identity.actor_id in failed["actor_ids"]):
        raise PermissionDenied(
            f"the {what} cannot be written by the agent role/session that failed "
            f"({identity.agent_role}, {identity.actor_id}); it is written by the reviewer or human who caught it"
        )


def validate_incident(identity: Identity, f: dict[str, Any], refs: list[dict[str, Any]],
                      known_classes: frozenset[str] | None) -> None:
    for key in ("skill", "step"):
        if not isinstance(f.get(key), str) or not f[key].strip() or len(f[key]) > 200:
            raise ValidationError(f"{key} is required (at most 200 chars, in skill terms)")
    signal_type, signal_source = f.get("signal_type"), f.get("signal_source")
    if signal_type not in SIGNAL_TYPES:
        raise ValidationError(f"signal_type must be one of {SIGNAL_TYPES}")
    if signal_source not in SIGNAL_SOURCE_AUTHORITY[identity.actor_type]:
        raise PermissionDenied(f"{identity.actor_type} callers cannot claim signal_source {signal_source}")
    validate_failure_class(f.get("failure_class"), known_classes,
                           required=signal_type in ("negative", "production"))

    evidence_refs = f.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise ValidationError("evidence_refs must list at least one entry_id in this ledger")
    missing = set(evidence_refs) - {e["entry_id"] for e in refs}
    if missing:
        raise ValidationError(f"evidence_refs not found in this ledger: {sorted(missing)}")

    if not isinstance(f.get("pattern_eligible"), bool):
        raise ValidationError("pattern_eligible must be true or false")
    vs = f.get("verification_strength")
    if vs is not None:
        if not isinstance(vs, dict) or set(vs) - {"changed_code_coverage", "acceptance_criteria_exercised"}:
            raise ValidationError("verification_strength = {changed_code_coverage, acceptance_criteria_exercised}")
        cov = vs.get("changed_code_coverage")
        if cov is not None and (isinstance(cov, bool) or not isinstance(cov, (int, float)) or not 0 <= cov <= 1):
            raise ValidationError("changed_code_coverage must be within [0, 1] or null")
    if signal_type == "positive":
        # Positive-signal quality gate (§4.2): a clean run only counts when verification meant something.
        if not vs or vs.get("acceptance_criteria_exercised") is not True or vs.get("changed_code_coverage") is None:
            raise ValidationError(
                "a positive signal needs verification_strength with acceptance_criteria_exercised=true and "
                "changed_code_coverage; otherwise record it as unverified-positive"
            )
    if signal_type == "unverified-positive" and f["pattern_eligible"]:
        raise ValidationError("unverified-positive signals are never pattern_eligible")

    note = f.get("note")
    if note is not None:
        if not isinstance(note, str) or not note.strip() or len(note) > NOTE_MAX or "\n" in note:
            raise ValidationError(f"note must be one line of at most {NOTE_MAX} characters, in skill terms")
        if signal_source not in ("REVIEWER", "HUMAN"):
            raise ValidationError("a note is for judgment-only failures and comes from the REVIEWER or HUMAN who caught it")
        check_not_self_authored(identity, failing_actors(refs), "note")


def validate_sanitization(result: Any, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("passed") is not True:
        raise ValidationError("sanitization_result {passed: true, checker_version, checked_at} is required; "
                              "content that fails sanitize_check.py stays local")
    if not isinstance(result.get("checker_version"), str) or not result["checker_version"].strip():
        raise ValidationError("sanitization_result.checker_version is required")
    try:
        checked = parse_iso(result["checked_at"])
    except (KeyError, TypeError, ValueError):
        raise ValidationError("sanitization_result.checked_at must be ISO 8601")
    if checked > (now or datetime.now(timezone.utc)) + timedelta(minutes=5):
        raise ValidationError("sanitization_result.checked_at is in the future")
    return {"passed": True, "checker_version": result["checker_version"], "checked_at": result["checked_at"]}


def validate_lesson_content(f: dict[str, Any], known_classes: frozenset[str] | None) -> None:
    for key, cap in (("skill", 200), ("step", 200), ("what_failed", NOTE_MAX), ("advice", 500)):
        if not isinstance(f.get(key), str) or not f[key].strip() or len(f[key]) > cap:
            raise ValidationError(f"{key} is required (at most {cap} chars)")
    validate_failure_class(f.get("failure_class"), known_classes, required=True)
    if f.get("remedy_kind") not in REMEDY_KINDS:
        raise ValidationError(f"remedy_kind must be one of {REMEDY_KINDS}")
    occ = f.get("occurrences")
    if not isinstance(occ, dict) or set(occ) != {"incidents", "change_sets", "projects"} or not all(
            isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in occ.values()) or occ["incidents"] < 1:
        raise ValidationError("occurrences = {incidents >= 1, change_sets, projects} (non-negative integers)")
    for key in ("what_failed", "advice", "check"):
        if f.get(key) and _LOCAL_POINTER.search(f[key]):
            raise ValidationError(f"{key} contains a local pointer (entry/change-set id or repo@sha:path); "
                                  "lessons are written in skill terms only")


def is_expired(entry: dict[str, Any], at: datetime | None = None) -> bool:
    expires = (entry.get("metadata") or {}).get("expires_at")
    if not expires:
        return False
    return parse_iso(expires) <= (at or datetime.now(timezone.utc))
