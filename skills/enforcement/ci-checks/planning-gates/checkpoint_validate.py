#!/usr/bin/env python3
"""Validate checkpoint.json files against the schema and gate-skip detection.

A run that skipped a gate cannot be resumed: completed_stages must have exit-gate
evidence for each stage (checked against the evidence export).

Usage:
    python checkpoint_validate.py --checkpoint .adlc/runs/R-abc/checkpoint.json
    python checkpoint_validate.py --checkpoint PATH --evidence evidence.json --check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import minyaml  # noqa: E402

REPO_ROOT = HERE.parents[3]
SCHEMA = REPO_ROOT / "skills" / "workflow" / "schemas" / "checkpoint.schema.json"
STAGES_PATH = REPO_ROOT / "skills" / "workflow" / "stages.yaml"
REQUIRED_FIELDS = {"run_id", "requested", "completed_stages", "stopped_at",
                   "stop_reason", "ledger_cursor", "handoff", "next_preflight", "created_at"}
VALID_STAGES = {"INTAKE", "ARCHITECTURE", "PLAN", "DESIGN", "IMPLEMENT",
                "TEST", "REVIEW", "INTEGRATE", "RELEASE", "LEARN"}
VALID_STOP_REASONS = {"END_REACHED", "GATE_FAILED", "ASK_PENDING", "BLOCKED",
                      "OBSERVED_STAGE", "USER_STOP"}


def validate_structure(cp: dict) -> list[str]:
    problems = []
    missing = REQUIRED_FIELDS - set(cp.keys())
    if missing:
        problems.append(f"missing required fields: {sorted(missing)}")
    if not isinstance(cp.get("completed_stages"), list):
        problems.append("completed_stages must be a list")
    else:
        bad = [s for s in cp["completed_stages"] if s not in VALID_STAGES]
        if bad:
            problems.append(f"invalid stages in completed_stages: {bad}")
    if cp.get("stopped_at") not in VALID_STAGES:
        problems.append(f"invalid stopped_at: {cp.get('stopped_at')}")
    if cp.get("stop_reason") not in VALID_STOP_REASONS:
        problems.append(f"invalid stop_reason: {cp.get('stop_reason')}")
    cursor = cp.get("ledger_cursor", "")
    if not isinstance(cursor, str) or (cursor and not cursor.startswith("ENTRY-")):
        problems.append("ledger_cursor must start with ENTRY-")
    return problems


def validate_gates(cp: dict, evidence: dict, stages_data: dict) -> list[str]:
    """Check that every completed stage has exit-gate evidence."""
    problems = []
    completed = cp.get("completed_stages", [])
    stages = stages_data.get("stages", {})
    gate_events = {e.get("source", ""): e for e in evidence.get("gate_results", [])}
    reviews = evidence.get("reviews", [])

    for stage_name in completed:
        stage = stages.get(stage_name, {})
        exit_gates = stage.get("exit_gate", [])
        for gate in exit_gates:
            kind = gate.get("kind")
            ref = gate.get("ref", "")
            if kind == "script":
                script_name = Path(ref).stem if ref else ""
                has_result = any(script_name in src for src in gate_events)
                if not has_result:
                    problems.append(f"{stage_name}: no gate result for script {ref}")
            elif kind == "judgment":
                role = gate.get("role", "")
                has_review = any(
                    r.get("item") == ref and r.get("role") == role
                    for r in reviews
                )
                if not has_review:
                    problems.append(f"{stage_name}: no {role} review for {ref}")
            elif kind == "approval":
                when = gate.get("when", "always")
                if when != "always":
                    continue
                has_approval = any(
                    a.get("item") == ref and a.get("lifecycle_state") == "APPROVED"
                    for a in evidence.get("approvals", [])
                )
                if not has_approval:
                    problems.append(f"{stage_name}: no approval for {ref}")
    return problems


def validate(checkpoint_path: Path, evidence_path: Path | None = None) -> dict:
    result = {"ok": True, "checkpoint": str(checkpoint_path), "findings": []}

    try:
        cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "checkpoint": str(checkpoint_path),
                "findings": [{"severity": "ERROR", "message": str(exc)}]}

    structural = validate_structure(cp)
    for p in structural:
        result["ok"] = False
        result["findings"].append({"severity": "ERROR", "type": "schema", "message": p})

    if evidence_path and evidence_path.exists():
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        stages_data = minyaml.load(STAGES_PATH) if STAGES_PATH.exists() else {}
        gate_problems = validate_gates(cp, evidence, stages_data)
        for p in gate_problems:
            result["ok"] = False
            result["findings"].append({"severity": "HIGH", "type": "gate_skip", "message": p})

    return result


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", required=True, help="path to checkpoint.json")
    ap.add_argument("--evidence", help="SYSTEM evidence export for gate-skip detection")
    ap.add_argument("--check", action="store_true", help="exit 1 if validation fails")
    args = ap.parse_args(argv)

    ev_path = Path(args.evidence) if args.evidence else None
    result = validate(Path(args.checkpoint), ev_path)
    print(json.dumps(result, indent=2))
    if args.check:
        return 0 if result["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
