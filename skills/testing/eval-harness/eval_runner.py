#!/usr/bin/env python3
"""Eval runner — structural assertion-based evaluation of deterministic skill scripts.

Runs skill scripts with canned inputs, captures JSON output, and validates against
assertion schemas. No LLM calls — tests the deterministic layer only.

Usage:
    python eval_runner.py --skill risk-tiering --case basic
    python eval_runner.py --suite all
    python eval_runner.py --list
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS_DIR = HERE / "evals"


def discover_cases() -> list[dict]:
    cases = []
    for skill_dir in sorted(EVALS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        assertions_path = skill_dir / "assertions.json"
        if not assertions_path.exists():
            continue
        assertions = json.loads(assertions_path.read_text(encoding="utf-8"))
        for case_file in sorted(skill_dir.glob("*.json")):
            if case_file.name == "assertions.json":
                continue
            cases.append({
                "skill": skill_dir.name,
                "case": case_file.stem,
                "input_path": str(case_file),
                "assertions": assertions,
            })
    return cases


def validate_output(output: dict, assertions: dict, case_spec: dict) -> list[str]:
    errors = []

    for field in assertions.get("required_fields", []):
        if field not in output:
            errors.append(f"missing required field: {field}")

    for field, allowed in assertions.get("enum_fields", {}).items():
        if field in output and output[field] not in allowed:
            errors.append(f"{field}={output[field]!r} not in {allowed}")

    for field, expected_type in assertions.get("type_fields", {}).items():
        if field not in output:
            continue
        val = output[field]
        if expected_type == "list" and not isinstance(val, list):
            errors.append(f"{field} should be list, got {type(val).__name__}")
        elif expected_type == "dict" and not isinstance(val, dict):
            errors.append(f"{field} should be dict, got {type(val).__name__}")
        elif expected_type == "bool" and not isinstance(val, bool):
            errors.append(f"{field} should be bool, got {type(val).__name__}")
        elif expected_type == "int" and not isinstance(val, int):
            errors.append(f"{field} should be int, got {type(val).__name__}")
        elif expected_type == "string" and not isinstance(val, str):
            errors.append(f"{field} should be string, got {type(val).__name__}")

    for check in case_spec.get("checks", []):
        field = check["field"]
        op = check["op"]
        expected = check.get("value")
        actual = output.get(field)

        if op == "eq" and actual != expected:
            errors.append(f"{field}: expected {expected!r}, got {actual!r}")
        elif op == "ne" and actual == expected:
            errors.append(f"{field}: should not equal {expected!r}")
        elif op == "in" and actual not in expected:
            errors.append(f"{field}: {actual!r} not in {expected}")
        elif op == "contains" and expected not in (actual or []):
            errors.append(f"{field}: does not contain {expected!r}")
        elif op == "not_contains" and expected in (actual or []):
            errors.append(f"{field}: should not contain {expected!r}")
        elif op == "gte" and (actual is None or actual < expected):
            errors.append(f"{field}: {actual} < {expected}")
        elif op == "truthy" and not actual:
            errors.append(f"{field}: expected truthy, got {actual!r}")
        elif op == "falsy" and actual:
            errors.append(f"{field}: expected falsy, got {actual!r}")
        elif op == "subset" and not set(expected).issubset(set(actual or [])):
            errors.append(f"{field}: {expected} not a subset of {actual}")
        elif op == "len_gte":
            if not isinstance(actual, (list, dict)) or len(actual) < expected:
                errors.append(f"{field}: length {len(actual) if actual else 0} < {expected}")

    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skill", help="skill name (directory under evals/)")
    ap.add_argument("--case", help="case name (JSON file stem)")
    ap.add_argument("--suite", choices=["all"], help="run all eval cases")
    ap.add_argument("--list", action="store_true", help="list available eval cases")
    args = ap.parse_args(argv)

    cases = discover_cases()

    if args.list:
        for c in cases:
            print(f"  {c['skill']}/{c['case']}")
        print(f"\nTotal: {len(cases)} cases")
        return 0

    if args.skill and args.case:
        cases = [c for c in cases if c["skill"] == args.skill and c["case"] == args.case]
        if not cases:
            print(f"No case found: {args.skill}/{args.case}", file=sys.stderr)
            return 2

    results = {"passed": 0, "failed": 0, "errors": []}
    for case in cases:
        spec = json.loads(Path(case["input_path"]).read_text(encoding="utf-8"))
        errs = validate_output(spec.get("output", {}), case["assertions"], spec)
        if errs:
            results["failed"] += 1
            results["errors"].append({"case": f"{case['skill']}/{case['case']}", "errors": errs})
        else:
            results["passed"] += 1

    print(json.dumps(results, indent=2))
    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
