#!/usr/bin/env python3
"""Secret scanning for ADLC projects.

Scans files for common secret patterns (API keys, tokens, passwords, private keys).

Usage:
    python adlc_scan.py src/config.py src/app.py
    python adlc_scan.py --staged
    python adlc_scan.py --pretty
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

SECRET_PATTERNS = [
    ("aws_access_key", r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"),
    ("aws_secret_key", r"(?i)aws[_\-]?secret[_\-]?access[_\-]?key[\s:=]+['\"]?[A-Za-z0-9/+=]{40}"),
    ("generic_api_key", r"(?i)(?:api[_\-]?key|apikey)[\s:=]+['\"]?[A-Za-z0-9_\-]{20,}"),
    ("generic_secret", r"(?i)(?:secret|password|passwd|pwd)[\s:=]+['\"]?[^\s'\"]{8,}"),
    ("generic_token", r"(?i)(?:token|bearer)[\s:=]+['\"]?[A-Za-z0-9_\-\.]{20,}"),
    ("private_key", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    ("github_token", r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}"),
    ("slack_token", r"xox[baprs]-[0-9A-Za-z\-]{10,}"),
    ("connection_string", r"(?i)(?:mysql|postgres|mongodb|redis)://[^\s'\"]{10,}"),
]

SKIP_EXTENSIONS = frozenset({".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".png", ".jpg",
                              ".gif", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".db", ".sqlite"})


def _scan_file(path: str) -> list[dict]:
    findings = []
    ext = os.path.splitext(path)[1].lower()
    if ext in SKIP_EXTENSIONS:
        return findings
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                for name, pattern in SECRET_PATTERNS:
                    if re.search(pattern, line):
                        findings.append({
                            "file": path, "line": line_no,
                            "pattern": name,
                            "snippet": line.strip()[:80],
                        })
    except OSError:
        pass
    return findings


def _staged_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="ADLC secret scanner")
    parser.add_argument("files", nargs="*", help="Files to scan")
    parser.add_argument("--staged", action="store_true", help="Scan git staged files")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    args = parser.parse_args()

    files = args.files
    if args.staged:
        files = _staged_files()
    if not files:
        print("No files to scan.", file=sys.stderr)
        sys.exit(0)

    all_findings: list[dict] = []
    for path in files:
        all_findings.extend(_scan_file(path))

    result = {"files_scanned": len(files), "findings": all_findings}

    if args.pretty:
        print(f"Scanned {len(files)} file(s), found {len(all_findings)} potential secret(s).")
        for f in all_findings:
            print(f"  {f['file']}:{f['line']}  [{f['pattern']}]  {f['snippet']}")
        if not all_findings:
            print("  No secrets detected.")
    else:
        json.dump(result, sys.stdout, indent=2)
        print()

    sys.exit(1 if all_findings else 0)


if __name__ == "__main__":
    main()
