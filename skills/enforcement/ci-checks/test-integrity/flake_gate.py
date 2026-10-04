#!/usr/bin/env python3
"""New-test flake gate: run new tests N times with randomized order to detect flakiness.

Before a PR can merge, every new or changed test runs N times in random order.
A flaky new test is a defect in the test — not acceptable noise. Plan section 4.13 rule 6,
ADR 0003 addition 4.

Usage:
    python flake_gate.py --runs 5 --test-command "pytest" --test-files FILE...
    python flake_gate.py --runs 5 --runner pytest [--changed-files-from git --base main]

Exit codes: 0 all stable, 1 flaky tests detected, 2 error.
"""
from __future__ import annotations

import argparse
import json
import os
import random
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
]

RUNNER_RANDOM_FLAGS: dict[str, list[str]] = {
    "pytest":  ["-p", "randomly", "--randomly-seed=random"],
    "jest":    ["--randomize"],
    "vitest":  ["--sequence.shuffle"],
    "go":      ["-shuffle=on"],
    "cargo":   [],
    "flutter": ["--test-randomize-ordering-seed=random"],
    "junit":   [],
}

RUNNER_BASE_COMMANDS: dict[str, list[str]] = {
    "pytest":  ["python", "-m", "pytest", "--tb=short", "-q"],
    "jest":    ["npx", "jest", "--no-coverage"],
    "vitest":  ["npx", "vitest", "run"],
    "go":      ["go", "test", "-v", "-count=1"],
    "cargo":   ["cargo", "test"],
    "flutter": ["flutter", "test"],
    "junit":   ["mvn", "-pl", ".", "test", "-Dtest="],
}

EXT_TO_RUNNER: dict[str, str] = {
    ".py": "pytest", ".ts": "jest", ".tsx": "jest", ".js": "jest",
    ".jsx": "jest", ".mjs": "jest", ".go": "go", ".rs": "cargo",
    ".dart": "flutter", ".java": "junit", ".kt": "junit",
}

RUN_TIMEOUT = int(os.environ.get("ADLC_FLAKE_GATE_TIMEOUT", "120"))


def is_test_file(path: str) -> bool:
    return any(p.search(path) for p in TEST_PATTERNS)


def git_diff_files(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return [f for f in result.stdout.strip().splitlines() if f and is_test_file(f)]


def detect_runner(files: list[str], explicit: str | None) -> str:
    if explicit:
        return explicit
    for f in files:
        ext = Path(f).suffix.lower()
        if ext in EXT_TO_RUNNER:
            return EXT_TO_RUNNER[ext]
    return "pytest"


def build_run_command(runner: str, test_command: str | None, test_file: str,
                      use_random: bool, seed: int) -> list[str]:
    if test_command:
        cmd = test_command.split() + [test_file]
    else:
        base_cmd = list(RUNNER_BASE_COMMANDS.get(runner, ["python", "-m", "pytest", "-q"]))
        if runner == "go":
            pkg = "./" + str(Path(test_file).parent).replace("\\", "/")
            cmd = base_cmd + [pkg]
        elif runner == "junit":
            cmd = base_cmd[:-1] + [base_cmd[-1] + Path(test_file).stem]
        else:
            cmd = base_cmd + [test_file]

    if use_random:
        random_flags = list(RUNNER_RANDOM_FLAGS.get(runner, []))
        if runner == "pytest":
            random_flags = ["-p", "randomly", f"--randomly-seed={seed}"]
        elif runner == "go":
            cmd = [c if c != "-shuffle=on" else f"-shuffle={seed}" for c in cmd]
            random_flags = [f"-shuffle={seed}"] if "-shuffle=" not in " ".join(cmd) else []
        cmd.extend(random_flags)

    return cmd


def run_single(runner: str, test_command: str | None, test_file: str,
               use_random: bool, seed: int) -> dict:
    cmd = build_run_command(runner, test_command, test_file, use_random, seed)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT,
            env={**os.environ, "CI": "1"},
        )
        return {
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "seed": seed,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "returncode": -1, "seed": seed, "error": "timeout"}
    except FileNotFoundError as exc:
        return {"passed": False, "returncode": -1, "seed": seed, "error": str(exc)}


def check_file(runner: str, test_command: str | None, test_file: str,
               num_runs: int, use_random: bool) -> dict:
    outcomes = []
    for i in range(num_runs):
        seed = random.randint(1, 999999)
        r = run_single(runner, test_command, test_file, use_random, seed)
        outcomes.append("pass" if r["passed"] else "fail")

    unique = set(outcomes)
    flaky = len(unique) > 1
    pass_count = outcomes.count("pass")
    fail_count = outcomes.count("fail")

    return {
        "file": test_file,
        "outcomes": outcomes,
        "flaky": flaky,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "flaky_rate": round(min(pass_count, fail_count) / num_runs, 3) if flaky else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=5, help="number of runs per test file (default 5)")
    ap.add_argument("--runner", choices=list(RUNNER_BASE_COMMANDS), help="test runner")
    ap.add_argument("--test-command", help="custom test command (overrides --runner)")
    ap.add_argument("--test-files", nargs="*", help="explicit test files")
    ap.add_argument("--changed-files-from", default="git", choices=["git"])
    ap.add_argument("--base", default="main", help="base branch for git diff (default main)")
    ap.add_argument("--no-random", action="store_true", help="disable random ordering")
    args = ap.parse_args(argv)

    try:
        if args.test_files:
            test_files = [f for f in args.test_files if is_test_file(f)]
        else:
            test_files = git_diff_files(args.base)

        if not test_files:
            report = {"ok": True, "classification": "FACT", "source": "flake_gate.py",
                      "runs": args.runs, "results": [], "flaky_files": [],
                      "note": "no new or modified test files found"}
            print(json.dumps(report, indent=2))
            return 0

        runner = detect_runner(test_files, args.runner)
        use_random = not args.no_random

        results = []
        for tf in test_files:
            r = check_file(runner, args.test_command, tf, args.runs, use_random)
            results.append(r)

        flaky_files = [r["file"] for r in results if r["flaky"]]
        all_failing = [r["file"] for r in results if r["fail_count"] == args.runs]
        ok = len(flaky_files) == 0

        report = {
            "ok": ok,
            "classification": "FACT",
            "source": "flake_gate.py",
            "runs": args.runs,
            "runner": runner,
            "randomized": use_random,
            "results": results,
            "flaky_files": flaky_files,
            "consistently_failing": all_failing,
            "summary": {
                "total": len(results),
                "stable_passing": sum(1 for r in results if not r["flaky"] and r["pass_count"] == args.runs),
                "stable_failing": len(all_failing),
                "flaky": len(flaky_files),
            },
        }
        print(json.dumps(report, indent=2))
        return 0 if ok else 1

    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
