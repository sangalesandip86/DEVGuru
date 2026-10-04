#!/usr/bin/env python3
"""Impact plan check: verify that the test files in a PR match the declared impact plan.

The impact plan (from suite-authoring) declares which test files will be created or modified.
This check ensures no undeclared test files sneak in (scope creep) and no declared files
are missing (incomplete implementation). Plan section 4.13, ADR 0003.

Usage:
    python impact_plan_check.py --plan plans/test-designs/ST-1/impact-plan.json --base main
    python impact_plan_check.py --plan FILE --actual-files FILE...

Exit codes: 0 plan matches reality, 1 mismatch, 2 error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TEST_PATTERNS = [
    re.compile(r"test_[^/]*\.py$"),
    re.compile(r"[^/]*_test\.py$"),
    re.compile(r"[^/]*\.test\.[cm]?[jt]sx?$"),
    re.compile(r"[^/]*\.spec\.[cm]?[jt]sx?$"),
    re.compile(r"[^/]*_test\.go$"),
    re.compile(r"[^/]*_test\.rs$"),
    re.compile(r"[^/]*_test\.dart$"),
    re.compile(r"Tests?\.(java|kt|cs|swift)$"),
    re.compile(r"[^/]*_spec\.rb$"),
    re.compile(r"\.feature$"),
]


def is_test_file(path: str) -> bool:
    return any(p.search(path) for p in TEST_PATTERNS)


def git_changed_test_files(base: str) -> dict[str, str]:
    result = subprocess.run(
        ["git", "diff", "--name-status", "--diff-filter=ADMR", f"{base}...HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    files: dict[str, str] = {}
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0][0]
        path = parts[-1]
        if is_test_file(path):
            action_map = {"A": "create", "M": "modify", "D": "delete", "R": "modify"}
            files[path] = action_map.get(status, "modify")
    return files


def load_impact_plan(plan_path: str) -> list[dict]:
    data = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    files = data.get("files") or data.get("impact_plan", {}).get("files", [])
    if not isinstance(files, list):
        raise ValueError("impact plan must have a 'files' array with {path, action, reason}")
    return files


def normalize(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def compare(planned: list[dict], actual: dict[str, str]) -> dict:
    planned_paths = {normalize(f["path"]): f for f in planned}
    actual_paths = {normalize(p): a for p, a in actual.items()}

    matched = []
    undeclared = []
    missing = []
    action_mismatch = []

    for path, action in actual_paths.items():
        if path in planned_paths:
            plan_entry = planned_paths[path]
            plan_action = plan_entry.get("action", "modify")
            if plan_action == action:
                matched.append({"path": path, "action": action, "reason": plan_entry.get("reason", "")})
            else:
                action_mismatch.append({
                    "path": path,
                    "planned_action": plan_action,
                    "actual_action": action,
                    "reason": plan_entry.get("reason", ""),
                })
        else:
            undeclared.append({"path": path, "actual_action": action})

    for path, entry in planned_paths.items():
        if path not in actual_paths:
            plan_action = entry.get("action", "modify")
            if plan_action != "delete":
                missing.append({"path": path, "planned_action": plan_action,
                                "reason": entry.get("reason", "")})

    return {
        "matched": matched,
        "undeclared": undeclared,
        "missing": missing,
        "action_mismatch": action_mismatch,
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True, help="path to impact-plan.json")
    ap.add_argument("--base", default="main", help="base branch for git diff (default main)")
    ap.add_argument("--actual-files", nargs="*",
                    help="explicit list of changed test files (overrides git diff)")
    args = ap.parse_args(argv)

    try:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            raise FileNotFoundError(f"impact plan not found: {args.plan}")
        planned = load_impact_plan(args.plan)

        if args.actual_files:
            actual = {f: "modify" for f in args.actual_files if is_test_file(f)}
        else:
            actual = git_changed_test_files(args.base)

        result = compare(planned, actual)
        ok = len(result["undeclared"]) == 0 and len(result["missing"]) == 0

        report = {
            "ok": ok,
            "classification": "FACT",
            "source": "impact_plan_check.py",
            "plan_file": args.plan,
            "planned_count": len(planned),
            "actual_count": len(actual),
            **result,
            "summary": {
                "matched": len(result["matched"]),
                "undeclared": len(result["undeclared"]),
                "missing": len(result["missing"]),
                "action_mismatch": len(result["action_mismatch"]),
            },
            "verdict": "PASS" if ok else "FAIL",
        }

        if result["undeclared"]:
            report["note_undeclared"] = ("Undeclared test files found. Either add them to the "
                                         "impact plan or remove them from the PR.")
        if result["missing"]:
            report["note_missing"] = ("Declared test files not found in the PR. Either implement "
                                       "them or update the impact plan.")

        print(json.dumps(report, indent=2))
        return 0 if ok else 1

    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
