#!/usr/bin/env python3
"""Metrics export from the ADLC Evidence Ledger.

Shows counts by classification, role activity, and lifecycle states.

Usage:
    python adlc_metrics.py --db .adlc/evidence_ledger.db
    python adlc_metrics.py --db .adlc/evidence_ledger.db --pretty
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_query(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.OperationalError:
        return []


def gather_metrics(db_path: str) -> dict:
    conn = _connect(db_path)

    total_row = _safe_query(conn, "SELECT COUNT(*) AS n FROM evidence")
    total = total_row[0]["n"] if total_row else 0

    by_class = {r["classification"]: r["n"] for r in _safe_query(
        conn, "SELECT classification, COUNT(*) AS n FROM evidence GROUP BY classification")}

    by_role = {r["agent_role"]: r["n"] for r in _safe_query(
        conn, "SELECT COALESCE(agent_role, '(none)') AS agent_role, COUNT(*) AS n "
              "FROM evidence GROUP BY agent_role ORDER BY n DESC")}

    by_lifecycle = {r["lifecycle_state"]: r["n"] for r in _safe_query(
        conn, "SELECT COALESCE(lifecycle_state, '(none)') AS lifecycle_state, COUNT(*) AS n "
              "FROM evidence GROUP BY lifecycle_state")}

    by_trust = {r["trust_level"]: r["n"] for r in _safe_query(
        conn, "SELECT trust_level, COUNT(*) AS n FROM evidence GROUP BY trust_level")}

    incident_rows = _safe_query(conn, "SELECT status, COUNT(*) AS n FROM incidents GROUP BY status")
    incidents = {r["status"]: r["n"] for r in incident_rows}

    conn.close()
    return {
        "total_evidence": total,
        "by_classification": by_class,
        "by_role": by_role,
        "by_lifecycle_state": by_lifecycle,
        "by_trust_level": by_trust,
        "incidents_by_status": incidents,
    }


def _render_pretty(data: dict) -> str:
    lines = ["=== ADLC Metrics ===", f"Total evidence entries: {data['total_evidence']}", ""]
    for section, key in [("By Classification", "by_classification"),
                         ("By Role", "by_role"),
                         ("By Lifecycle State", "by_lifecycle_state"),
                         ("By Trust Level", "by_trust_level"),
                         ("Incidents by Status", "incidents_by_status")]:
        lines.append(f"{section}:")
        items = data.get(key, {})
        if not items:
            lines.append("  (none)")
        for k, v in items.items():
            lines.append(f"  {k:30s} {v:>6d}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ADLC Evidence Ledger metrics export")
    parser.add_argument("--db", default=os.path.join(".adlc", "evidence_ledger.db"),
                        help="Path to evidence_ledger.db")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    args = parser.parse_args()

    data = gather_metrics(args.db)
    if args.pretty:
        print(_render_pretty(data))
    else:
        json.dump(data, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
