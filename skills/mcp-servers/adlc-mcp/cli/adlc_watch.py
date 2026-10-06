#!/usr/bin/env python3
"""Live terminal dashboard for the ADLC Event Journal.

Reads event_journal.db and displays active sessions, tasks, and stage transitions.

Usage:
    python adlc_watch.py --db .adlc/event_journal.db
    python adlc_watch.py --db .adlc/event_journal.db --interval 5
    python adlc_watch.py --db .adlc/event_journal.db --json
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _recent_entries(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT id, run_id, change_set_id, event_type, actor_type, actor_id, "
            "agent_role, timestamp FROM journal_entries ORDER BY seq DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in reversed(rows)]


def _active_sessions(entries: list[dict]) -> dict[str, dict]:
    sessions: dict[str, dict] = {}
    for e in entries:
        actor = e["actor_id"]
        if e["event_type"] in ("session.join", "session.heartbeat"):
            sessions[actor] = {"role": e["agent_role"], "last_seen": e["timestamp"]}
        elif e["event_type"] == "session.leave":
            sessions.pop(actor, None)
    return sessions


def _active_tasks(entries: list[dict]) -> dict[str, dict]:
    tasks: dict[str, dict] = {}
    for e in entries:
        if e["event_type"] in ("task.start", "task.claim", "task.checkpoint"):
            tasks[e["id"]] = {"owner": e["actor_id"], "event": e["event_type"],
                              "updated": e["timestamp"]}
        elif e["event_type"] in ("task.deliver", "task.abandon"):
            tasks.pop(e.get("id", ""), None)
    return tasks


def _current_stage(entries: list[dict]) -> str:
    stage = ""
    for e in entries:
        if e["event_type"] == "stage.enter":
            stage = e.get("change_set_id", "unknown")
        elif e["event_type"] == "stage.exit":
            stage = ""
    return stage


def snapshot(db_path: str) -> dict:
    conn = _connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
    except sqlite3.OperationalError:
        return {"error": f"no journal_entries table in {db_path}"}
    entries = _recent_entries(conn, 200)
    conn.close()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_entries": total,
        "active_sessions": _active_sessions(entries),
        "active_tasks": _active_tasks(entries),
        "current_stage": _current_stage(entries),
        "recent_events": entries[-10:],
    }


def _render_pretty(data: dict) -> str:
    lines = [f"=== ADLC Watch — {data.get('timestamp', '')} ===",
             f"Total journal entries: {data.get('total_entries', 0)}",
             f"Current stage: {data.get('current_stage') or '(none)'}",
             "",
             "Active sessions:"]
    for actor, info in data.get("active_sessions", {}).items():
        lines.append(f"  {actor} [{info['role']}] last seen {info['last_seen']}")
    if not data.get("active_sessions"):
        lines.append("  (none)")
    lines.append("")
    lines.append("Active tasks:")
    for tid, info in data.get("active_tasks", {}).items():
        lines.append(f"  {tid[:12]}  owner={info['owner']}  {info['event']}  {info['updated']}")
    if not data.get("active_tasks"):
        lines.append("  (none)")
    lines.append("")
    lines.append("Recent events:")
    for e in data.get("recent_events", []):
        lines.append(f"  {e['timestamp']}  {e['event_type']:24s} {e['actor_id']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ADLC Event Journal live dashboard")
    parser.add_argument("--db", default=os.path.join(".adlc", "event_journal.db"),
                        help="Path to event_journal.db")
    parser.add_argument("--interval", type=int, default=2, help="Refresh interval in seconds (0 = one-shot)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of pretty text")
    args = parser.parse_args()

    while True:
        data = snapshot(args.db)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            os.system("cls" if os.name == "nt" else "clear")
            print(_render_pretty(data))
        if args.interval <= 0:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
