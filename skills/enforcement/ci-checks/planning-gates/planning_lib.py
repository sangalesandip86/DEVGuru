"""Shared logic for the planning gates (plan v3.1 §4.12, §5.6).

Stdlib only. Used by plan_lint.py, readiness_gate.py and completion_gate.py; designed so the
``work_planning`` module of the adlc MCP server can import the same evaluation later.

Authority model enforced here (plan §5.5):
  * STRUCTURAL items are deterministic checks over plan files and SYSTEM-exported evidence.
  * JUDGMENT items are satisfied ONLY by a REVIEWED/ACCEPT record from the named role (an
    AGENT authenticated as that role) or from a HUMAN. SYSTEM actors and VERIFIED records
    never satisfy a judgment, whatever they say.
  * APPROVAL items are satisfied ONLY by an authenticated HUMAN approval event naming the
    required approver.
"""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import minyaml
from ac_hash import ac_hash

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[2]
PLANNING = SKILLS / "product-planning"
POLICIES = PLANNING / "policies"
SCHEMAS = PLANNING / "schemas"
PATH_TIER_SCRIPT = SKILLS / "change-management" / "risk-tiering" / "scripts" / "path_tier_lookup.py"

TIERS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
KINDS = {"requirements": "requirement", "epics": "epic", "stories": "story", "milestones": "milestone"}
POST_READY = {"READY", "IN_PROGRESS", "IN_VERIFICATION", "DONE", "ACCEPTED"}
ALLOWED_SIZES = {"XS", "S", "M"}
SPIKE_ALLOWED_PATHS = ["docs/**", "**/docs/**", "**/adr/**", "**/*.md", "plans/**", "**/plans/**"]

PASS, MISSING, FAIL, REJECTED = "PASS", "MISSING", "FAIL", "REJECTED"


# --------------------------------------------------------------------------- loading

def load_policy(name: str, policy_dir: Path | None = None) -> dict:
    return minyaml.load((policy_dir or POLICIES) / f"{name}.yaml")


def load_schema(kind: str) -> dict:
    return json.loads((SCHEMAS / f"{kind}.schema.json").read_text(encoding="utf-8"))


def load_plans(plan_dir: Path) -> tuple[dict[str, dict[str, dict]], list[dict]]:
    """Return ({kind: {id: doc}}, load_errors). Each doc gets a private '_file' key."""
    plans: dict[str, dict[str, dict]] = {k: {} for k in KINDS.values()}
    errors: list[dict] = []
    for sub, kind in KINDS.items():
        d = Path(plan_dir) / sub
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix not in (".yaml", ".yml", ".json"):
                continue
            try:
                doc = minyaml.load(f)
            except (ValueError, OSError) as exc:
                errors.append({"file": str(f), "error": f"parse error: {exc}"})
                continue
            if not isinstance(doc, dict):
                errors.append({"file": str(f), "error": "top level must be a mapping"})
                continue
            doc_id = doc.get("id")
            if doc_id in plans[kind]:
                errors.append({"file": str(f), "error": f"duplicate id {doc_id}"})
                continue
            doc["_file"] = str(f)
            plans[kind][doc_id] = doc
    return plans, errors


