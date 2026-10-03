#!/usr/bin/env python3
"""Readiness gate — evaluates the Definition of Ready for a story (plan v3.1 §4.12).

Runs as a SYSTEM CI job on the merged plan + a SYSTEM-exported evidence file. It is the
only path by which a story reaches READY; agents have no tool that sets story status.

    python readiness_gate.py --plans plans/ --story ST-101 --evidence evidence.json

Output (stdout, JSON):
    {"story", "stage": "READY", "result": "READY" | "NOT_READY", "ac_hash",
     "effective_tier": {...}, "items": [{id, check, status, detail}], "not_applicable": [...]}

The gate checks that the right KIND of evidence exists from the right actor: STRUCTURAL items
run deterministic checks; JUDGMENT items need a REVIEWED/ACCEPT from the named role (or a
human); APPROVAL items need an authenticated human approval. It never makes a judgment itself.

Exit codes: 0 READY, 1 NOT_READY, 2 usage/input error.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import planning_lib as pl  # noqa: E402


def evaluate(plan_dir: Path, story_id: str, evidence: dict, now: datetime | None = None,
             policy_dir: Path | None = None) -> dict:
    plans, load_errors = pl.load_plans(plan_dir)
    story = pl.find_story(plans, story_id)
    if story is None:
        raise LookupError(f"story {story_id} not found under {plan_dir}/stories")
    types = pl.load_policy("story-types", policy_dir)
    policy = pl.load_policy("dor-policy", policy_dir)
    tier = pl.effective_tier(story, types)
    ctx = pl.Ctx(story, plans, evidence, tier["tier"], now=now, policy=policy)
    res = pl.evaluate_policy(policy, ctx)
    ok = all(i["status"] == pl.PASS for i in res["items"])
    return {
        "story": story_id,
        "stage": "READY",
        "result": "READY" if ok else "NOT_READY",
        "ac_hash": ctx.ac_hash,
        "effective_tier": tier,
        "items": res["items"],
        "not_applicable": res["not_applicable"],
        "plan_load_errors": load_errors,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--plans", required=True, help="plans/ directory")
    ap.add_argument("--story", required=True, help="story id, e.g. ST-101")
    ap.add_argument("--evidence", help="SYSTEM-exported evidence JSON (reviews, approvals, questions, assumptions)")
    ap.add_argument("--now", help="ISO timestamp for assumption expiry (default: current time)")
    ap.add_argument("--policy-dir", help="override policies directory (tests only)")
    args = ap.parse_args(argv)
    try:
        now = pl._parse_ts(args.now) if args.now else None
        out = evaluate(Path(args.plans), args.story, pl.load_evidence(args.evidence), now,
                       Path(args.policy_dir) if args.policy_dir else None)
    except (LookupError, ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0 if out["result"] == "READY" else 1


if __name__ == "__main__":
    sys.exit(main())
