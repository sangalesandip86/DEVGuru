"""Work Planning rules — pure functions (plan v3.1 Product Planning layer, §6 Module 4).

Story status is *derived* from observed evidence, never set: an agent cannot make a story
READY, DONE or ACCEPTED. Plan files have no status field.
"""
from __future__ import annotations

import re
from typing import Any

from adlc_mcp.kernel.errors import ValidationError
from adlc_mcp.kernel.util import canonical_json, sha256_hex

ITEM_ID = re.compile(r"^(REQ|EPIC|FEAT|ST|MS)-\d+$")
ID_ANYWHERE = re.compile(r"\b(?:REQ|EPIC|FEAT|ST|MS)-\d+\b")
AC_ID = re.compile(r"^ST-\d+/AC-\d+$")
KINDS = {"REQ": "requirement", "EPIC": "epic", "FEAT": "feature", "ST": "story", "MS": "milestone"}
STORY_STATES = ("DRAFT", "REFINING", "READY", "IN_PROGRESS", "IN_VERIFICATION", "DONE", "ACCEPTED",
                "BLOCKED", "SPLIT", "CANCELLED")
STORY_TYPES = ("FEATURE_STORY", "UI_STORY", "API_CONTRACT", "DATA_MIGRATION", "SECURITY_STORY", "INFRASTRUCTURE",
               "TECHNICAL_STORY", "REFACTOR", "BUG_FIX", "SPIKE", "TEST_AUTOMATION", "DOCUMENTATION")
SIZES = ("XS", "S", "M", "L")
FORBIDDEN_PLAN_FIELDS = ("status", "state", "ready", "done", "accepted")
WORK_EVENT_TYPES = ("readiness_gate", "completion_gate", "pr_opened", "po_acceptance", "cancelled", "split")
SCOPE_FIELDS = ("parent", "requirement", "requirements", "epic", "feature", "source_refs")
TIME_FIELDS = ("milestone", "milestones")
_AFTER_VERIFYING = ("VERIFYING", "INTEGRATED", "RELEASED")


def kind_of(item_id: str) -> str:
    if not ITEM_ID.match(item_id or ""):
        raise ValidationError(f"invalid planning id {item_id!r} (REQ-n, EPIC-n, FEAT-n, ST-n, MS-n)")
    return KINDS[item_id.split("-")[0]]


