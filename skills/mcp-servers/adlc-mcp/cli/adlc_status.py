#!/usr/bin/env python3
"""ADLC platform health check.

Checks if MCP server databases exist, counts entries, and shows module health.

Usage:
    python adlc_status.py
    python adlc_status.py --data-dir .adlc
    python adlc_status.py --pretty
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

MODULES = {
    "evidence_ledger": {"table": "evidence", "label": "Evidence Ledger"},
    "change_management": {"table": "change_sets", "label": "Change Management"},
    "work_planning": {"table": "work_items", "label": "Work Planning"},
    "contract_registry": {"table": "contracts", "label": "Contract Registry"},
    "event_journal": {"table": "journal_entries", "label": "Event Journal"},
    "stage_engine": {"table": "stage_transitions", "label": "Stage Engine"},
    "concurrency": {"table": "task_claims", "label": "Concurrency"},
    "parallel_coordinator": {"table": "parallel_plans", "label": "Parallel Coordinator"},
}


def _check_module(db_path: Path, table: str) -> dict:
    if not db_path.is_file():
        return {"status": "missing", "count": 0}
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        conn.close()
        return {"status": "ok", "count": row[0]}
    except sqlite3.OperationalError:
        return {"status": "no_table", "count": 0}
    except sqlite3.DatabaseError as e:
        return {"status": "error", "error": str(e), "count": 0}


def check_health(data_dir: str) -> dict:
    base = Path(data_dir)
    modules = {}
    for mod_name, info in MODULES.items():
        candidates = [base / f"{mod_name}.db"]
        if base.is_dir():
            for sub in base.iterdir():
                if sub.is_dir():
                    candidates.append(sub / f"{mod_name}.db")

        found = False
        for db_path in candidates:
            if db_path.is_file():
                result = _check_module(db_path, info["table"])
                result["path"] = str(db_path)
                modules[mod_name] = result
                found = True
                break
        if not found:
            modules[mod_name] = {"status": "missing", "count": 0}

    healthy = sum(1 for m in modules.values() if m["status"] == "ok")
    return {
        "data_dir": data_dir,
        "modules": modules,
        "healthy": healthy,
        "total": len(MODULES),
    }


def _render_pretty(data: dict) -> str:
    lines = [f"=== ADLC Status ({data['healthy']}/{data['total']} modules healthy) ===",
             f"Data dir: {data['data_dir']}", ""]
    for name, info in data["modules"].items():
        label = MODULES.get(name, {}).get("label", name)
        status_icon = {"ok": "+", "missing": "-", "no_table": "?", "error": "!"}.get(
            info["status"], "?")
        count_str = f"  ({info['count']} rows)" if info["status"] == "ok" else ""
        path_str = f"  [{info.get('path', '')}]" if info.get("path") else ""
        lines.append(f"  [{status_icon}] {label:25s} {info['status']}{count_str}{path_str}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ADLC platform health check")
    parser.add_argument("--data-dir", default=".adlc", help="ADLC data directory")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    args = parser.parse_args()

    data = check_health(args.data_dir)
    if args.pretty:
        print(_render_pretty(data))
    else:
        json.dump(data, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
