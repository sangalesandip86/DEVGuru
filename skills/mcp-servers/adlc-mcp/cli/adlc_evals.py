#!/usr/bin/env python3
"""Run deterministic regression suite. Wraps replay_runner.py.

Usage:
    python adlc_evals.py golden-cases/
    python adlc_evals.py golden-cases/risk.json
    python adlc_evals.py --check
    python adlc_evals.py golden-cases/ --pretty
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RUNNER = REPO_ROOT / "skills" / "testing" / "deterministic-regression" / "scripts" / "replay_runner.py"


def _run_replay(target: str, check: bool = False) -> dict:
    cmd = [sys.executable, str(RUNNER)]
    if check:
        cmd.append("--check")
    else:
        cmd.append(target)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "target": target}
    except OSError as e:
        return {"status": "error", "error": str(e)}

    lines = result.stdout.strip().splitlines()
    try:
        output = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        output = {"raw_output": result.stdout.strip()}

    return {
        "status": "pass" if result.returncode == 0 else "fail",
        "returncode": result.returncode,
        "output": output,
        "stderr": result.stderr.strip() if result.stderr.strip() else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ADLC deterministic regression suite")
    parser.add_argument("target", nargs="?", help="Golden cases directory or file")
    parser.add_argument("--check", action="store_true", help="Run built-in self-test")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    args = parser.parse_args()

    if not RUNNER.is_file():
        print(json.dumps({"error": f"replay_runner.py not found at {RUNNER}"}))
        sys.exit(1)

    if not args.target and not args.check:
        parser.error("either target or --check is required")

    result = _run_replay(args.target or "", args.check)

    if args.pretty:
        status = result["status"]
        icon = "PASS" if status == "pass" else "FAIL"
        print(f"[{icon}] Regression suite: {status}")
        if result.get("stderr"):
            print(f"  stderr: {result['stderr'][:200]}")
        output = result.get("output", {})
        if isinstance(output, dict):
            for k, v in output.items():
                if k != "raw_output":
                    print(f"  {k}: {v}")
            if "raw_output" in output:
                print(f"  output: {output['raw_output'][:300]}")
        print(f"  exit code: {result.get('returncode', '?')}")
    else:
        json.dump(result, sys.stdout, indent=2)
        print()

    sys.exit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
