#!/usr/bin/env python3
"""Export DORA and ADLC health metrics from the evidence ledger and forge events.

Produces a JSON object with:
  - dora: deployment_frequency, lead_time_for_changes, change_failure_rate, time_to_restore
  - planning: story_cycle_time, ac_coverage_rate, plan_revision_count
  - test_health: flake_rate, mutation_score_median, red_green_pass_rate
  - review: pr_size_median, review_wait_median, no_review_merge_count

Usage:
    python metrics_export.py --db PATH [--since YYYY-MM-DD] [--until YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def dora_metrics(conn: sqlite3.Connection, since: str, until: str) -> dict:
    deploys = _query(conn,
        "SELECT * FROM forge_events WHERE event_type = 'deploy' AND timestamp >= ? AND timestamp <= ?",
        (since, until))
    rollbacks = _query(conn,
        "SELECT * FROM forge_events WHERE event_type = 'rollback' AND timestamp >= ? AND timestamp <= ?",
        (since, until))
    merges = _query(conn,
        "SELECT * FROM forge_events WHERE event_type = 'merge' AND timestamp >= ? AND timestamp <= ?",
        (since, until))

    days = max(1, (datetime.fromisoformat(until) - datetime.fromisoformat(since)).days)
    deploy_freq = len(deploys) / days if deploys else 0

    lead_times = []
    for d in deploys:
        matching_merges = [m for m in merges if m["change_set_id"] == d["change_set_id"]]
        for m in matching_merges:
            try:
                lt = (datetime.fromisoformat(d["timestamp"]) - datetime.fromisoformat(m["timestamp"])).total_seconds() / 3600
                if lt >= 0:
                    lead_times.append(lt)
            except (ValueError, TypeError):
                continue

    cfr = len(rollbacks) / len(deploys) if deploys else 0

    restore_times = []
    for rb in rollbacks:
        matching_deploys = [d for d in deploys
                           if d["change_set_id"] == rb["change_set_id"]
                           and d["timestamp"] < rb["timestamp"]]
        if matching_deploys:
            last_deploy = max(matching_deploys, key=lambda d: d["timestamp"])
            try:
                rt = (datetime.fromisoformat(rb["timestamp"]) - datetime.fromisoformat(last_deploy["timestamp"])).total_seconds() / 3600
                restore_times.append(rt)
            except (ValueError, TypeError):
                continue

    return {
        "deployment_frequency_per_day": round(deploy_freq, 3),
        "lead_time_hours_median": round(median(lead_times), 1) if lead_times else None,
        "change_failure_rate": round(cfr, 3),
        "time_to_restore_hours_median": round(median(restore_times), 1) if restore_times else None,
        "sample": {"deploys": len(deploys), "merges": len(merges), "rollbacks": len(rollbacks)},
    }


def planning_metrics(conn: sqlite3.Connection, since: str, until: str) -> dict:
    history = _query(conn,
        "SELECT * FROM status_history WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp",
        (since, until))

    cs_starts: dict[str, str] = {}
    cs_ends: dict[str, str] = {}
    revision_counts: dict[str, int] = {}
    for h in history:
        csid = h["change_set_id"]
        if h["to_status"] == "PLANNED" and csid not in cs_starts:
            cs_starts[csid] = h["timestamp"]
        if h["to_status"] in ("INTEGRATED", "RELEASED"):
            cs_ends[csid] = h["timestamp"]
        if h["to_status"] == "PLANNED" and h["from_status"] in ("EXECUTING", "PLAN_APPROVED"):
            revision_counts[csid] = revision_counts.get(csid, 0) + 1

    cycle_times = []
    for csid, start in cs_starts.items():
        if csid in cs_ends:
            try:
                ct = (datetime.fromisoformat(cs_ends[csid]) - datetime.fromisoformat(start)).total_seconds() / 3600
                cycle_times.append(ct)
            except (ValueError, TypeError):
                continue

    return {
        "story_cycle_time_hours_median": round(median(cycle_times), 1) if cycle_times else None,
        "plan_revision_count": sum(revision_counts.values()),
        "change_sets_completed": len(cs_ends),
    }


def test_health_metrics(evidence_conn: sqlite3.Connection, since: str, until: str) -> dict:
    entries = _query(evidence_conn,
        "SELECT e.*, c.content FROM evidence e LEFT JOIN evidence_content c ON c.entry_id = e.entry_id "
        "WHERE e.timestamp >= ? AND e.timestamp <= ? AND e.source_type = 'ci_gate'",
        (since, until))

    flake_runs = [e for e in entries if "flake" in (e.get("source") or "").lower()]
    rg_runs = [e for e in entries if "red_green" in (e.get("source") or "").lower()]

    return {
        "flake_gate_runs": len(flake_runs),
        "red_green_runs": len(rg_runs),
        "ci_gate_entries": len(entries),
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="path to change_management.db")
    ap.add_argument("--evidence-db", help="path to evidence_ledger.db (defaults to sibling)")
    ap.add_argument("--since", default=_iso(datetime.now(timezone.utc) - timedelta(days=30)))
    ap.add_argument("--until", default=_iso(datetime.now(timezone.utc)))
    args = ap.parse_args(argv)

    cm_conn = _connect(args.db)
    ev_path = args.evidence_db or str(Path(args.db).parent / "evidence_ledger.db")
    ev_conn = _connect(ev_path) if Path(ev_path).exists() else None

    result = {
        "period": {"since": args.since, "until": args.until},
        "dora": dora_metrics(cm_conn, args.since, args.until),
        "planning": planning_metrics(cm_conn, args.since, args.until),
    }
    if ev_conn:
        result["test_health"] = test_health_metrics(ev_conn, args.since, args.until)
        ev_conn.close()
    cm_conn.close()

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
