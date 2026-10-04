#!/usr/bin/env python3
"""Detect flaky tests from JUnit XML reports of repeated runs.

A test is flaky when, against the same code, it both passed and failed across
runs. Skipped results are ignored for the verdict but counted.

Usage:
    flaky-detector.py run1.xml run2.xml ... [--min-runs 2] [--threshold 0.0]
    flaky-detector.py --dir reports/ [--glob "*.xml"]

Each positional file (or each file under --dir) is treated as one run.
Output: JSON on stdout. Exit 0 = no flaky tests, 1 = flaky tests found,
2 = input error.
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PASS, FAIL, SKIP = "pass", "fail", "skip"


def parse_report(path: Path) -> dict[str, str]:
    """Return {test_id: outcome} for one JUnit XML file."""
    root = ET.parse(path).getroot()
    results: dict[str, str] = {}
    for case in root.iter("testcase"):
        classname = case.get("classname") or case.get("file") or ""
        name = case.get("name") or ""
        test_id = f"{classname}::{name}" if classname else name
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = FAIL
        elif case.find("skipped") is not None:
            outcome = SKIP
        else:
            outcome = PASS
        # A test id repeated within one file (e.g. retries) counts as failing
        # in that run if any attempt failed, and is itself a flake signal.
        prev = results.get(test_id)
        if prev is None or prev == SKIP:
            results[test_id] = outcome
        elif prev != "mixed" and outcome != SKIP and prev != outcome:
            results[test_id] = "mixed"
    return results


def analyze(runs: list[dict[str, str]], min_runs: int = 2, threshold: float = 0.0) -> dict:
    tests: dict[str, dict[str, int]] = {}
    for run in runs:
        for test_id, outcome in run.items():
            counts = tests.setdefault(test_id, {PASS: 0, FAIL: 0, SKIP: 0, "mixed": 0})
            counts[outcome] += 1

    flaky = []
    stable_failures = []
    for test_id, c in sorted(tests.items()):
        executed = c[PASS] + c[FAIL] + c["mixed"]
        if executed < min_runs and c["mixed"] == 0:
            continue
        failing = c[FAIL] + c["mixed"]
        if c["mixed"] or (c[PASS] and c[FAIL]):
            flake_rate = round(failing / executed, 4) if executed else 0.0
            if flake_rate > threshold or c["mixed"]:
                flaky.append({
                    "test": test_id,
                    "runs": executed,
                    "passed": c[PASS],
                    "failed": c[FAIL],
                    "retried_within_run": c["mixed"],
                    "skipped": c[SKIP],
                    "flake_rate": flake_rate,
                })
        elif executed and c[FAIL] == executed:
            stable_failures.append({"test": test_id, "runs": executed})

    flaky.sort(key=lambda t: (-t["flake_rate"], t["test"]))
    return {
        "classification": "FACT",
        "runs_analyzed": len(runs),
        "tests_seen": len(tests),
        "flaky_count": len(flaky),
        "suite_flake_rate": round(len(flaky) / len(tests), 4) if tests else 0.0,
        "flaky": flaky,
        "consistently_failing": stable_failures,
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("reports", nargs="*", type=Path, help="JUnit XML files, one per run")
    p.add_argument("--dir", type=Path, help="directory of JUnit XML files")
    p.add_argument("--glob", default="*.xml")
    p.add_argument("--min-runs", type=int, default=2)
    p.add_argument("--threshold", type=float, default=0.0,
                   help="report only tests whose flake rate exceeds this")
    args = p.parse_args(argv)

    files = list(args.reports)
    if args.dir:
        files += sorted(args.dir.glob(args.glob))
    if len(files) < 2:
        print(json.dumps({"error": "need at least two run reports"}), file=sys.stderr)
        return 2
    try:
        runs = [parse_report(f) for f in files]
    except (OSError, ET.ParseError) as exc:
        print(json.dumps({"error": f"cannot parse report: {exc}"}), file=sys.stderr)
        return 2

    result = analyze(runs, args.min_runs, args.threshold)
    result["sources"] = [str(f) for f in files]
    print(json.dumps(result, indent=2))
    return 1 if result["flaky"] else 0


if __name__ == "__main__":
    sys.exit(main())