def load_evidence(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def public(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


# --------------------------------------------------------------------------- JSON Schema (subset)

def validate(instance: Any, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Validate the JSON-Schema subset used by skills/product-planning/schemas."""
    root = root or schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            return [f"{path}: unsupported $ref {ref}"]
        target: Any = root
        for part in ref[2:].split("/"):
            target = target[part]
        return validate(instance, target, root, path)
    errs: list[str] = []
    if "enum" in schema and instance not in schema["enum"]:
        return [f"{path}: {instance!r} not in {schema['enum']}"]
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        ok = any(_is_type(instance, ty) for ty in types)
        if not ok:
            return [f"{path}: expected {t}, got {type(instance).__name__}"]
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errs.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errs.append(f"{path}: {instance!r} does not match {schema['pattern']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errs.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errs.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errs.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if "items" in schema:
            for i, item in enumerate(instance):
                errs += validate(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errs.append(f"{path}: missing required '{req}'")
        props = schema.get("properties", {})
        for k, v in instance.items():
            if k.startswith("_"):
                continue
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                hint = " (status is derived by the gates, never stored in plan files)" if k == "status" else ""
                errs.append(f"{path}: unexpected field '{k}'{hint}")
    return errs


def _is_type(v: Any, t: str) -> bool:
    return {
        "object": isinstance(v, dict),
        "array": isinstance(v, list),
        "string": isinstance(v, str),
        "boolean": isinstance(v, bool),
        "integer": isinstance(v, int) and not isinstance(v, bool),
        "number": isinstance(v, (int, float)) and not isinstance(v, bool),
        "null": v is None,
    }.get(t, False)


# --------------------------------------------------------------------------- tiers

def max_tier(*tiers: str | None) -> str | None:
    present = [t for t in tiers if t]
    return max(present, key=TIERS.index) if present else None


_path_tier_mod = None


def _path_tier_module():
    global _path_tier_mod
    if _path_tier_mod is None and PATH_TIER_SCRIPT.is_file():
        spec = importlib.util.spec_from_file_location("path_tier_lookup", PATH_TIER_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _path_tier_mod = mod
    return _path_tier_mod


def path_tier(paths: list[str]) -> dict | None:
    """Tier for paths via the Phase 0 lookup; None when the lookup is unavailable or no paths."""
    if not paths:
        return None
    mod = _path_tier_module()
    if mod is None:
        return None
    config = json.loads(mod.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    control, _ = mod.load_control_files(mod.DEFAULT_CONTROL_FILES)
    return mod.lookup(list(paths), config, control)


def effective_tier(story: dict, story_types: dict) -> dict:
    """Effective tier = max(type floor, path tier, declared). Never lowered by any input.

    Fail-safe (plan §5.3): if no input yields a tier, the tier is HIGH.
    """
    floor = (story_types.get("types", {}).get(story.get("type"), {}) or {}).get("tier_floor")
    declared = story.get("risk_tier")
    pt = path_tier(story.get("affected_paths") or [])
    p_tier = pt["tier"] if pt else None
    tier = max_tier(floor, p_tier, declared)
    source = {"type_floor": floor, "path_tier": p_tier, "declared": declared}
    if tier is None:
        return {"tier": "HIGH", "sources": source, "fail_safe": True,
                "reason": "no type floor, declared tier or affected_paths: tier uncomputable -> HIGH (§5.3)"}
    return {"tier": tier, "sources": source, "fail_safe": False}


# --------------------------------------------------------------------------- applicability

def _cond_holds(cond: dict, story: dict, tier: str) -> bool:
    for key, val in cond.items():
        if key == "type" and story.get("type") not in val:
            return False
        if key == "not_type" and story.get("type") in val:
            return False
        if key == "tier_at_least" and TIERS.index(tier) < TIERS.index(val):
            return False
        if key == "data_classification" and story.get("data_classification") not in val:
            return False
        if key == "size" and story.get("size") not in val:
            return False
        if key == "touches":
            touches = story.get("touches") or {}
            if not any(bool(touches.get(flag)) for flag in val):
                return False
        if key not in ("type", "not_type", "tier_at_least", "data_classification", "size", "touches"):
            raise ValueError(f"unknown policy condition '{key}'")
    return True


def applies(item: dict, story: dict, tier: str) -> bool:
    a = item.get("applies", "mandatory")
    if a == "mandatory":
        return True
    if isinstance(a, dict):
        if "when" in a:
            return _cond_holds(a["when"], story, tier)
        if "when_any" in a:
            return any(_cond_holds(c, story, tier) for c in a["when_any"])
    raise ValueError(f"item {item.get('id')}: unsupported applies {a!r}")


# --------------------------------------------------------------------------- context

class Ctx:
    def __init__(self, story: dict, plans: dict, evidence: dict, tier: str,
                 coverage: dict | None = None, now: datetime | None = None,
                 policy: dict | None = None):
        self.story = story
        self.sid = story.get("id")
        self.plans = plans
        self.evidence = evidence or {}
        self.tier = tier
        self.coverage = coverage if coverage is not None else self.evidence.get("ac_coverage")
        self.now = now or datetime.now(timezone.utc)
        self.policy = policy or {}
        self.ac_hash = ac_hash(story)

    def ev(self, key: str) -> list[dict]:
        return [e for e in self.evidence.get(key, []) if e.get("story") == self.sid]

    def linked_change_sets(self) -> list[dict]:
        return [cs for cs in self.evidence.get("change_sets", []) if self.sid in (cs.get("story_refs") or [])]

    @property
    def acs(self) -> list[dict]:
        return self.story.get("acceptance_criteria") or []


def _ok(detail: str = "") -> tuple[str, str]:
    return PASS, detail


def _missing(detail: str) -> tuple[str, str]:
    return MISSING, detail


def _fail(detail: str) -> tuple[str, str]:
    return FAIL, detail


def _nonempty(v: Any) -> bool:
    return bool(v.strip()) if isinstance(v, str) else bool(v)


# --------------------------------------------------------------------------- structural checks

def schema_valid(c: Ctx, item: dict) -> tuple[str, str]:
    errs = validate(public(c.story), load_schema("story"))
    return _ok() if not errs else _fail("; ".join(errs[:5]))


def has_objective(c: Ctx, item: dict):
    return _ok() if _nonempty(c.story.get("objective")) else _missing("objective is empty")


def has_value_statement(c: Ctx, item: dict):
    return _ok() if _nonempty(c.story.get("value_statement")) else _missing("value_statement is empty")


def has_persona(c: Ctx, item: dict):
    return _ok() if _nonempty(c.story.get("persona")) else _missing("persona is empty")


def has_scope(c: Ctx, item: dict):
    if not _nonempty(c.story.get("scope")):
        return _missing("scope is empty")
    if "out_of_scope" not in c.story:
        return _missing("out_of_scope must be stated (an empty list is an explicit statement)")
    return _ok()


AC_ID = re.compile(r"^ST-(\d+)/AC-(\d+)$")


def ac_standard_errors(story: dict) -> list[str]:
    errs = []
    acs = story.get("acceptance_criteria") or []
    if not acs:
        return ["no acceptance criteria"]
    seen = set()
    for ac in acs:
        aid = ac.get("id", "")
        m = AC_ID.match(aid)
        if not m:
            errs.append(f"{aid!r}: id must look like ST-n/AC-n")
        elif f"ST-{m.group(1)}" != story.get("id"):
            errs.append(f"{aid}: AC id prefix does not match story {story.get('id')}")
        if aid in seen:
            errs.append(f"{aid}: duplicate AC id")
        seen.add(aid)
        for f in ("given", "when", "then"):
            if not _nonempty(ac.get(f)):
                errs.append(f"{aid}: '{f}' is empty")
        if ac.get("kind") not in ("functional", "negative", "nfr"):
            errs.append(f"{aid}: kind must be functional|negative|nfr")
        if ac.get("verification") not in ("automated", "manual"):
            errs.append(f"{aid}: verification must be automated|manual")
    return errs


def ac_meet_standard(c: Ctx, item: dict):
    errs = ac_standard_errors(c.story)
    return _ok(f"{len(c.acs)} AC") if not errs else _fail("; ".join(errs[:5]))


def has_negative_ac(c: Ctx, item: dict):
    return _ok() if any(a.get("kind") == "negative" for a in c.acs) \
        else _missing("no AC with kind: negative (error/edge path)")


_NUM = re.compile(r"\d")


def nfr_ac_quantified(c: Ctx, item: dict):
    bad = [a.get("id") for a in c.acs if a.get("kind") == "nfr" and not _NUM.search(str(a.get("then", "")))]
    return _ok() if not bad else _fail(f"nfr AC without a measurable number in 'then': {bad}")


def has_traceability(c: Ctx, item: dict):
    rid = c.story.get("requirement_id")
    if not rid:
        return _missing("requirement_id missing")
    if c.plans and c.plans.get("requirement") is not None and rid not in c.plans["requirement"]:
        return _fail(f"requirement {rid} not found in plans/")
    refs = c.story.get("source_refs") or []
    if not refs or not all(r.get("trust_level") for r in refs):
        return _missing("source_refs missing or without trust_level")
    return _ok()


def dependencies_resolved(c: Ctx, item: dict):
    problems = []
    for d in c.story.get("dependencies") or []:
        if d.get("status") == "UNRESOLVED":
            problems.append(f"{d.get('ref')} is UNRESOLVED")
        elif d.get("status") == "ACCEPTED_RISK" and not str(d.get("owner", "")).startswith("human:"):
            problems.append(f"{d.get('ref')} ACCEPTED_RISK without a human owner")
        elif d.get("status") not in ("RESOLVED", "UNRESOLVED", "ACCEPTED_RISK"):
            problems.append(f"{d.get('ref')} has unknown status (fail-safe: UNRESOLVED)")
    return _ok() if not problems else _missing("; ".join(problems))


def no_open_blocking_questions(c: Ctx, item: dict):
    open_q = [q.get("id") for q in c.ev("questions") if q.get("state", "OPEN") == "OPEN" and q.get("blocking")]
    return _ok() if not open_q else _missing(f"open blocking QUESTIONs: {open_q}")


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def no_unexpired_risky_assumptions(c: Ctx, item: dict):
    risky = []
    for a in c.ev("assumptions"):
        if a.get("impact", "HIGH") == "LOW":
            continue
        exp = _parse_ts(a.get("expires_at"))
        if exp is None or exp > c.now:  # no expiry recorded = treated as unexpired (fail-safe)
            risky.append(a.get("id"))
    return _ok() if not risky else _missing(f"unexpired ASSUMPTIONs with impact > LOW: {risky}")


def size_within_limit(c: Ctx, item: dict):
    size = c.story.get("size")
    if size in ALLOWED_SIZES:
        return _ok(size)
    return _fail(f"size {size!r}: must be split before READY (allowed {sorted(ALLOWED_SIZES)})")


def has_security_considerations(c: Ctx, item: dict):
    return _ok() if _nonempty(c.story.get("security_considerations")) else _missing("security_considerations empty")


def has_threat_statement(c: Ctx, item: dict):
    return _ok() if _nonempty(c.story.get("threat_statement")) else _missing("threat_statement empty")


def has_contract_refs(c: Ctx, item: dict):
    return _ok() if (c.story.get("touches") or {}).get("api_contracts") \
        else _missing("touches.api_contracts names no contract")


def has_ux(c: Ctx, item: dict):
    return _ok() if _nonempty(c.story.get("ux")) else _missing("ux expectations empty")


def _has_tag(c: Ctx, tag: str) -> bool:
    return any(tag in (a.get("tags") or []) for a in c.acs)


def has_accessibility_ac(c: Ctx, item: dict):
    return _ok() if _has_tag(c, "accessibility") else _missing("no AC tagged accessibility")


def has_rollback_plan(c: Ctx, item: dict):
    return _ok() if _nonempty(c.story.get("rollback_plan")) else _missing("rollback_plan empty")


def has_nfrs(c: Ctx, item: dict):
    if _nonempty(c.story.get("nfrs")) or any(a.get("kind") == "nfr" for a in c.acs):
        return _ok()
    return _missing("no nfrs and no nfr-kind AC")


def has_reproduction_ac(c: Ctx, item: dict):
    return _ok() if _has_tag(c, "reproduction") else _missing("no AC tagged reproduction")


def has_no_behaviour_change_ac(c: Ctx, item: dict):
    return _ok() if _has_tag(c, "no-behaviour-change") else _missing("no AC tagged no-behaviour-change")


def spike_framed(c: Ctx, item: dict):
    sp = c.story.get("spike") or {}
    if not _nonempty(sp.get("question")):
        return _missing("spike.question empty")
    tb = sp.get("timebox_days")
    if not isinstance(tb, (int, float)) or not 0.5 <= tb <= 10:
        return _fail("spike.timebox_days must be between 0.5 and 10")
    return _ok()


# -- DoD structural

def ready_at_current_ac(c: Ctx, item: dict):
    rec = (c.evidence.get("readiness") or {}).get(c.sid)
    if not rec or rec.get("status") not in POST_READY:
        return _missing("story never passed the readiness gate")
    if rec.get("ac_hash") != c.ac_hash:
        return _fail("AC changed after READY (AC freeze): story must return to REFINING")
    return _ok()


def change_sets_integrated(c: Ctx, item: dict):
    cs = c.linked_change_sets()
    if not cs:
        return _missing("no Change Set declares this story (Implements: / story_refs)")
    pending = [x.get("id") for x in cs if x.get("status") not in ("INTEGRATED", "RELEASED")]
    return _ok(f"{len(cs)} Change Set(s)") if not pending else _missing(f"not INTEGRATED: {pending}")


def automated_ac_covered(c: Ctx, item: dict):
    auto = [a["id"] for a in c.acs if a.get("verification") == "automated"]
    if not auto:
        return _ok("no automated AC")
    if not c.coverage:
        return _missing("no ac-coverage report supplied")
    acmap = c.coverage.get("acceptance_criteria", {})
    bad = [aid for aid in auto if not (acmap.get(aid) or {}).get("passing")]
    return _ok(f"{len(auto)} automated AC passing") if not bad else _missing(f"not covered by a passing test: {bad}")


def _gate_results(c: Ctx) -> dict[str, list[str]]:
    cs_ids = {x.get("id") for x in c.linked_change_sets()}
    out: dict[str, list[str]] = {}
    for g in c.evidence.get("gates", []):
        if g.get("story") != c.sid and g.get("change_set") not in cs_ids:
            continue
        if g.get("actor_type", "SYSTEM") != "SYSTEM":
            continue  # VERIFIED comes only from machine evidence ingested by the server
        out.setdefault(g.get("gate"), []).append(g.get("result"))
    return out


def _gate_ok(results: list[str] | None) -> bool:
    return bool(results) and all(r == "VERIFIED" for r in results)


def tier_gates_verified(c: Ctx, item: dict):
    required = (c.policy.get("tier_gates") or {}).get(c.tier, [])
    res = _gate_results(c)
    bad = [g for g in required if not _gate_ok(res.get(g))]
    return _ok(f"{required}") if not bad else _missing(f"gates not VERIFIED for tier {c.tier}: {bad}")


def gate_verified(c: Ctx, item: dict):
    g = item["gate"]
    return _ok() if _gate_ok(_gate_results(c).get(g)) else _missing(f"gate '{g}' not VERIFIED")


def secret_scan_clean(c: Ctx, item: dict):
    return _ok() if _gate_ok(_gate_results(c).get("secret-scan")) else _missing("gate 'secret-scan' not VERIFIED")


def _all_changed_paths(c: Ctx) -> list[str]:
    paths: list[str] = []
    for cs in c.linked_change_sets():
        paths += cs.get("changed_paths") or []
    return paths


def diff_within_scope(c: Ctx, item: dict):
    paths = _all_changed_paths(c)
    if not paths:
        return _missing("no changed_paths recorded for linked Change Sets")
    declared = c.story.get("affected_paths") or []
    problems = []
    if declared:
        mod = _path_tier_module()
        if mod is not None:
            outside = [p for p in paths if not mod.matches(mod.normalize(p), declared)]
            if outside:
                problems.append(f"outside affected_paths: {outside[:5]}")
    pt = path_tier(paths)
    if pt and TIERS.index(pt["tier"]) > TIERS.index(c.tier):
        problems.append(f"actual diff is {pt['tier']} but story was planned at {c.tier}: "
                        f"re-tier required (type/scope mismatch, §4.12)")
    return _ok() if not problems else _fail("; ".join(problems))


def spike_decision_recorded(c: Ctx, item: dict):
    ds = [d for d in c.ev("decisions") if d.get("adr_ref")]
    return _ok() if ds else _missing("no DECISION with a merged ADR reference for the spike")


def spike_follow_ups_exist(c: Ctx, item: dict):
    stories = (c.plans or {}).get("story", {})
    ups = [s for s, d in stories.items() if d.get("follow_up_of") == c.sid]
    return _ok(f"follow-ups: {ups}") if ups else _missing("no story with follow_up_of pointing at the spike")


def spike_no_production_code(c: Ctx, item: dict):
    mod = _path_tier_module()
    merged = [cs for cs in c.linked_change_sets() if cs.get("status") in ("INTEGRATED", "RELEASED")]
    offenders = []
    for cs in merged:
        for p in cs.get("changed_paths") or []:
            norm = mod.normalize(p) if mod else p
            if mod is None or not mod.matches(norm, SPIKE_ALLOWED_PATHS):
                offenders.append(p)
    return _ok() if not offenders else _fail(f"spike merged production paths: {offenders[:5]}")


STRUCTURAL_CHECKS: dict[str, Callable[[Ctx, dict], tuple[str, str]]] = {
    f.__name__: f for f in [
        schema_valid, has_objective, has_value_statement, has_persona, has_scope, ac_meet_standard,
        has_negative_ac, nfr_ac_quantified, has_traceability, dependencies_resolved,
        no_open_blocking_questions, no_unexpired_risky_assumptions, size_within_limit,
        has_security_considerations, has_threat_statement, has_contract_refs, has_ux,
        has_accessibility_ac, has_rollback_plan, has_nfrs, has_reproduction_ac,
        has_no_behaviour_change_ac, spike_framed, ready_at_current_ac, change_sets_integrated,
        automated_ac_covered, tier_gates_verified, gate_verified, secret_scan_clean,
        diff_within_scope, spike_decision_recorded, spike_follow_ups_exist, spike_no_production_code,
    ]
}


# --------------------------------------------------------------------------- judgment / approval

def _judgment_actor_ok(rec: dict, role: str) -> tuple[bool, str]:
    actor = rec.get("actor_type")
    if actor == "SYSTEM":
        return False, "SYSTEM evidence cannot satisfy a JUDGMENT"
    if rec.get("lifecycle_state", "REVIEWED") != "REVIEWED":
        return False, f"lifecycle_state {rec.get('lifecycle_state')} is not REVIEWED"
    if actor == "HUMAN":
        return True, ""
    if actor == "AGENT" and rec.get("role") == role:
        return True, ""
    return False, f"actor {actor}/{rec.get('role')} is not role {role}"


def evaluate_judgment(c: Ctx, item: dict) -> tuple[str, str]:
    role = item["role"]
    recs = [r for r in c.ev("reviews") if r.get("item") == item["id"]]
    if item.get("per_manual_ac"):
        manual = [a["id"] for a in c.acs if a.get("verification") == "manual"]
        if not manual:
            return _ok("no manual AC")
        missing = []
        for aid in manual:
            st, _ = _judge([r for r in recs if r.get("ac") == aid], role, item, c)
            if st != PASS:
                missing.append(aid)
        return _ok() if not missing else _missing(f"manual AC without verification record: {missing}")
    return _judge(recs, role, item, c)


def _judge(recs: list[dict], role: str, item: dict, c: Ctx) -> tuple[str, str]:
    notes = []
    verdict = None
    for r in recs:  # chronological; the latest valid verdict wins
        ok, why = _judgment_actor_ok(r, role)
        if not ok:
            notes.append(why)
            continue
        if item.get("pin_ac_hash") and r.get("ac_hash") != c.ac_hash:
            notes.append("review recorded against a stale AC hash")
            continue
        verdict = r.get("verdict")
    if verdict == "ACCEPT":
        return _ok(f"REVIEWED by {role}")
    if verdict == "REJECT":
        return REJECTED, f"{role} REJECTED; only a human lifts a domain rejection (§4.7)"
    return _missing(f"needs REVIEWED/ACCEPT from {role}" + (f" ({'; '.join(sorted(set(notes)))})" if notes else ""))


def evaluate_approval(c: Ctx, item: dict) -> tuple[str, str]:
    approver = item["approver"]
    for a in c.ev("approvals"):
        if a.get("item") == item["id"] and a.get("approver") == approver and a.get("actor_type") == "HUMAN":
            return _ok(f"APPROVED by {approver}")
    return _missing(f"needs authenticated APPROVAL from {approver}")


# --------------------------------------------------------------------------- policy evaluation

def evaluate_policy(policy: dict, c: Ctx, variant: str | None = None) -> dict:
    results, not_applicable = [], []
    for item in policy["items"]:
        iv = item.get("variant", "any")
        if variant and iv not in ("any", variant):
            continue
        if not applies(item, c.story, c.tier):
            not_applicable.append(item["id"])
            continue
        kind = item["check"]
        if kind == "STRUCTURAL":
            fn = STRUCTURAL_CHECKS.get(item.get("function", ""))
            status, detail = fn(c, item) if fn else (FAIL, f"unknown check function {item.get('function')}")
        elif kind == "JUDGMENT":
            status, detail = evaluate_judgment(c, item)
        elif kind == "APPROVAL":
            status, detail = evaluate_approval(c, item)
        else:
            status, detail = FAIL, f"unknown check kind {kind}"
        results.append({"id": item["id"], "check": kind, "stage": item.get("stage", policy.get("stage")),
                        "status": status, "detail": detail})
    return {"items": results, "not_applicable": not_applicable}


def find_story(plans: dict, story_id: str) -> dict | None:
    return plans.get("story", {}).get(story_id)
