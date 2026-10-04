"""Canonical acceptance-criteria hash (plan v3.1 §4.12 — AC freeze).

Thin wrapper: the implementation lives in ``skills/core/repo-facts/achash.py`` so the MCP
server and CI gates share one algorithm. This file re-exports the public API and keeps the
convenience CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path

# repo-facts lives under skills/core; parents[4] is the repo root.
_REPO_FACTS = str(Path(__file__).resolve().parents[4] / "skills" / "core" / "repo-facts")
if _REPO_FACTS not in sys.path:
    sys.path.insert(0, _REPO_FACTS)

from achash import HASHED_FIELDS, ac_hash, canonical_ac  # noqa: E402, F401

if __name__ == "__main__":  # pragma: no cover - convenience CLI
    import argparse

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import minyaml

    ap = argparse.ArgumentParser(description="Print the canonical AC hash of a story file.")
    ap.add_argument("story_file")
    args = ap.parse_args()
    print(ac_hash(minyaml.load(args.story_file)))
