#!/usr/bin/env python3
"""plan-lint — validates a plans/ tree (plan v3.1 §4.12). Runs on every PR touching plans/.

Checks
  * every file parses (YAML subset) and validates against its schema (no status fields)
  * file name matches the artifact id; ids are unique per kind
  * referential integrity: requirement/epic/milestone/story/feature/follow-up references exist
  * AC standard: ids `ST-n/AC-n` prefixed by their own story, unique, Given/When/Then present
  * ACCEPTED_RISK dependencies name a human owner
  * warnings: nfr AC without a number; milestone that looks like a technical layer;
    story <-> milestone membership declared on one side only
  * AC freeze: given a readiness record (`--readiness`, or the `readiness` key of a SYSTEM
    evidence export) listing stories that reached READY or later with the AC hash recorded at
    READY, any story whose current AC hash differs is reported as REQUIRES_REFINING. The
    tracker-projection job then moves it back to REFINING and the old qa-derive REVIEWED stops
    counting (the readiness gate pins JUDGMENT reviews to the current hash).

Exit codes: 0 clean (warnings allowed), 1 errors, 2 usage error,
            4 AC-freeze violations when --fail-on-freeze is given.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import planning_lib as pl  # noqa: E402
from ac_hash import ac_hash, canonical_ac  # noqa: E402

LAYER_WORDS = re.compile(
    r"^\s*(the\s+)?(backend|front[- ]?end|ui|api|database|db|data layer|persistence|infrastructure|infra|"
    r"services?|schema|middleware)(\s+(layer|work|foundation|tier|build|implementation))?\s*$",
    re.IGNORECASE)


def lint(plan_dir: Path, readiness: dict | None = None) -> dict:
    plans, load_errors = pl.load_plans(plan_dir)
    errors: list[dict] = [{"file": e["file"], "error": e["error"]} for e in load_errors]
    warnings: list[dict] = []

    def err(doc: dict, msg: str) -> None:
        errors.append({"file": doc.get("_file"), "id": doc.get("id"), "error": msg})

    def warn(doc: dict, msg: str) -> None:
        warnings.append({"file": doc.get("_file"), "id": doc.get("id"), "warning": msg})

    for kind, docs in plans.items():
        schema = pl.load_schema(kind)
        for doc_id, doc in docs.items():
            for e in pl.validate(pl.public(doc), schema):
                err(doc, e)
            stem = Path(doc["_file"]).stem
            if doc_id and stem != doc_id:
                err(doc, f"file name '{stem}' must match id '{doc_id}'")

    reqs, epics, stories, mss = (plans["requirement"], plans["epic"], plans["story"], plans["milestone"])
    features = {f.get("id"): eid for eid, e in epics.items() for f in (e.get("features") or [])}

    for e in epics.values():
        if e.get("requirement_id") and e["requirement_id"] not in reqs:
            err(e, f"requirement {e['requirement_id']} not found")
        for m in e.get("milestone_ids") or []:
            if m not in mss:
                err(e, f"milestone {m} not found")

    for s in stories.values():
        if s.get("requirement_id") and s["requirement_id"] not in reqs:
            err(s, f"requirement {s['requirement_id']} not found")
        if s.get("epic_id") and s["epic_id"] not in epics:
            err(s, f"epic {s['epic_id']} not found")
        if s.get("feature_id"):
            if s["feature_id"] not in features:
                err(s, f"feature {s['feature_id']} not found in any epic")
            elif features[s["feature_id"]] != s.get("epic_id"):
                err(s, f"feature {s['feature_id']} belongs to {features[s['feature_id']]}, not {s.get('epic_id')}")
        if s.get("follow_up_of") and s["follow_up_of"] not in stories:
            err(s, f"follow_up_of {s['follow_up_of']} not found")
        for m in s.get("milestone_ids") or []:
            if m not in mss:
                err(s, f"milestone {m} not found")
            elif s["id"] not in (mss[m].get("story_ids") or []) and \
                    s.get("epic_id") not in (mss[m].get("epic_ids") or []):
                warn(s, f"lists milestone {m}, but {m} lists neither the story nor its epic")
        if s.get("type") != "SPIKE" or s.get("acceptance_criteria"):  # a SPIKE may have no AC
            for e in pl.ac_standard_errors(s):
                err(s, f"AC standard: {e}")
        for a in s.get("acceptance_criteria") or []:
            if a.get("kind") == "nfr" and not re.search(r"\d", str(a.get("then", ""))):
                warn(s, f"{a.get('id')}: nfr AC has no measurable number")
        for d in s.get("dependencies") or []:
            ref = d.get("ref", "")
            if re.match(r"^ST-\d+$", ref) and ref not in stories:
                err(s, f"dependency {ref} not found")
            if re.match(r"^EPIC-\d+$", ref) and ref not in epics:
                err(s, f"dependency {ref} not found")
            if d.get("status") == "ACCEPTED_RISK" and not str(d.get("owner", "")).startswith("human:"):
                err(s, f"dependency {ref}: ACCEPTED_RISK needs owner human:<role>")

    for m in mss.values():
        for sid in m.get("story_ids") or []:
            if sid not in stories:
                err(m, f"story {sid} not found")
        for eid in m.get("epic_ids") or []:
            if eid not in epics:
                err(m, f"epic {eid} not found")
        if LAYER_WORDS.match(str(m.get("name", ""))):
            warn(m, "milestone name looks like a technical layer; milestones are outcome checkpoints (§4.12)")
        for ex in m.get("exit_criteria") or []:
            if not str(ex.get("id", "")).startswith(f"{m.get('id')}/"):
                err(m, f"exit criterion {ex.get('id')} must be prefixed {m.get('id')}/")
            if ex.get("check") == "JUDGMENT" and not ex.get("role"):
                err(m, f"exit criterion {ex.get('id')}: JUDGMENT needs a role")
            if ex.get("check") == "APPROVAL" and not ex.get("approver"):
                err(m, f"exit criterion {ex.get('id')}: APPROVAL needs a human: approver")

    freeze = []
    for sid, rec in (readiness or {}).items():
        if rec.get("status") not in pl.POST_READY:
            continue
        s = stories.get(sid)
        if s is None:
            freeze.append({"story": sid, "action": "REQUIRES_REFINING",
                           "reason": "story file removed after READY"})
            continue
        current = ac_hash(s)
        if current != rec.get("ac_hash"):
            freeze.append({"story": sid, "status_at_record": rec.get("status"),
                           "recorded_ac_hash": rec.get("ac_hash"), "current_ac_hash": current,
                           "action": "REQUIRES_REFINING",
                           "reason": "acceptance criteria changed after READY; qa-derive test design "
                                     "REVIEWED is invalidated and the DoR re-runs"})

    return {
        "counts": {k: len(v) for k, v in plans.items()},
        "errors": errors,
        "warnings": warnings,
        "freeze_violations": freeze,
        "ac_hashes": {sid: ac_hash(s) for sid, s in stories.items()},
    }


def changed_acs(base_dir: Path, head_dir: Path) -> list[str]:
    """AC IDs added, removed, or changed in meaning between two plans/ trees.

    Feeds test_integrity_guard.py --ac-changed-file: a test expectation may change only
    when one of its AC tags is in this list (plan v3.1 §4.13 rule 6).
    """
    def by_id(plan_dir: Path) -> dict[str, dict]:
        plans, _ = pl.load_plans(plan_dir) if plan_dir.is_dir() else ({"story": {}}, [])
        return {a["id"]: a for s in plans["story"].values() for a in canonical_ac(s.get("acceptance_criteria", []))
                if "id" in a}
    base, head = by_id(base_dir), by_id(head_dir)
    return sorted(i for i in set(base) | set(head) if base.get(i) != head.get(i))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lint a plans/ tree (schemas, references, AC standard, AC freeze).")
    ap.add_argument("plans", help="plans/ directory")
    ap.add_argument("--readiness", help="JSON {story_id: {status, ac_hash}} or an evidence export with a 'readiness' key")
    ap.add_argument("--fail-on-freeze", action="store_true", help="exit 4 when an AC freeze violation exists")
    ap.add_argument("--changed-ac-against", metavar="BASE_PLANS",
                    help="print only a JSON list of AC IDs that differ from BASE_PLANS (for the test integrity guard)")
    args = ap.parse_args(argv)
    if args.changed_ac_against:
        print(json.dumps(changed_acs(Path(args.changed_ac_against), Path(args.plans))))
        return 0
    if not Path(args.plans).is_dir():
        print(json.dumps({"error": f"{args.plans} is not a directory"}), file=sys.stderr)
        return 2
    readiness = None
    if args.readiness:
        data = json.loads(Path(args.readiness).read_text(encoding="utf-8"))
        readiness = data.get("readiness", data) if isinstance(data, dict) else None
    out = lint(Path(args.plans), readiness)
    print(json.dumps(out, indent=2))
    if out["errors"]:
        return 1
    if args.fail_on_freeze and out["freeze_violations"]:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
