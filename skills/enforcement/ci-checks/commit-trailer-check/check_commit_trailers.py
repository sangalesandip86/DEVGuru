#!/usr/bin/env python3
"""CI check: commits produced under the ADLC platform carry required trailers.

Required trailers (SOC 2 CC8.1 — human author accountable, AI disclosed):
  - Co-Authored-By: (when AI assisted — vendor default on Claude Code/Copilot)
  - ADLC-Run: <run_id> (links commit to the ledger run for audit)

Usage:
    python check_commit_trailers.py --base main [--head HEAD]
    python check_commit_trailers.py --commits SHA1 SHA2 ...

Exit codes: 0 all commits compliant · 1 missing trailers found · 2 error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

COAUTHOR_RE = re.compile(r"^Co-Authored-By:\s+.+", re.MULTILINE | re.IGNORECASE)
RUN_ID_RE = re.compile(r"^ADLC-Run:\s+\S+", re.MULTILINE)
ASSISTED_RE = re.compile(r"^Assisted-by:\s+.+", re.MULTILINE | re.IGNORECASE)
AI_INDICATORS = (COAUTHOR_RE, ASSISTED_RE)


def git_log(args: list[str]) -> str:
    result = subprocess.run(
        ["git", "log", *args],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout


def check_commits(commits: list[str]) -> list[dict]:
    findings = []
    for sha in commits:
        msg = git_log(["--format=%B", "-1", sha]).strip()
        if not msg:
            continue
        has_ai = any(p.search(msg) for p in AI_INDICATORS)
        has_run_id = bool(RUN_ID_RE.search(msg))
        issues = []
        if has_ai and not has_run_id:
            issues.append("AI-authored commit missing ADLC-Run: trailer (cannot link to ledger)")
        if issues:
            findings.append({
                "commit": sha[:10],
                "subject": msg.split("\n")[0][:80],
                "issues": issues,
            })
    return findings


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="base branch for range")
    ap.add_argument("--head", default="HEAD", help="head ref (default HEAD)")
    ap.add_argument("--commits", nargs="*", help="explicit commit SHAs to check")
    args = ap.parse_args(argv)

    try:
        if args.commits:
            shas = args.commits
        elif args.base:
            log = git_log(["--format=%H", f"{args.base}...{args.head}"])
            shas = [s.strip() for s in log.strip().split("\n") if s.strip()]
        else:
            print(json.dumps({"error": "provide --base or --commits"}), file=sys.stderr)
            return 2

        if not shas:
            print(json.dumps({"ok": True, "commits_checked": 0}))
            return 0

        findings = check_commits(shas)
        result = {
            "ok": len(findings) == 0,
            "commits_checked": len(shas),
            "findings": findings,
        }
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
