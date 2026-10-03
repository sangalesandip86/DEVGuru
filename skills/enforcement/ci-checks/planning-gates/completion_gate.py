#!/usr/bin/env python3
"""Completion gate — evaluates the Definition of Done for a story (plan v3.1 §4.12).

Runs as a SYSTEM CI job. DONE and ACCEPTED are derived here from evidence; no agent tool
sets them.

    python completion_gate.py --plans plans/ --story ST-101 --evidence evidence.json \
        [--coverage ac-coverage.json]

The DoD variant comes from story-types.yaml (`dod_variant`): `standard`, or `spike` for a
SPIKE (DECISION + ADR + follow-up stories, no production code merged).

Result:
    NOT_DONE  — at least one DONE-stage item is not PASS
    DONE      — all DONE-stage items PASS; ACCEPTED-stage items (PO acceptance) still open
    ACCEPTED  — all items PASS (or no ACCEPTED-stage item applies, in which case DONE is
                terminal and the result is reported as DONE)

Exit codes: 0 DONE or ACCEPTED, 1 NOT_DONE, 2 usage/input error.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import planning_lib as pl  # noqa: E402


def evaluate(plan_dir: Path, story_id: str, evidence: dict, coverage: dict | None = None,
             now: datetime | None = None, policy_dir: Path | None = None) -> dict:
    plans, load_errors = pl.load_plans(plan_dir)
    story = pl.find_story(plans, story_id)
    if story is None:
        raise LookupError(f"story {story_id} not found under {plan_dir}/stories")
    types = pl.load_policy("story-types", policy_dir)
    policy = pl.load_policy("dod-policy", policy_dir)
    variant = (types["types"].get(story.get("type"), {}) or {}).get("dod_variant", "standard")
    tier = pl.effective_tier(story, types)
    ctx = pl.Ctx(story, plans, evidence, tier["tier"], coverage=coverage, now=now, policy=policy)
    res = pl.evaluate_policy(policy, ctx, variant=variant)
    done_items = [i for i in res["items"] if i["stage"] != "ACCEPTED"]
    acc_items = [i for i in res["items"] if i["stage"] == "ACCEPTED"]
    if not all(i["status"] == pl.PASS for i in done_items):
        result = "NOT_DONE"
    elif acc_items and all(i["status"] == pl.PASS for i in acc_items):
        result = "ACCEPTED"
    else:
        result = "DONE"
    return {
        "story": story_id,
        "stage": "DONE",
        "variant": variant,
        "result": result,
        "awaiting_acceptance": bool(acc_items) and result == "DONE",
        "ac_hash": ctx.ac_hash,
        "effective_tier": tier,
        "items": res["items"],
        "not_applicable": res["not_applicable"],
        "plan_load_errors": load_errors,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--plans", required=True)
    ap.add_argument("--story", required=True)
    ap.add_argument("--evidence", help="SYSTEM-exported evidence JSON")
    ap.add_argument("--coverage", help="ac_coverage.py output (overrides evidence.ac_coverage)")
    ap.add_argument("--now")
    ap.add_argument("--policy-dir")
    args = ap.parse_args(argv)
    try:
        coverage = json.loads(Path(args.coverage).read_text(encoding="utf-8")) if args.coverage else None
        now = pl._parse_ts(args.now) if args.now else None
        out = evaluate(Path(args.plans), args.story, pl.load_evidence(args.evidence), coverage, now,
                       Path(args.policy_dir) if args.policy_dir else None)
    except (LookupError, ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0 if out["result"] in ("DONE", "ACCEPTED") else 1


if __name__ == "__main__":
    sys.exit(main())
