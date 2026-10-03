#!/usr/bin/env python3
"""CI check: every AGENTS.md has a sibling CLAUDE.md that imports it (plan §8, §9 step 2).

Claude Code reads AGENTS.md only as a fallback when no CLAUDE.md exists, so the platform keeps
AGENTS.md as the source of truth and places a one-line `@AGENTS.md` CLAUDE.md beside each one.

Usage: python check_agents_md_shim.py [--root DIR] [--strict]
  --strict  also require CLAUDE.md to contain nothing but `@AGENTS.md`
Exit 0 = pass, 1 = violation. JSON report on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist", ".adlc"}


def find_agents_md(root: Path) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if "AGENTS.md" in filenames:
            found.append(Path(dirpath) / "AGENTS.md")
    return sorted(found)


def check(root: Path, strict: bool = False) -> list[str]:
    problems = []
    for agents in find_agents_md(root):
        rel = agents.relative_to(root).as_posix()
        shim = agents.with_name("CLAUDE.md")
        if not shim.exists():
            problems.append(f"{rel}: missing sibling CLAUDE.md")
            continue
        lines = [ln.strip() for ln in shim.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if "@AGENTS.md" not in lines:
            problems.append(f"{rel}: sibling CLAUDE.md does not import @AGENTS.md")
        elif strict and lines != ["@AGENTS.md"]:
            problems.append(f"{rel}: sibling CLAUDE.md has content beyond '@AGENTS.md'")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    problems = check(args.root.resolve(), args.strict)
    print(json.dumps({"check": "agents-md-shim", "ok": not problems,
                      "agents_md_found": len(find_agents_md(args.root.resolve())),
                      "problems": problems}, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
