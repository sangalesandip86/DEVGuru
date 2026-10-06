"""Parallel Execution Coordinator — public surface.

Manages parallel work items: decomposition, worker launch, status tracking,
result integration, and emergency stop.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import asdict
from typing import Any

from adlc_mcp.kernel import db
from adlc_mcp.kernel.config import Config
from adlc_mcp.kernel.errors import ValidationError
from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.util import now_iso

from .domain import WorkItem, ParallelPlan, MAX_WORKERS
from .store import ParallelCoordinatorStore

NAME = "parallel_coordinator"


class ParallelCoordinator:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._store = ParallelCoordinatorStore(conn)

    def migrate(self) -> list[str]:
        return self._store.migrate()

    def create_parallel_plan(self, identity: Identity, *, change_set_id: str,
                             items: list[dict[str, Any]],
                             max_workers: int = MAX_WORKERS) -> dict[str, Any]:
        if not change_set_id:
            raise ValidationError("change_set_id is required")
        if not items:
            raise ValidationError("at least one work item is required")
        if max_workers < 1 or max_workers > MAX_WORKERS:
            raise ValidationError(f"max_workers must be 1-{MAX_WORKERS}")

        plan_id = uuid.uuid4().hex
        work_items = [
            WorkItem(
                item_id=uuid.uuid4().hex,
                change_set_id=change_set_id,
                description=item.get("description", ""),
                planned_files=item.get("planned_files", []),
                role=item.get("role", "developer"),
            ) for item in items
        ]

        plan = ParallelPlan(
            plan_id=plan_id, change_set_id=change_set_id,
            items=work_items, max_workers=min(max_workers, MAX_WORKERS))

        return self._store.create_plan(plan, now_iso())

    def start_worker(self, identity: Identity, *, item_id: str,
                     worktree_path: str = "") -> dict[str, Any]:
        if not item_id:
            raise ValidationError("item_id is required")
        worker_id = uuid.uuid4().hex
        return self._store.start_worker(item_id, worker_id, worktree_path, now_iso())

    def get_worker_status(self, *, plan_id: str) -> dict[str, Any]:
        if not plan_id:
            raise ValidationError("plan_id is required")
        workers = self._store.get_worker_status(plan_id)
        return {"plan_id": plan_id,
                "workers": [asdict(w) for w in workers],
                "running": sum(1 for w in workers if w.state == "running"),
                "completed": sum(1 for w in workers if w.state == "completed"),
                "total": len(workers)}

    def integrate_results(self, identity: Identity, *, plan_id: str) -> dict[str, Any]:
        if not plan_id:
            raise ValidationError("plan_id is required")
        plan = self._store.get_plan(plan_id)
        if not plan:
            raise ValidationError(f"plan {plan_id} not found")

        incomplete = [i for i in plan["items"] if i["state"] not in ("completed", "stopped")]
        if incomplete:
            return {"plan_id": plan_id, "ready": False,
                    "incomplete": [i["item_id"] for i in incomplete]}

        completed = [i for i in plan["items"] if i["state"] == "completed"]
        return {"plan_id": plan_id, "ready": True,
                "completed_items": len(completed),
                "results": [{"item_id": i["item_id"], "result": i["result"]}
                            for i in completed]}

    def stop_all_workers(self, identity: Identity, *, plan_id: str) -> dict[str, Any]:
        if not plan_id:
            raise ValidationError("plan_id is required")
        return self._store.stop_all_workers(plan_id, now_iso())


class ParallelCoordinatorModule:
    name = NAME

    def __init__(self, config: Config) -> None:
        self._conn = db.connect(config.db_path(NAME))
        self._api = ParallelCoordinator(self._conn)

    def migrate(self, conn: sqlite3.Connection | None = None) -> None:
        self._api.migrate()

    def register_tools(self, server: Any, identity: Identity) -> list[str]:
        from .tools import register_tools
        return register_tools(server, self._api, identity)

    @property
    def api(self) -> ParallelCoordinator:
        return self._api

    def close(self) -> None:
        self._conn.close()


def create_module(config: Config) -> ParallelCoordinatorModule:
    module = ParallelCoordinatorModule(config)
    module.migrate()
    return module
