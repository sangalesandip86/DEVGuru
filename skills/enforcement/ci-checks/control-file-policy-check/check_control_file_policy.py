#!/usr/bin/env python3
"""CI check: the deployed managed settings actually deny every control-file glob.

Verifies (plan §2 Phase 0, §4.11):
  1. every glob in control-file-paths.json has both `Edit(<glob>)` and `Write(<glob>)` in
     `permissions.deny`;
  2. `allowManagedHooksOnly` is true;
  3. a PreToolUse hook runs control_file_guard.py;
  4. no `permissions.allow` rule re-allows a control-file path.

Usage:
  python check_control_file_policy.py [--settings PATH] [--control-paths PATH]
Exit 0 = pass, 1 = policy violation, 2 = bad input. JSON report on stdout.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import adlc_enforcement as ae  # noqa: E402

DEFAULT_SETTINGS = HERE.parents[1] / "managed-settings" / "templates" / "claude-code-managed-settings.json"
RULE = re.compile(r"^(Edit|Write)\((.*)\)$")


def check(settings: dict, globs: list[str]) -> list[str]:
    problems: list[str] = []
    perms = settings.get("permissions", {}) or {}
    deny = set(perms.get("deny", []) or [])
    for g in globs:
        for tool in ("Edit", "Write"):
            if f"{tool}({g})" not in deny:
                problems.append(f"missing deny rule {tool}({g})")
    if settings.get("allowManagedHooksOnly") is not True:
        problems.append("allowManagedHooksOnly is not true")
    pre = (settings.get("hooks", {}) or {}).get("PreToolUse", []) or []
    commands = [h.get("command", "") for m in pre for h in m.get("hooks", [])]
    if not any("control_file_guard.py" in c for c in commands):
        problems.append("no PreToolUse hook runs control_file_guard.py")
    for rule in perms.get("allow", []) or []:
        m = RULE.match(rule)
        # Probe the allow pattern with a concrete path: `**` and `*` become one segment.
        probe = m.group(2).replace("**", "x").replace("*", "x") if m else ""
        if m and ae.match_control_path(probe, globs):
            problems.append(f"allow rule re-allows a control path: {rule}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    ap.add_argument("--control-paths", type=Path, default=None)
    args = ap.parse_args()
    try:
        settings = json.loads(args.settings.read_text(encoding="utf-8"))
        globs = ae.load_control_globs(args.control_paths)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"check": "control-file-policy", "ok": False, "error": str(exc)}))
        return 2
    problems = check(settings, globs)
    print(json.dumps({"check": "control-file-policy", "ok": not problems,
                      "globs_checked": len(globs), "problems": problems}, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
