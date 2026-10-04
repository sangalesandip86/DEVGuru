#!/usr/bin/env python3
"""Phase 0 path-based risk-tier lookup (plan §2 Phase 0, §5.3, §7).

Given changed file paths, return the highest risk tier with the rules that matched.

Tier rules, in order of precedence:
  * Control-file path (governance control-file-paths.json)  -> CRITICAL, always.
  * Path matches a rule in path-tiers.json                  -> that rule's tier.
  * Path matches only docs_only patterns                    -> LOW.
  * Any other path                                          -> default_tier (MEDIUM).
  * No paths, or config cannot be loaded                    -> uncomputable_tier (HIGH).
The overall tier is the maximum across paths. Diff size above the cap sets
decompose_required (plan §7); it does not change the tier.

Importable: `compute_path_tier(paths, changed_lines=None)` returns the result dict, and
`effective_tier(type_floor, path_tier, computed_tier)` combines tiers per v3.1 §4.12.

Exit codes: 0 = computed, 2 = usage error, 3 = tier fell back to uncomputable.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

TIERS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE.parent / "path-tiers.json"
DEFAULT_CONTROL_FILES = (
    HERE.parents[2] / "governance" / "default-permissions" / "reference" / "control-file-paths.json"
)

# Used only when the governance control-file list is absent or unreadable.
FALLBACK_CONTROL_FILES = [
    ".claude/**", ".github/agents/**", ".github/skills/**", ".github/instructions/**",
    ".github/copilot-instructions.md", ".github/hooks/**", ".mcp.json", "**/.mcp.json",
    ".vscode/mcp.json", "AGENTS.md", "**/AGENTS.md", "CLAUDE.md", "**/CLAUDE.md",
    "CLAUDE.local.md", "**/CLAUDE.local.md", "CODEOWNERS", ".github/CODEOWNERS",
    "docs/CODEOWNERS", ".github/rulesets/**", ".github/workflows/**", ".gitlab-ci.yml",
    "azure-pipelines.yml", "Jenkinsfile", "skills/**", "dist/**",
]


@lru_cache(maxsize=None)
def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a repo-relative glob ('**' = any depth, '*' = within a segment)."""
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path: str, patterns: list[str]) -> list[str]:
    return [p for p in patterns if glob_to_regex(p).match(path)]


