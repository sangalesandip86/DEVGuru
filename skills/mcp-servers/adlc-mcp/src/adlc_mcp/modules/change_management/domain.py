"""Change Management rules — pure functions, no I/O except reading the declared path-tier files.

Plan refs: §4.5 (lifecycle, completion criteria, approval matrix, staleness, risk tiering,
tasks/checkpoints, parallel execution), §4.1 (failure catalog), §5.3 (fail-safe defaults),
§5.10 (forge as source of truth), §7 (change-size cap).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from adlc_mcp.kernel.errors import PermissionDenied, ValidationError
from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.vocab import ESCALATION_REASON_CODES, RISK_TIERS, max_tier, tier_index

# --------------------------------------------------------------------------- lifecycle
ACTIVE = ("DRAFT", "SCOPED", "PLANNED", "PLAN_APPROVED", "EXECUTING", "VERIFYING", "INTEGRATED")
TERMINAL = ("FAILED", "CANCELLED", "ROLLED_BACK")
FORWARD: dict[str, tuple[str, ...]] = {
    "DRAFT": ("SCOPED",),
    "SCOPED": ("PLANNED",),
    "PLANNED": ("PLAN_APPROVED", "SCOPED"),
    "PLAN_APPROVED": ("EXECUTING",),
    "EXECUTING": ("VERIFYING", "PLANNED"),      # PLANNED = REPLAN (needs re-approval)
    "VERIFYING": ("INTEGRATED", "EXECUTING"),   # EXECUTING = rework after failed verification
    "INTEGRATED": ("RELEASED",),
    "RELEASED": ("ROLLED_BACK",),               # ROLLED_BACK is reachable only from RELEASED
}
# Reached only through observed forge/CI events (ingest_forge_event), never update_status.
FORGE_ONLY = ("PLAN_APPROVED", "INTEGRATED", "RELEASED", "ROLLED_BACK")
BLOCK_KINDS = ("GATE_FAILED", "DEPENDENCY_UNMET", "ESCALATION")


def allowed_targets(status: str, blocked_from: str | None) -> set[str]:
    if status in TERMINAL:
        return set()
    if status == "BLOCKED":
        exits = {blocked_from, "FAILED", "CANCELLED"} - {None}
        if blocked_from == "PLAN_APPROVED":
            exits.add("PLANNED")
        if blocked_from == "INTEGRATED":
            exits.add("EXECUTING")
        return exits
    targets = set(FORWARD.get(status, ()))
    if status in ACTIVE:
        targets |= {"BLOCKED", "FAILED", "CANCELLED"}
    return targets


def check_manual_transition(
    identity: Identity, current: str, target: str, blocked_from: str | None, block_kind: str | None
) -> None:
    """Rules for update_status. Privileged states come only from forge events (§5.10)."""
    if target in FORGE_ONLY:
        raise PermissionDenied(
            f"{target} is set only from an observed forge/CI event via ingest_forge_event — "
            "never by update_status, regardless of caller"
        )
    if target not in allowed_targets(current, blocked_from):
        raise ValidationError(f"invalid transition {current} -> {target}")
    if target == "CANCELLED" and not identity.is_human:
        raise PermissionDenied("CANCELLED is a human decision")
    if current == "BLOCKED" and target == blocked_from and block_kind == "ESCALATION" and not identity.is_human:
        raise PermissionDenied("an ESCALATION block is lifted only by an authenticated human")


# --------------------------------------------------------------------------- approval matrix (§4.5)
APPROVAL_MATRIX: dict[str, dict[str, dict[str, Any]]] = {
    "LOW": {
        "plan": {"verified": True, "reviews": [], "humans": []},
        "release": {"humans": []},
    },
    "MEDIUM": {
        "plan": {"verified": True, "reviews": ["code-reviewer"], "humans": []},
        "release": {"humans": ["human:tech-lead"]},
    },
    "HIGH": {
        "plan": {"verified": True, "reviews": [], "humans": ["human:tech-lead"]},
        "release": {"humans": ["human:security-lead"]},
    },
    "CRITICAL": {
        "plan": {"verified": True, "reviews": [], "humans": ["human:security-lead", "human:product-owner"]},
        "release": {"humans": ["human:release-manager"]},
    },
}


def effective_tier(tier: str | None) -> str:
    """Fail-safe: a tier that was never computed is treated as HIGH (§5.3)."""
    return tier if tier in RISK_TIERS else "HIGH"


def plan_approval_missing(
    tier: str | None, events: list[dict[str, Any]], accepted_reviews: set[str],
    approval_epoch: int = 0,
) -> list[str]:
    req = APPROVAL_MATRIX[effective_tier(tier)]["plan"]
    missing = []
    epoch_events = [e for e in events if e.get("payload", {}).get("approval_epoch", 0) == approval_epoch]
    if req["verified"] and not any(e["event_type"] == "plan_check_passed" for e in epoch_events):
        missing.append("VERIFIED plan check (plan_check_passed CI event)")
    for role in req["reviews"]:
        if role not in accepted_reviews:
            missing.append(f"REVIEWED ACCEPT from {role}")
    approved_by = {e["payload"].get("approver_role") for e in epoch_events
                   if e["event_type"] == "codeowners_review" and e["payload"].get("state") == "approved"}
    missing += [f"APPROVED by {h}" for h in req["humans"] if h not in approved_by]
    return missing


def release_missing(tier: str | None, events: list[dict[str, Any]], environment: str) -> list[str]:
    missing = []
    if not any(e["event_type"] == "deployment" and e["payload"].get("environment") == environment
               and e["payload"].get("status") == "success" for e in events):
        missing.append(f"successful deployment record for {environment}")
    approved_by = {e["payload"].get("approver_role") for e in events
                   if e["event_type"] == "environment_approval" and e["payload"].get("environment") == environment}
    missing += [f"environment approval by {h}" for h in APPROVAL_MATRIX[effective_tier(tier)]["release"]["humans"]
                if h not in approved_by]
    return missing


FORGE_EVENT_TYPES = (
    "plan_check_passed", "codeowners_review", "pr_merged", "deployment", "environment_approval", "rollback",
)
_FORGE_REQUIRED = {
    "codeowners_review": ("approver", "approver_role", "state"),
    "pr_merged": ("repository", "commit_sha", "target_branch"),
    "deployment": ("environment", "status"),
    "environment_approval": ("approver", "approver_role", "environment"),
}


def validate_forge_event(event_type: str, payload: dict[str, Any]) -> None:
    if event_type not in FORGE_EVENT_TYPES:
        raise ValidationError(f"event_type must be one of {FORGE_EVENT_TYPES}")
    missing = [k for k in _FORGE_REQUIRED.get(event_type, ()) if not payload.get(k)]
    if missing:
        raise ValidationError(f"{event_type} payload missing {missing}")
    role = payload.get("approver_role")
    if role is not None and not str(role).startswith("human:"):
        raise ValidationError("approver_role must name a human approver (human:<role>)")


# --------------------------------------------------------------------------- risk tiering
_BUILTIN_PATH_TIERS: list[tuple[str, str]] = [
    # Control files (§4.1) — always CRITICAL.
    ("*.claude/*", "CRITICAL"), ("*.github/workflows/*", "CRITICAL"), ("*.github/agents/*", "CRITICAL"),
    ("*.github/hooks/*", "CRITICAL"), ("*.github/skills/*", "CRITICAL"), ("*.github/instructions/*", "CRITICAL"),
    ("*agents.md", "CRITICAL"), ("*claude.md", "CRITICAL"), ("*claude.local.md", "CRITICAL"),
    ("*codeowners", "CRITICAL"), ("*.mcp.json", "CRITICAL"), ("*skills/enforcement/*", "CRITICAL"),
    ("*payment*", "CRITICAL"), ("*billing*", "CRITICAL"),
    ("*auth/*", "HIGH"), ("*/migrations/*", "HIGH"), ("migrations/*", "HIGH"), ("*.proto", "HIGH"),
    ("*openapi*", "HIGH"), ("*/api/*", "HIGH"), ("*secret*", "HIGH"), ("*.tf", "HIGH"),
    ("*.md", "LOW"), ("docs/*", "LOW"), ("*/docs/*", "LOW"),
]
DEFAULT_UNMATCHED_TIER = "MEDIUM"


def _collect_patterns(obj: Any, keys=("pattern", "patterns", "paths", "globs", "path")) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, list):
        for x in obj:
            out += _collect_patterns(x, keys)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                out += _collect_patterns(v, keys)
            elif isinstance(v, (dict, list)):
                out += _collect_patterns(v, keys)
    return out


def _glob_to_fnmatch(pattern: str) -> str:
    p = pattern.lower().replace("\\", "/").replace("**/", "*").replace("/**", "/*")
    return p if p.startswith(("*", "/")) else p


def load_path_tiers(repo_root: Path | None) -> tuple[list[tuple[str, str]], str, str]:
    """Returns (rules, default_tier, source). Reads the declared files when present (tolerant of
    shape), always keeping the built-in control-file → CRITICAL rules as a floor."""
    rules: list[tuple[str, str]] = []
    default = DEFAULT_UNMATCHED_TIER
    source = "builtin"
    override = os.environ.get("ADLC_PATH_TIERS")
    tier_file = Path(override) if override else (
        repo_root / "skills/change-management/risk-tiering/path-tiers.json" if repo_root else None)
    try:
        if tier_file and tier_file.is_file():
            data = json.loads(tier_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("default_tier") in RISK_TIERS:
                default = data["default_tier"]
            entries = data.get("rules", data.get("tiers", data)) if isinstance(data, dict) else data
            if isinstance(entries, dict):        # {"CRITICAL": [patterns], ...}
                for tier, pats in entries.items():
                    if tier in RISK_TIERS:
                        rules += [(p, tier) for p in _collect_patterns(pats)]
            elif isinstance(entries, list):      # [{"pattern(s)": ..., "tier": ...}]
                for e in entries:
                    if isinstance(e, dict) and e.get("tier") in RISK_TIERS:
                        rules += [(p, e["tier"]) for p in _collect_patterns(e)]
            if rules:
                source = str(tier_file)
        cf = repo_root / "skills/governance/default-permissions/reference/control-file-paths.json" if repo_root else None
        if cf and cf.is_file():
            rules += [(p, "CRITICAL") for p in _collect_patterns(json.loads(cf.read_text(encoding="utf-8")))]
    except (OSError, ValueError):
        rules, source = [], "builtin (declared file unreadable)"
    return rules + _BUILTIN_PATH_TIERS, default, source


def path_tier(path: str, rules: list[tuple[str, str]], default: str) -> tuple[str, str | None]:
    p = path.lower().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    best, matched = None, None
    for pattern, tier in rules:
        pat = _glob_to_fnmatch(pattern)
        if fnmatch.fnmatchcase(p, pat) or fnmatch.fnmatchcase("/" + p, pat) or fnmatch.fnmatchcase(p, "*/" + pat):
            if best is None or tier_index(tier) > tier_index(best):
                best, matched = tier, pattern
    return (best or default), matched


def compute_tier(
    paths: list[str],
    reason_codes: list[str],
    assessed_tiers: list[str],
    rules: list[tuple[str, str]],
    default: str,
) -> dict[str, Any]:
    bad = [c for c in reason_codes if c not in ESCALATION_REASON_CODES]
    if bad:
        raise ValidationError(f"unknown escalation reason codes {bad}; closed list: {ESCALATION_REASON_CODES}")
    bad = [t for t in assessed_tiers if t not in RISK_TIERS]
    if bad:
        raise ValidationError(f"assessed_tiers must be in {RISK_TIERS}")
    matches = []
    if paths:
        per_path = [(p, *path_tier(p, rules, default)) for p in paths]
        base = max_tier(t for _, t, _ in per_path)
        matches = [{"path": p, "tier": t, "pattern": m} for p, t, m in per_path]
        uncomputable = False
    else:
        base, uncomputable = "HIGH", True            # tier can't be computed → HIGH (§5.3)
    base = max_tier([base, *assessed_tiers])         # roles disagree → higher wins (§5.3)
    final = base
    if reason_codes:                                 # exactly one level, never more (§4.5)
        final = RISK_TIERS[min(tier_index(base) + 1, len(RISK_TIERS) - 1)]
    return {"base_tier": base, "final_tier": final, "uncomputable": uncomputable, "matches": matches,
            "reason_codes": sorted(set(reason_codes))}


# --------------------------------------------------------------------------- snapshot staleness (§4.5)
ALWAYS_OVERLAP_CLASSES: dict[str, tuple[str, ...]] = {
    "lockfile": ("*package-lock.json", "*yarn.lock", "*pnpm-lock.yaml", "*poetry.lock", "*pipfile.lock",
                 "*cargo.lock", "*go.sum", "*gemfile.lock", "*composer.lock", "*packages.lock.json", "*uv.lock"),
    "dependency_manifest": ("*package.json", "*pyproject.toml", "*requirements*.txt", "*go.mod", "*cargo.toml",
                            "*pom.xml", "*build.gradle", "*build.gradle.kts", "*.csproj", "*gemfile", "*setup.py",
                            "*setup.cfg"),
    "iac": ("*.tf", "*.tfvars", "*dockerfile*", "*docker-compose*", "*/helm/*", "*/k8s/*", "*/kubernetes/*",
            "*.bicep", "*cloudformation*"),
    "migration": ("*/migrations/*", "migrations/*", "*/migrate/*", "*.sql"),
    "schema": ("*.proto", "*.graphql", "*.avsc", "*openapi*", "*swagger*", "*schema*.json", "*.xsd"),
    "ci_config": ("*.github/workflows/*", "*.gitlab-ci.yml", "*jenkinsfile", "*azure-pipelines.yml",
                  "*.circleci/*", "*bitbucket-pipelines.yml"),
    "feature_flags": ("*feature-flag*", "*feature_flag*", "*featureflag*", "*/flags/*", "*flags.json",
                      "*flags.yaml", "*flags.yml"),
}


def always_overlap_class(path: str) -> str | None:
    p = path.lower().replace("\\", "/")
    for cls, pats in ALWAYS_OVERLAP_CLASSES.items():
        if any(fnmatch.fnmatchcase(p, pat) for pat in pats):
            return cls
    return None


def staleness(
    pinned: dict[str, str],
    current_heads: dict[str, str],
    changed_paths: dict[str, list[str]],
    task_paths: dict[str, list[str]],
) -> dict[str, Any]:
    """Per-repo verdict. Missing information resolves to STALE (more scrutiny, never less)."""
    repos = {}
    for repo, sha in pinned.items():
        head = current_heads.get(repo)
        if head is None:
            repos[repo] = {"verdict": "STALE", "reason": "current HEAD not supplied (unknown → stale)"}
            continue
        if head == sha:
            repos[repo] = {"verdict": "CURRENT"}
            continue
        changed = changed_paths.get(repo)
        if changed is None:
            repos[repo] = {"verdict": "STALE", "reason": "HEAD moved; changed paths not supplied"}
            continue
        mine = {p.replace("\\", "/") for p in task_paths.get(repo, [])}
        overlap = sorted({p.replace("\\", "/") for p in changed} & mine)
        classes = sorted({c for p in changed if (c := always_overlap_class(p))})
        if overlap or classes:
            repos[repo] = {"verdict": "STALE", "reason": "overlapping changes since snapshot",
                           "overlapping_paths": overlap, "always_overlap_classes": classes}
        else:
            repos[repo] = {"verdict": "STALE_NON_OVERLAPPING",
                           "reason": "HEAD moved without overlap; refresh snapshot before VERIFYING"}
    overall = "STALE" if any(r["verdict"] == "STALE" for r in repos.values()) else (
        "STALE_NON_OVERLAPPING" if any(r["verdict"] == "STALE_NON_OVERLAPPING" for r in repos.values()) else "CURRENT")
    return {"verdict": overall, "repositories": repos}


# --------------------------------------------------------------------------- tasks & failure policy (§4.1)
TASK_STATUSES = ("PENDING", "IN_PROGRESS", "DONE", "BLOCKED")
ITERATION_CAP = 3
FAILURE_POLICY: dict[str, tuple[str, bool]] = {
    # failure class: (retry policy, counts toward the 3-attempt cap)
    "LOOP": ("RETRY", True),
    "INVALID_OUTPUT": ("RETRY", True),
    "TOOL_TRANSIENT": ("RETRY", True),
    "TOOL_PERSISTENT": ("STOP", False),
    "SCOPE_VIOLATION": ("ESCALATE", False),
    "PERMISSION_DENIAL": ("ESCALATE", False),
    "SECURITY_REJECTION": ("ESCALATE", False),
    "CONTEXT_EXCEEDED": ("REPLAN", False),
    "SESSION_CRASH": ("RESUME", False),
}

ARTIFACT_REF = re.compile(r"^[A-Za-z0-9_.\-/]+@[0-9a-f]{7,40}:[^\s]+$")
CONTENT_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
VERDICTS = ("ACCEPT", "REJECT")
MAX_HANDOFF_CYCLES = 3


def validate_handoff_payload(payload: dict[str, Any]) -> None:
    for i, inp in enumerate(payload.get("inputs", []) or []):
        ref = inp.get("artifact_ref", "")
        if not ARTIFACT_REF.match(ref):
            raise ValidationError(
                f"inputs[{i}].artifact_ref must be repo@sha:path where sha is 7-40 hex chars "
                f"(got {ref!r}). Example: my-repo@abc1234def:src/main.ts"
            )
        if not CONTENT_HASH.match(inp.get("content_hash", "")):
            raise ValidationError(f"inputs[{i}].content_hash must be sha256:<64 hex>")
    for i, claim in enumerate(payload.get("claims", []) or []):
        cls = claim.get("classification")
        if not claim.get("source") and cls not in ("QUESTION", "ASSUMPTION"):
            raise ValidationError(
                f"claims[{i}] has no source — evidence-gate: record it as a QUESTION or tagged ASSUMPTION"
            )
        if cls == "INFERENCE" and not claim.get("input_references"):
            raise ValidationError(
                f"claims[{i}] is an INFERENCE without input_references — INFERENCEs must cite their evidence"
            )


def diff_size_cap() -> int:
    try:
        return int(os.environ.get("ADLC_MAX_DIFF_LINES", "400"))
    except ValueError:
        return 400


def as_list(x: Iterable[str] | None) -> list[str]:
    return list(x or [])
