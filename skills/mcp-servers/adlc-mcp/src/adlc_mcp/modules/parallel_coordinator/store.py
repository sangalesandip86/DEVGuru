"""Parallel Execution Coordinator persistence layer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .domain import WorkItem, ParallelPlan, WorkerStatus, MAX_WORKERS, WORKER_STATES

_MIGRATION_DIR = Path(__file__).parent / "migrations"


class ParallelCoordinatorStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def migrate(self) -> list[str]:
        applied: list[str] = []
        for sql_file in sorted(_MIGRATION_DIR.glob("*.sql")):
            self._conn.executescript(sql_file.read_text(encoding="utf-8"))
            applied.append(sql_file.name)
        return applied

    def create_plan(self, plan: ParallelPlan, timestamp: str) -> dict[str, Any]:
        plan.max_workers = min(plan.max_workers, MAX_WORKERS)

        self._conn.execute(
            "INSERT INTO parallel_plans (plan_id, change_set_id, max_workers, auto_start, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (plan.plan_id, plan.change_set_id, plan.max_workers,
             1 if plan.auto_start_allowed else 0, timestamp))

        for item in plan.items:
            self._conn.execute(
                "INSERT INTO work_items "
                "(item_id, plan_id, change_set_id, description, planned_files, role, state, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (item.item_id, plan.plan_id, plan.change_set_id,
                 item.description, json.dumps(item.planned_files),
                 item.role, "pending", timestamp))

        self._conn.commit()
        return {"plan_id": plan.plan_id, "items": len(plan.items),
                "max_workers": plan.max_workers,
                "auto_start_allowed": plan.auto_start_allowed}

    def start_worker(self, item_id: str, worker_id: str, worktree_path: str,
                     timestamp: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT state, plan_id FROM work_items WHERE item_id = ?",
            (item_id,)).fetchone()
        if not row:
            return {"error": f"work item {item_id} not found"}
        if row[0] != "pending":
            return {"error": f"work item {item_id} is {row[0]}, not pending"}

        running_count = self._conn.execute(
            "SELECT COUNT(*) FROM work_items WHERE plan_id = ? AND state = 'running'",
            (row[1],)).fetchone()[0]

        plan_row = self._conn.execute(
            "SELECT max_workers FROM parallel_plans WHERE plan_id = ?",
            (row[1],)).fetchone()
        max_w = plan_row[0] if plan_row else MAX_WORKERS

        if running_count >= max_w:
            return {"error": f"max workers ({max_w}) reached"}

        self._conn.execute(
            "UPDATE work_items SET state = 'running', worker_id = ?, "
            "worktree_path = ?, updated_at = ? WHERE item_id = ?",
            (worker_id, worktree_path, timestamp, item_id))
        self._conn.commit()
        return {"item_id": item_id, "worker_id": worker_id, "state": "running",
                "worktree_path": worktree_path}

    def update_worker_state(self, item_id: str, state: str, result: dict | None,
                            timestamp: str) -> dict[str, Any]:
        if state not in WORKER_STATES:
            return {"error": f"unknown state: {state}"}
        updates = ["state = ?", "updated_at = ?"]
        params: list[Any] = [state, timestamp]
        if result is not None:
            updates.append("result = ?")
            params.append(json.dumps(result))
        params.append(item_id)
        self._conn.execute(
            f"UPDATE work_items SET {', '.join(updates)} WHERE item_id = ?", params)
        self._conn.commit()
        return {"item_id": item_id, "state": state}

    def get_worker_status(self, plan_id: str) -> list[WorkerStatus]:
        rows = self._conn.execute(
            "SELECT item_id, worker_id, state, role, worktree_path "
            "FROM work_items WHERE plan_id = ? ORDER BY item_id",
            (plan_id,)).fetchall()
        return [WorkerStatus(worker_id=r[1], item_id=r[0], state=r[2],
                             role=r[3], worktree_path=r[4]) for r in rows]

    def stop_all_workers(self, plan_id: str, timestamp: str) -> dict[str, Any]:
        cursor = self._conn.execute(
            "UPDATE work_items SET state = 'stopped', updated_at = ? "
            "WHERE plan_id = ? AND state IN ('pending', 'running')",
            (timestamp, plan_id))
        self._conn.commit()
        return {"plan_id": plan_id, "stopped": cursor.rowcount}

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT plan_id, change_set_id, max_workers, auto_start, created_at "
            "FROM parallel_plans WHERE plan_id = ?", (plan_id,)).fetchone()
        if not row:
            return None
        items = self._conn.execute(
            "SELECT item_id, description, state, worker_id, worktree_path, result "
            "FROM work_items WHERE plan_id = ? ORDER BY item_id",
            (plan_id,)).fetchall()
        return {
            "plan_id": row[0], "change_set_id": row[1],
            "max_workers": row[2], "auto_start": bool(row[3]),
            "created_at": row[4],
            "items": [{"item_id": i[0], "description": i[1], "state": i[2],
                       "worker_id": i[3], "worktree_path": i[4],
                       "result": json.loads(i[5])} for i in items],
        }
