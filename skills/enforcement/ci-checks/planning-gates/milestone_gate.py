#!/usr/bin/env python3
"""Evaluate milestone exit criteria against story/change-set status.

STRUCTURAL criteria are evaluated automatically from gate results:
  - "ST-n ... DONE" → query the story's completion gate
  - "no OPEN blocking QUESTION" → query evidence for blocking items
  - deployment/rollback patterns → check forge events

JUDGMENT/APPROVAL criteria require human evidence.

Usage:
    python milestone_gate.py --milestone MS-1.yaml --evidence evidence.json [--plans DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planning_lib as pl  # noqa: E402

STORY_DONE_RE = re.compile(r"\b(ST-\d+)\b.*?\b(DONE|READY|INTEGRATED|RELEASED)\b", re.IGNORECASE)
NO_OPEN_RE = re.compile(r"\bno\b.*?\bOPEN\b.*?\b(QUESTION|blocking)\b", re.IGNORECASE)
DEPLOY_RE = re.compile(r"\b(deploy|rollout|release)\b.*?\bVERIFIED\b", re.IGNORECASE)


def evaluate_criterion(criterion: dict, evidence: dict, plans_dir: Path | None) -> dict:
    cid = criterion["id"]
    check = criterion.get("check", "STRUCTURAL")
    desc = criterion.get("description", "")
    result = {"id": cid, "check": check, "description": desc}

    if check in ("JUDGMENT", "APPROVAL"):
        approver = criterion.get("approver")
        approvals = evidence.get("approvals", [])
        found = any(
            a.get("item") == cid and a.get("lifecycle_state") == "APPROVED"
            for a in approvals
        )
        result["status"] = "MET" if found else "PENDING"
        if not found:
            result["detail"] = f"awaiting {check.lower()} from {approver or 'human'}"
        return result

    story_refs = STORY_DONE_RE.findall(desc)
    if story_refs:
        missing = []
        for story_id, expected_status in story_refs:
            cs = next((c for c in evidence.get("change_sets", [])
                       if story_id in (c.get("story_refs") or [])), None)
            if cs is None:
                missing.append(f"{story_id}: no change set found")
            elif cs.get("status") not in ("DONE", "INTEGRATED", "RELEASED"):
                missing.append(f"{story_id}: status is {cs.get('status', 'UNKNOWN')}")
        result["status"] = "MET" if not missing else "NOT_MET"
        if missing:
            result["detail"] = "; ".join(missing)
        return result

    if NO_OPEN_RE.search(desc):
        blocking = evidence.get("blocking_items", [])
        result["status"] = "MET" if not blocking else "NOT_MET"
        if blocking:
            result["detail"] = f"{len(blocking)} open blocking item(s)"
        return result

    if DEPLOY_RE.search(desc):
        deploys = [e for e in evidence.get("forge_events", [])
                   if e.get("event_type") == "deploy"]
        rollbacks = [e for e in evidence.get("forge_events", [])
                     if e.get("event_type") == "rollback"]
        if deploys and not rollbacks:
            result["status"] = "MET"
        elif not deploys:
            result["status"] = "NOT_MET"
            result["detail"] = "no deployment observed"
        else:
            result["status"] = "NOT_MET"
            result["detail"] = f"{len(rollbacks)} rollback(s) after deployment"
        return result

    result["status"] = "INFORMATIONAL"
    result["detail"] = "STRUCTURAL criterion not auto-evaluable; check manually"
    return result


def evaluate_milestone(milestone: dict, evidence: dict, plans_dir: Path | None = None) -> dict:
    criteria = milestone.get("exit_criteria", [])
    results = [evaluate_criterion(c, evidence, plans_dir) for c in criteria]
    met = sum(1 for r in results if r["status"] == "MET")
    return {
        "milestone_id": milestone.get("id", "unknown"),
        "criteria_count": len(results),
        "met": met,
        "not_met": sum(1 for r in results if r["status"] == "NOT_MET"),
        "pending": sum(1 for r in results if r["status"] == "PENDING"),
        "informational": sum(1 for r in results if r["status"] == "INFORMATIONAL"),
        "overall": "COMPLETE" if met == len(results) else "INCOMPLETE",
        "criteria": results,
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--milestone", required=True, help="milestone YAML file")
    ap.add_argument("--evidence", required=True, help="SYSTEM evidence export JSON")
    ap.add_argument("--plans", help="plans/ directory")
    args = ap.parse_args(argv)

    import minyaml
    milestone = minyaml.load(args.milestone)
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    plans_dir = Path(args.plans) if args.plans else None

    result = evaluate_milestone(milestone, evidence, plans_dir)
    print(json.dumps(result, indent=2))
    return 0 if result["overall"] == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
