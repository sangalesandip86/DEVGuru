#!/usr/bin/env python3
"""CI helper: list changed files that are control files and mark the PR CRITICAL.

Does not fail the build — human approval is enforced by CODEOWNERS + ruleset. It makes the
CRITICAL tier visible (job summary + JSON) so reviewers and the ledger see it.

Usage: python flag_control_file_changes.py CHANGED_FILES_TXT [--control-paths PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_skills_root_env = os.environ.get("ADLC_SKILLS_ROOT")
_enforcement = Path(_skills_root_env, "skills", "enforcement").resolve() if _skills_root_env else HERE.parents[1]
sys.path.insert(0, str(_enforcement / "lib"))
import adlc_enforcement as ae  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("changed_files", type=Path)
    ap.add_argument("--control-paths", type=Path, default=None)
    args = ap.parse_args()
    globs = ae.load_control_globs(args.control_paths)
    files = [ln.strip() for ln in args.changed_files.read_text(encoding="utf-8").splitlines() if ln.strip()]
    hits = [{"path": f, "glob": g} for f in files if (g := ae.match_control_path(f, globs))]
    report = {"check": "control-file-changes", "risk_tier": "CRITICAL" if hits else None,
              "requires_human_approval": bool(hits), "control_files_changed": hits}
    print(json.dumps(report, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and hits:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### ⚠ Control-file change — CRITICAL tier, human approval required\n\n")
            fh.writelines(f"- `{h['path']}` (matches `{h['glob']}`)\n" for h in hits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
