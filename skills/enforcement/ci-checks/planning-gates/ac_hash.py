"""Canonical acceptance-criteria hash (plan v3.1 §4.12 — AC freeze).

One function, shared by plan-lint, the readiness gate, the completion gate and (later) the
``work_planning`` module of the adlc MCP server. Every producer of a JUDGMENT review that is
pinned to the AC (qa-derive testability, developer feasibility) records this value; a review
recorded against a different hash no longer counts.

What is hashed: each criterion's semantic fields only (id, given, when, then, kind,
verification, tags), with whitespace collapsed, sorted by id. Reordering criteria or
re-wrapping text does not change the hash; changing what a criterion says does.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

HASHED_FIELDS = ("id", "given", "when", "then", "kind", "verification", "tags")
_WS = re.compile(r"\s+")


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return _WS.sub(" ", value).strip()
    if isinstance(value, list):
        return sorted(_norm(v) for v in value) if all(isinstance(v, str) for v in value) \
            else [_norm(v) for v in value]
    return value


def canonical_ac(criteria: list[dict]) -> list[dict]:
    out = []
    for ac in criteria or []:
        item = {k: _norm(ac.get(k)) for k in HASHED_FIELDS if ac.get(k) not in (None, [], "")}
        out.append(item)
    return sorted(out, key=lambda a: str(a.get("id", "")))


def ac_hash(story: dict) -> str:
    """Return ``sha256:<hex>`` over the story's canonical acceptance criteria."""
    payload = json.dumps(canonical_ac(story.get("acceptance_criteria", [])),
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


if __name__ == "__main__":  # pragma: no cover - convenience CLI
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import minyaml

    ap = argparse.ArgumentParser(description="Print the canonical AC hash of a story file.")
    ap.add_argument("story_file")
    args = ap.parse_args()
    print(ac_hash(minyaml.load(args.story_file)))