def validate_plan_item(item_id: str, data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValidationError(f"{item_id}: plan data must be an object")
    if data.get("id", item_id) != item_id:
        raise ValidationError(f"{item_id}: id in file does not match")
    bad = [f for f in FORBIDDEN_PLAN_FIELDS if f in data]
    if bad:
        raise ValidationError(f"{item_id}: plan files have no status field (found {bad}); status is derived by gates")


_AC_HASHED_FIELDS = ("id", "given", "when", "then", "kind", "verification", "tags")
_AC_WS = re.compile(r"\s+")


def _ac_norm(value: Any) -> Any:
    if isinstance(value, str):
        return _AC_WS.sub(" ", value).strip()
    if isinstance(value, list):
        return sorted(_ac_norm(v) for v in value) if all(isinstance(v, str) for v in value) \
            else [_ac_norm(v) for v in value]
    return value


def _canonical_ac(criteria: list[dict]) -> list[dict]:
    out = []
    for ac in criteria or []:
        item = {k: _ac_norm(ac.get(k)) for k in _AC_HASHED_FIELDS if ac.get(k) not in (None, [], "")}
        out.append(item)
    return sorted(out, key=lambda a: str(a.get("id", "")))


def ac_hash(data: dict[str, Any]) -> str:
    import json
    payload = json.dumps(_canonical_ac(data.get("acceptance_criteria") or []),
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + sha256_hex(payload)


def edges_for(item_id: str, kind: str, data: dict[str, Any]) -> set[tuple[str, str, str]]:
    def ids(value: Any) -> set[str]:
        return set(ID_ANYWHERE.findall(canonical_json(value))) - {item_id}

    out: set[tuple[str, str, str]] = set()
    for f in SCOPE_FIELDS:
        if f in data:
            out |= {(item_id, d, "scope") for d in ids(data[f])}
    for f in TIME_FIELDS:
        if f in data:
            out |= {(item_id, d, "time") for d in ids(data[f])}
    if kind == "milestone" and "stories" in data:
        out |= {(s, item_id, "time") for s in ids(data["stories"])}
    if "depends_on" in data:
        out |= {(item_id, d, "depends_on") for d in ids(data["depends_on"])}
    return out


def _latest(events: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    found = [e for e in events if e["event_type"] == event_type]
    return found[-1] if found else None


def derive_status(
    data: dict[str, Any],
    current_ac_hash: str,
    events: list[dict[str, Any]],
    linked_cs_statuses: dict[str, str | None],
) -> dict[str, Any]:
    """Derive a story's status from the plan file, observed events and linked Change Sets."""
    flags: list[str] = []
    if _latest(events, "cancelled"):
        return {"status": "CANCELLED", "flags": flags}
    if _latest(events, "split") or data.get("split_into"):
        return {"status": "SPLIT", "flags": flags}
    if not data.get("acceptance_criteria"):
        return {"status": "DRAFT", "flags": flags}
    status = "REFINING"
    ready = _latest(events, "readiness_gate")
    if ready and ready["payload"].get("passed"):
        if ready["payload"].get("ac_hash") == current_ac_hash:
            status = "READY"
        else:
            flags.append("AC_FREEZE_VIOLATION: acceptance criteria changed after READY; DoR re-runs and "
                         "qa-derive test-design REVIEWED is invalidated")
    if status == "READY" and (_latest(events, "pr_opened") or linked_cs_statuses):
        status = "IN_PROGRESS"
    if status == "IN_PROGRESS" and linked_cs_statuses and all(
            s in _AFTER_VERIFYING for s in linked_cs_statuses.values()):
        status = "IN_VERIFICATION"
    done = _latest(events, "completion_gate")
    if status in ("READY", "IN_PROGRESS", "IN_VERIFICATION") and done and done["payload"].get("passed") \
            and done["payload"].get("ac_hash") == current_ac_hash:
        status = "DONE"
    if status == "DONE" and _latest(events, "po_acceptance"):
        status = "ACCEPTED"
    if status in ("IN_PROGRESS", "IN_VERIFICATION") and any(s == "BLOCKED" for s in linked_cs_statuses.values()):
        flags.append(f"returns to {status} when the linked Change Set unblocks")
        status = "BLOCKED"
    return {"status": status, "flags": flags}


def validate_work_event(event_type: str, payload: dict[str, Any]) -> None:
    if event_type not in WORK_EVENT_TYPES:
        raise ValidationError(f"event_type must be one of {WORK_EVENT_TYPES}")
    if event_type in ("readiness_gate", "completion_gate"):
        if not isinstance(payload.get("passed"), bool) or not payload.get("ac_hash"):
            raise ValidationError(f"{event_type} needs passed (bool) and the ac_hash it evaluated")
    if event_type == "po_acceptance" and payload.get("approver_role") != "human:product-owner":
        raise ValidationError("po_acceptance must come from human:product-owner")
    if event_type == "cancelled" and not str(payload.get("approver_role", "")).startswith("human:"):
        raise ValidationError("cancellation is a human decision (approver_role human:<role>)")


def structural_readiness(story_id: str, data: dict[str, Any]) -> list[str]:
    """Deterministic DoR pre-checks the module can run itself. The policy evaluator is authoritative."""
    missing = []
    stype = data.get("type")
    if stype not in STORY_TYPES:
        missing.append(f"type must be one of the story types (got {stype!r})")
    acs = data.get("acceptance_criteria") or []
    if not acs:
        missing.append("acceptance criteria")
    for i, ac in enumerate(acs):
        if not isinstance(ac, dict):
            missing.append(f"AC[{i}] must be an object")
            continue
        if not AC_ID.match(str(ac.get("id", ""))) or not str(ac.get("id", "")).startswith(story_id + "/"):
            missing.append(f"AC[{i}] needs a stable id {story_id}/AC-n")
        if not all(ac.get(k) for k in ("given", "when", "then")):
            missing.append(f"AC[{i}] needs Given/When/Then")
        if ac.get("kind") not in ("functional", "negative", "nfr"):
            missing.append(f"AC[{i}] kind must be functional|negative|nfr")
        if ac.get("verification") not in ("automated", "manual"):
            missing.append(f"AC[{i}] verification must be automated|manual")
    if stype not in ("DOCUMENTATION", "SPIKE") and acs and not any(
            isinstance(a, dict) and a.get("kind") == "negative" for a in acs):
        missing.append("at least one negative acceptance criterion")
    if not data.get("source_refs"):
        missing.append("source_refs (traceability to the requirement)")
    if data.get("size") not in ("XS", "S", "M"):
        missing.append("size must be XS|S|M (an L must be split before READY)")
    return missing


def structural_done(linked_cs_statuses: dict[str, str | None]) -> list[str]:
    if not linked_cs_statuses:
        return ["at least one linked Change Set"]
    return [f"linked Change Set {cs} is {s or 'UNKNOWN'} (needs INTEGRATED)"
            for cs, s in linked_cs_statuses.items() if s not in ("INTEGRATED", "RELEASED")]


def implemented_ids(declaration: str) -> set[str]:
    ids: set[str] = set()
    for m in re.finditer(r"(?im)^\s*Implements:\s*(.+)$", declaration or ""):
        ids |= set(ID_ANYWHERE.findall(m.group(1)))
    return ids