def normalize(path: str) -> str:
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def load_control_files(path: Path) -> tuple[list[str], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        patterns = [g for globs in data["categories"].values() for g in globs]
        if not patterns:
            raise ValueError("empty control-file list")
        return patterns, str(path)
    except (OSError, ValueError, KeyError, TypeError):
        return FALLBACK_CONTROL_FILES, "embedded-fallback"


def max_tier(a: str, b: str) -> str:
    return a if TIERS.index(a) >= TIERS.index(b) else b


def lookup(paths: list[str], config: dict, control_files: list[str],
           changed_lines: int | None = None) -> dict:
    uncomputable = config.get("uncomputable_tier", "HIGH")
    paths = [normalize(p) for p in paths if p.strip()]
    if not paths:
        return {
            "tier": uncomputable,
            "computed": False,
            "reason": "NO_INPUT: no changed paths supplied; fail-safe default applied (§5.3)",
            "paths": [],
            "reason_codes": [],
            "decompose_required": False,
        }

    default_tier = config.get("default_tier", "MEDIUM")
    docs = config.get("docs_only", {})
    overall = "LOW"
    reason_codes: set[str] = set()
    results = []
    for path in paths:
        hits = []
        tier = None
        cf = matches(path, control_files)
        if cf:
            tier = "CRITICAL"
            hits.append({"rule": "control-files", "tier": "CRITICAL", "patterns": cf})
            reason_codes.add("SENSITIVE_PATH")
        for rule in config.get("rules", []):
            m = matches(path, rule["patterns"])
            if m:
                hits.append({"rule": rule["id"], "tier": rule["tier"], "patterns": m})
                tier = rule["tier"] if tier is None else max_tier(tier, rule["tier"])
                if rule.get("reason_code") and TIERS.index(rule["tier"]) >= TIERS.index("HIGH"):
                    reason_codes.add(rule["reason_code"])
        if tier is None:
            m = matches(path, docs.get("patterns", []))
            if m:
                tier = docs.get("tier", "LOW")
                hits.append({"rule": "docs_only", "tier": tier, "patterns": m})
            else:
                tier = default_tier
                hits.append({"rule": "default", "tier": tier, "patterns": []})
        overall = max_tier(overall, tier)
        results.append({"path": path, "tier": tier, "matched": hits})

    cap = config.get("diff_size_cap", {})
    reasons = []
    if cap.get("max_files") is not None and len(paths) > cap["max_files"]:
        reasons.append(f"{len(paths)} files > max_files {cap['max_files']}")
    if changed_lines is not None and cap.get("max_changed_lines") is not None \
            and changed_lines > cap["max_changed_lines"]:
        reasons.append(f"{changed_lines} changed lines > max_changed_lines {cap['max_changed_lines']}")

    return {
        "tier": overall,
        "computed": True,
        "reason": "highest tier across changed paths",
        "paths": results,
        "reason_codes": sorted(reason_codes),
        "changed_lines": changed_lines,
        "decompose_required": bool(reasons),
        "decompose_reasons": reasons,
    }


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compute_path_tier(paths: list[str], changed_lines: int | None = None,
                      config_path: Path = DEFAULT_CONFIG,
                      control_files_path: Path = DEFAULT_CONTROL_FILES) -> dict:
    """Public API for importers (e.g. product-planning readiness_gate.py).

    Returns the same dict as the CLI: {"tier", "computed", "paths": [{path, tier, matched}],
    "reason_codes", "decompose_required", ...}. Never raises on bad config: falls back to the
    uncomputable tier (HIGH) with computed=False.
    """
    try:
        config = load_config(config_path)
    except (OSError, ValueError) as exc:
        return {"tier": "HIGH", "computed": False, "paths": [], "reason_codes": [],
                "decompose_required": False,
                "reason": f"CONFIG_ERROR: {exc}; fail-safe default applied (§5.3)"}
    control_files, source = load_control_files(Path(control_files_path))
    result = lookup(paths, config, control_files, changed_lines)
    result["control_files_source"] = source
    return result


def effective_tier(*tiers: str | None) -> str:
    """Effective tier = max(story-type floor, path tier, computed tier) (v3.1 §4.12).

    None entries (no floor / not computed) are ignored; a type floor can raise the tier but never
    lower it. With no tiers at all, returns HIGH (uncomputable, §5.3).
    """
    present = [t for t in tiers if t]
    for t in present:
        if t not in TIERS:
            raise ValueError(f"unknown tier: {t}")
    if not present:
        return "HIGH"
    out = present[0]
    for t in present[1:]:
        out = max_tier(out, t)
    return out


def git_changes(base: str, repo: str) -> tuple[list[str], int]:
    out = subprocess.run(
        ["git", "-C", repo, "diff", "--numstat", base],
        check=True, capture_output=True, text=True,
    ).stdout
    paths, lines = [], 0
    for row in out.splitlines():
        added, deleted, path = row.split("\t", 2)
        paths.append(path)
        if added != "-":
            lines += int(added) + int(deleted)
    return paths, lines


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", help="changed file paths (repo-relative)")
    ap.add_argument("--stdin", action="store_true", help="read newline-separated paths from stdin")
    ap.add_argument("--git-base", help="compute changed paths and lines with `git diff --numstat BASE`")
    ap.add_argument("--repo", default=".", help="repository root for --git-base")
    ap.add_argument("--changed-lines", type=int, help="total added+deleted lines, for the diff-size cap")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--control-files", type=Path, default=DEFAULT_CONTROL_FILES)
    ap.add_argument("--type-floor", choices=TIERS,
                    help="story-type tier floor (product-planning/policies/story-types.yaml); "
                         "reported as effective_tier = max(floor, path tier)")
    args = ap.parse_args(argv)

    paths = list(args.paths)
    changed_lines = args.changed_lines
    if args.stdin:
        paths += sys.stdin.read().splitlines()
    try:
        if args.git_base:
            git_paths, git_lines = git_changes(args.git_base, args.repo)
            paths += git_paths
            if changed_lines is None:
                changed_lines = git_lines
        config = load_config(args.config)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({
            "tier": "HIGH", "computed": False,
            "reason": f"CONFIG_OR_INPUT_ERROR: {exc}; fail-safe default applied (§5.3)",
        }, indent=2))
        return 3

    control_files, control_source = load_control_files(args.control_files)
    result = lookup(paths, config, control_files, changed_lines)
    result["control_files_source"] = control_source
    if args.type_floor:
        result["type_floor"] = args.type_floor
        result["effective_tier"] = effective_tier(args.type_floor, result["tier"])
    print(json.dumps(result, indent=2))
    return 0 if result["computed"] else 3


if __name__ == "__main__":
    sys.exit(main())
