#!/usr/bin/env python3
"""Evidence Ledger CLI — the hook-facing and CI-facing write path. Not an MCP tool.

    append-fact                 read one JSON object on stdin and append a FACT as SYSTEM
    verify                     verify the hash chains and content commitments; exit 1 if broken
    purge                      delete expired evidence payloads; chains stay intact
    query                      print entries as JSON (filters: --change-set, --classification, …)
    record-gate                record a CI gate evaluation as a SYSTEM VERIFIED entry
    export-planning-evidence   export story evidence for readiness/completion gates
    record-planning-status     record a planning event (gate result, PO acceptance, …)
    ingest-ac-coverage         ingest AC coverage from JUnit XML as a SYSTEM FACT

Database: $ADLC_LEDGER_DB, else $ADLC_DATA_DIR/evidence_ledger.db (default .adlc/).
Hardening (default on): $ADLC_REQUIRE_HOOK_TOKEN (default 1) requires $ADLC_HOOK_TOKEN to resolve
to a SYSTEM credential, so an agent with shell access cannot impersonate a hook. Set to 0 to
disable (development only).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from adlc_mcp.kernel.config import Config  # noqa: E402
from adlc_mcp.kernel.errors import AdlcError  # noqa: E402
from adlc_mcp.kernel.identity import resolve_identity, system_identity  # noqa: E402
from adlc_mcp.kernel.util import now_iso  # noqa: E402
from adlc_mcp.modules.evidence_ledger.api import open_ledger  # noqa: E402

GATE_NAMES = ("readiness", "completion", "plan-lint", "ac-coverage", "test-integrity")
WORK_EVENT_TYPES = ("readiness_gate", "completion_gate", "po_acceptance", "cancelled", "split")
AC_RE = re.compile(r"\bST-\d+/AC-\d+\b")


def _require_system() -> None:
    if os.environ.get("ADLC_REQUIRE_HOOK_TOKEN", "1") != "0":
        resolve_identity(os.environ.get("ADLC_HOOK_TOKEN")).require("SYSTEM", action="ci-write")


def _open_work_planning():
    from adlc_mcp.kernel import db
    config = Config.from_env()
    from adlc_mcp.modules.work_planning.api import WorkPlanning
    conn = db.connect(config.db_path("work_planning"))
    wp = WorkPlanning(conn)
    wp.migrate()
    return wp


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="ledger database path (overrides env)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # --- append-fact (existing)
    af = sub.add_parser("append-fact", help="append a hook FACT (stdin JSON)")
    af.add_argument("--hook", default=None)

    # --- verify / purge (existing)
    sub.add_parser("verify", help="verify hash chains and content commitments")
    sub.add_parser("purge", help="delete expired evidence payloads")

    # --- query (existing)
    q = sub.add_parser("query", help="query evidence entries")
    q.add_argument("--change-set")
    q.add_argument("--classification")
    q.add_argument("--role")
    q.add_argument("--trust")
    q.add_argument("--limit", type=int, default=100)

    # --- record-gate (NEW: SYSTEM write path for CI gates → VERIFIED)
    rg = sub.add_parser("record-gate", help="record a CI gate result as SYSTEM VERIFIED")
    rg.add_argument("--gate", required=True, choices=GATE_NAMES)
    rg.add_argument("--story", required=True, help="story id, e.g. ST-1")
    rg_p = rg.add_mutually_exclusive_group(required=True)
    rg_p.add_argument("--passed", action="store_true", default=None)
    rg_p.add_argument("--failed", dest="passed", action="store_false")
    rg.add_argument("--ac-hash", help="AC hash the gate evaluated against")
    rg.add_argument("--change-set", help="change set id")
    rg.add_argument("--details", help="additional JSON details")

    # --- export-planning-evidence (NEW: evidence file for readiness/completion)
    ep = sub.add_parser("export-planning-evidence",
                        help="export story evidence for gate evaluation")
    ep.add_argument("--story", required=True, help="story id, e.g. ST-1")
    ep.add_argument("--out", help="output file (default: stdout)")

    # --- record-planning-status (NEW: planning events via work_planning)
    rp = sub.add_parser("record-planning-status",
                        help="record a planning event")
    rp.add_argument("--story", required=True, help="story id, e.g. ST-1")
    rp.add_argument("--event", required=True, choices=WORK_EVENT_TYPES)
    rp_p = rp.add_mutually_exclusive_group()
    rp_p.add_argument("--passed", action="store_true", default=None)
    rp_p.add_argument("--failed", dest="passed", action="store_false")
    rp.add_argument("--ac-hash", help="AC hash for gate events")
    rp.add_argument("--approver", help="approver role for cancellation")

    # --- ingest-ac-coverage (NEW: AC coverage from JUnit XML)
    ac = sub.add_parser("ingest-ac-coverage",
                        help="ingest AC coverage from JUnit XML")
    ac.add_argument("--story", required=True, help="story id, e.g. ST-1")
    ac.add_argument("--junit", required=True, help="JUnit XML file")
    ac.add_argument("--title-pattern", help="regex for AC ids in test names")

    args = ap.parse_args(argv)

    config = Config.from_env()
    ledger = open_ledger(args.db or config.db_path("evidence_ledger"), config.platform_release_sha,
                         config.evidence_retention_days)
    try:
        if args.cmd == "append-fact":
            if os.environ.get("ADLC_REQUIRE_HOOK_TOKEN", "1") != "0":
                resolve_identity(os.environ.get("ADLC_HOOK_TOKEN")).require("SYSTEM", action="append-fact")
            payload = json.loads(sys.stdin.read() or "{}")
            hook = args.hook or os.environ.get("ADLC_HOOK_NAME") or "unknown"
            entry = ledger.append_fact(hook, payload)
            print(json.dumps({"entry_id": entry["entry_id"], "trust_level": entry["trust_level"],
                              "row_hash": entry["row_hash"]}))

        elif args.cmd == "verify":
            results = ledger.verify()
            print(json.dumps(results, indent=2))
            return 0 if all(r["ok"] for r in results) else 1

        elif args.cmd == "purge":
            print(json.dumps(ledger.purge_expired_content()))

        elif args.cmd == "query":
            reader = system_identity("cli:query")
            rows = ledger.query_evidence(reader, change_set_id=args.change_set, classification=args.classification,
                                         actor_role=args.role, trust_level=args.trust, limit=args.limit)
            print(json.dumps(rows, indent=2))

        elif args.cmd == "record-gate":
            _require_system()
            details = json.loads(args.details) if args.details else {}
            content = json.dumps({
                "gate": args.gate, "story": args.story, "passed": args.passed,
                "ac_hash": args.ac_hash, "details": details,
            }, sort_keys=True)
            entry = ledger.record_evidence(
                system_identity("ci:gate-evaluator"),
                run_id=os.environ.get("ADLC_RUN_ID", "ci-run"),
                classification="DECISION", content=content, source_type="ci_result",
                source=f"gate:{args.gate}", lifecycle_state="VERIFIED",
                change_set_id=getattr(args, "change_set", None), tool="ci",
            )
            print(json.dumps({"entry_id": entry["entry_id"], "gate": args.gate,
                              "story": args.story, "passed": args.passed,
                              "lifecycle_state": "VERIFIED"}))

        elif args.cmd == "export-planning-evidence":
            identity = system_identity("ci:evidence-exporter")
            chain_results = ledger.verify()
            chain_ok = all(r["ok"] for r in chain_results)
            all_entries = ledger.query_evidence(identity, limit=10000)
            entry_ids = {e["entry_id"] for e in all_entries}
            reviews, approvals, questions, assumptions = [], [], [], []
            gates, decisions = [], []

            for e in all_entries:
                content = e.get("content") or ""
                if e.get("source_type") == "ci_result" and e.get("lifecycle_state") == "VERIFIED":
                    try:
                        payload = json.loads(content)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if payload.get("story") == args.story:
                        gates.append({"change_set": e.get("change_set_id") or "",
                                      "gate": payload.get("gate", ""),
                                      "result": "VERIFIED" if payload.get("passed") else "FAILED",
                                      "actor_type": e["actor_type"]})
                    continue
                if args.story not in content:
                    continue
                if e["classification"] == "DECISION":
                    decisions.append({"entry_id": e["entry_id"], "story": args.story,
                                      "content": content[:500]})
                elif e["classification"] == "QUESTION":
                    questions.append({"id": e["entry_id"], "story": args.story,
                                      "state": e.get("derived_status", "OPEN"),
                                      "blocking": (e.get("metadata") or {}).get("blocking", False)})
                elif e["classification"] == "ASSUMPTION":
                    assumptions.append({"id": e["entry_id"], "story": args.story,
                                        "impact": (e.get("metadata") or {}).get("impact", "LOW"),
                                        "expires_at": (e.get("metadata") or {}).get("expires_at", "")})
                elif e.get("lifecycle_state") in ("REVIEWED", "VERIFIED", "APPROVED"):
                    review = {"entry_id": e["entry_id"], "story": args.story,
                              "role": e.get("agent_role") or "", "actor_type": e["actor_type"],
                              "lifecycle_state": e["lifecycle_state"]}
                    if e["lifecycle_state"] == "APPROVED":
                        approvals.append(review)
                    else:
                        reviews.append(review)

            exported_ids = set()
            for lst in (reviews, approvals, questions, assumptions, decisions):
                for item in lst:
                    eid = item.get("entry_id") or item.get("id")
                    if eid:
                        exported_ids.add(eid)
            dangling = sorted(exported_ids - entry_ids)
            output = {"generated_by": "SYSTEM:ledger-export", "generated_at": now_iso(),
                      "chain_verified": chain_ok,
                      "dangling_entry_ids": dangling,
                      "reviews": reviews, "approvals": approvals, "questions": questions,
                      "assumptions": assumptions, "readiness": {}, "change_sets": [],
                      "gates": gates, "decisions": decisions}
            text = json.dumps(output, indent=2)
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
                print(json.dumps({"exported": args.out, "story": args.story,
                                  "reviews": len(reviews), "gates": len(gates)}))
            else:
                print(text)

        elif args.cmd == "record-planning-status":
            _require_system()
            wp = _open_work_planning()
            payload: dict = {}
            if args.event in ("readiness_gate", "completion_gate"):
                payload["passed"] = args.passed
                if args.ac_hash:
                    payload["ac_hash"] = args.ac_hash
            if args.event == "po_acceptance":
                payload["approver_role"] = "human:product-owner"
            if args.event == "cancelled":
                payload["approver_role"] = args.approver or "human:tech-lead"
            result = wp.ingest_work_event(system_identity("ci:planning-status"),
                                          story_id=args.story, event_type=args.event,
                                          payload=payload)
            print(json.dumps(result))

        elif args.cmd == "ingest-ac-coverage":
            _require_system()
            junit_path = Path(args.junit)
            if not junit_path.exists():
                print(json.dumps({"error": f"JUnit file not found: {args.junit}"}), file=sys.stderr)
                return 1
            root = ET.parse(junit_path).getroot()
            pattern = re.compile(args.title_pattern) if args.title_pattern else AC_RE
            covered: dict[str, list[str]] = {}
            for tc in root.iter("testcase"):
                name = tc.get("name", "")
                ids = set(pattern.findall(name))
                if args.story:
                    ids = {a for a in ids if a.startswith(args.story + "/")}
                failed = tc.find("failure") is not None or tc.find("error") is not None
                skipped = tc.find("skipped") is not None
                status = "FAILED" if failed else "SKIPPED" if skipped else "PASSED"
                for ac_id in ids:
                    covered.setdefault(ac_id, []).append(f"{name}:{status}")

            content = json.dumps({"story": args.story, "junit_file": str(junit_path),
                                  "coverage": {ac: tests for ac, tests in sorted(covered.items())},
                                  "covered_count": len(covered)}, sort_keys=True)
            entry = ledger.record_evidence(
                system_identity("ci:ac-coverage"),
                run_id=os.environ.get("ADLC_RUN_ID", "ci-run"), classification="FACT",
                content=content, source_type="ac_coverage",
                source=f"junit:{junit_path.name}", lifecycle_state="VERIFIED", tool="ci",
            )
            print(json.dumps({"entry_id": entry["entry_id"], "story": args.story,
                              "covered_acs": sorted(covered.keys()), "count": len(covered)}))

    except (AdlcError, json.JSONDecodeError, ET.ParseError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
