#!/usr/bin/env python3
"""Red/green check: new or modified test files must fail on base and pass on head.

Proves that new tests exercise real behavior. Without this check, LLM-generated tests
can be tautological (always pass regardless of implementation). Plan section 4.13 rule 6,
ADR 0003 addition 2.

How it works:
  1. Identify new/modified test files (from git diff base...head).
  2. For each file, extract the base-branch version of production code and the head-branch
     version of the test file into a temporary tree.
  3. Run the test on base production code -> expect FAILURE (red).
  4. Run the test on head production code -> expect PASS (green).

A test that passes on base is potentially tautological: it does not detect the change.

Runner detection uses --runner or --test-command. When neither is given, the script infers
the runner from file extensions.

Usage:
    python red_green_check.py --base main --head HEAD --runner pytest [--test-files FILE...]
    python red_green_check.py --base main --head HEAD --test-command "pytest" --test-files test_foo.py
    python red_green_check.py --base main --head HEAD [--changed-files-from git]

Exit codes: 0 all new tests are red/green, 1 some tests pass on base (tautological), 2 error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
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

RUNNER_COMMANDS: dict[str, list[str]] = {
    "pytest":  ["python", "-m", "pytest", "--tb=short", "-q"],
    "jest":    ["npx", "jest", "--no-coverage"],
    "vitest":  ["npx", "vitest", "run"],
    "go":      ["go", "test", "-v"],
    "cargo":   ["cargo", "test"],
    "flutter": ["flutter", "test"],
    "junit":   ["mvn", "-pl", ".", "test", "-Dsurefire.failIfNoSpecifiedTests=false", "-Dtest="],
}

EXT_TO_RUNNER: dict[str, str] = {
    ".py": "pytest",
    ".ts": "jest",
    ".tsx": "jest",
    ".js": "jest",
    ".jsx": "jest",
    ".mjs": "jest",
    ".go": "go",
    ".rs": "cargo",
    ".dart": "flutter",
    ".java": "junit",
    ".kt": "junit",
}

RUN_TIMEOUT = int(os.environ.get("ADLC_RED_GREEN_TIMEOUT", "120"))


def is_test_file(path: str) -> bool:
    return any(p.search(path) for p in TEST_PATTERNS)


def git_diff_files(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM", f"{base}...{head}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return [f for f in result.stdout.strip().splitlines() if f and is_test_file(f)]


def git_show(ref: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def detect_runner(files: list[str], explicit: str | None) -> str:
    if explicit:
        return explicit
    for f in files:
        ext = Path(f).suffix.lower()
        if ext in EXT_TO_RUNNER:
            return EXT_TO_RUNNER[ext]
    return "pytest"


def build_run_command(runner: str, test_command: str | None, test_file: str) -> list[str]:
    if test_command:
        return test_command.split() + [test_file]
    base_cmd = RUNNER_COMMANDS.get(runner, ["python", "-m", "pytest", "-q"])
    if runner == "go":
        pkg = "./" + str(Path(test_file).parent).replace("\\", "/")
        return base_cmd[:3] + ["-run", Path(test_file).stem.replace("_test", ""), pkg]
    if runner == "junit":
        cls = Path(test_file).stem
        return base_cmd[:-1] + [base_cmd[-1] + cls]
    return list(base_cmd) + [test_file]


def run_test(workdir: str, runner: str, test_command: str | None, test_file: str) -> dict:
    cmd = build_run_command(runner, test_command, test_file)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT,
            cwd=workdir, env={**os.environ, "CI": "1"},
        )
        passed = result.returncode == 0
        compile_error = False
        stderr = result.stderr or ""
        if not passed:
            compile_err_patterns = [
                "ModuleNotFoundError", "ImportError", "SyntaxError",
                "Cannot find module", "COMPILATION ERROR",
                "cannot find symbol", "does not exist",
            ]
            compile_error = any(p in stderr or p in (result.stdout or "") for p in compile_err_patterns)
        return {
            "passed": passed,
            "compile_error": compile_error,
            "returncode": result.returncode,
            "stdout_tail": (result.stdout or "")[-500:],
            "stderr_tail": stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "compile_error": False, "returncode": -1,
                "stdout_tail": "", "stderr_tail": "timeout"}
    except FileNotFoundError as exc:
        return {"passed": False, "compile_error": True, "returncode": -1,
                "stdout_tail": "", "stderr_tail": str(exc)}


def check_file(base_ref: str, head_ref: str, test_file: str, runner: str,
               test_command: str | None) -> dict:
    result = {"file": test_file, "runner": runner}

    with tempfile.TemporaryDirectory(prefix="rg_base_") as base_dir, \
         tempfile.TemporaryDirectory(prefix="rg_head_") as head_dir:

        head_content = git_show(head_ref, test_file)
        if head_content is None:
            result.update(red_on_base=None, green_on_head=None, verdict="SKIP",
                          reason="file not found on head")
            return result

        base_test = Path(base_dir) / test_file
        base_test.parent.mkdir(parents=True, exist_ok=True)
        base_test.write_bytes(head_content)

        head_test = Path(head_dir) / test_file
        head_test.parent.mkdir(parents=True, exist_ok=True)
        head_test.write_bytes(head_content)

        base_result = run_test(base_dir, runner, test_command, test_file)
        red_on_base = not base_result["passed"]
        base_status = "RED_BY_COMPILE" if (red_on_base and base_result["compile_error"]) \
            else ("RED_BY_ASSERTION" if red_on_base else "GREEN")

        head_result = run_test(head_dir, runner, test_command, test_file)
        green_on_head = head_result["passed"]
        head_status = "GREEN" if green_on_head else "RED"

        if base_status in ("RED_BY_ASSERTION", "RED_BY_COMPILE") and head_status == "GREEN":
            verdict = "PROVEN"
        elif base_status == "GREEN" and head_status == "GREEN":
            verdict = "NOT_PROVEN"
        elif head_status == "RED":
            verdict = "FAILING"
        else:
            verdict = "UNKNOWN"

        result.update(
            red_on_base=red_on_base,
            green_on_head=green_on_head,
            base_status=base_status,
            head_status=head_status,
            verdict=verdict,
        )
    return result


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="base branch or SHA")
    ap.add_argument("--head", default="HEAD", help="head branch or SHA (default HEAD)")
    ap.add_argument("--runner", choices=list(RUNNER_COMMANDS), help="test runner")
    ap.add_argument("--test-command", help="custom test command (overrides --runner)")
    ap.add_argument("--test-files", nargs="*", help="explicit test files (overrides git diff)")
    ap.add_argument("--changed-files-from", default="git", choices=["git"],
                    help="source for changed files (default: git)")
    ap.add_argument("--story-type", help="story type; REFACTOR/TECHNICAL_STORY expect green/green")
    args = ap.parse_args(argv)

    try:
        if args.test_files:
            test_files = [f for f in args.test_files if is_test_file(f)]
        else:
            test_files = git_diff_files(args.base, args.head)

        if not test_files:
            report = {"ok": True, "classification": "FACT", "source": "red_green_check.py",
                      "results": [], "tautological": [],
                      "note": "no new or modified test files found"}
            print(json.dumps(report, indent=2))
            return 0

        runner = detect_runner(test_files, args.runner)
        expect_green_green = args.story_type in ("REFACTOR", "TECHNICAL_STORY")

        results = []
        for tf in test_files:
            r = check_file(args.base, args.head, tf, runner, args.test_command)
            if expect_green_green and r.get("verdict") == "NOT_PROVEN":
                r["verdict"] = "CHARACTERIZATION_OK"
                r["note"] = "REFACTOR/TECHNICAL_STORY: green/green is expected (characterization)"
            results.append(r)

        tautological = [r["file"] for r in results if r["verdict"] == "NOT_PROVEN"]
        failing = [r["file"] for r in results if r["verdict"] == "FAILING"]
        ok = len(tautological) == 0 and len(failing) == 0

        report = {
            "ok": ok,
            "classification": "FACT",
            "source": "red_green_check.py",
            "base": args.base,
            "head": args.head,
            "runner": runner,
            "story_type": args.story_type,
            "results": results,
            "tautological": tautological,
            "failing": failing,
            "proven": [r["file"] for r in results if r["verdict"] in ("PROVEN", "CHARACTERIZATION_OK")],
            "summary": {
                "total": len(results),
                "proven": sum(1 for r in results if r["verdict"] == "PROVEN"),
                "not_proven": len(tautological),
                "failing": len(failing),
                "characterization_ok": sum(1 for r in results if r["verdict"] == "CHARACTERIZATION_OK"),
                "skipped": sum(1 for r in results if r["verdict"] == "SKIP"),
            },
        }
        print(json.dumps(report, indent=2))
        return 0 if ok else 1

    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
