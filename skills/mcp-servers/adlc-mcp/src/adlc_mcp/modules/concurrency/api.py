"""Concurrency Primitives — public surface.

Hard task claims, soft file intents, conflict prediction, and coordination messages.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import asdict
from typing import Any, Protocol

from adlc_mcp.kernel import db
from adlc_mcp.kernel.config import Config
from adlc_mcp.kernel.errors import ValidationError
from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.util import now_iso

from .domain import CoordMessage, DEFAULT_INTENT_TTL_MINUTES
from .store import ConcurrencyStore


class TaskRegistryPort(Protocol):
    def task_exists(self, task_id: str) -> bool: ...


class NullTaskRegistry:
    """Fail open when registry not connected."""
    def task_exists(self, task_id: str) -> bool:
        return True


NAME = "concurrency"


class ConcurrencyPrimitives:
    def __init__(self, conn: sqlite3.Connection, task_registry: TaskRegistryPort | None = None) -> None:
        self._store = ConcurrencyStore(conn)
        self._task_registry = task_registry or NullTaskRegistry()

    def migrate(self) -> list[str]:
        return self._store.migrate()

    def claim_task(self, identity: Identity, *, task_id: str) -> dict[str, Any]:
        if not task_id:
            raise ValidationError("task_id is required")
        if not self._task_registry.task_exists(task_id):
            raise ValidationError(f"task {task_id!r} does not exist \u2014 cannot claim a nonexistent task")
        ok, claim = self._store.claim_task(task_id, identity.actor_id)
        result: dict[str, Any] = {"task_id": task_id, "claimed": ok}
        if claim:
            result["holder"] = asdict(claim)
        return result

    def release_task(self, identity: Identity, *, task_id: str) -> dict[str, Any]:
        if not task_id:
            raise ValidationError("task_id is required")
        released = self._store.release_task(task_id, identity.actor_id)
        return {"task_id": task_id, "released": released}

    def declare_file_intent(self, identity: Identity, *, files: list[str],
                            ttl_minutes: int = DEFAULT_INTENT_TTL_MINUTES,
                            change_set_id: str = "") -> dict[str, Any]:
        if not files:
            raise ValidationError("files list is required")
        intent_id = uuid.uuid4().hex
        intent = self._store.declare_file_intent(
            intent_id, identity.actor_id, identity.agent_role or "",
            files, ttl_minutes, change_set_id)
        return asdict(intent)

    def check_conflicts(self, identity: Identity, *,
                        planned_files: list[str]) -> dict[str, Any]:
        if not planned_files:
            raise ValidationError("planned_files is required")
        conflicts = self._store.check_conflicts(identity.actor_id, planned_files)
        return {"planned_files": planned_files,
                "conflicts": [asdict(c) for c in conflicts],
                "has_conflicts": len(conflicts) > 0}

    def send_coordination_message(self, identity: Identity, *, to_actor: str,
                                  content: str, change_set_id: str = "",
                                  intent_id: str = "") -> dict[str, Any]:
        if not to_actor or not content:
            raise ValidationError("to_actor and content are required")
        msg = CoordMessage(
            message_id=uuid.uuid4().hex,
            from_actor=identity.actor_id,
            from_role=identity.agent_role or "",
            to_actor=to_actor, content=content,
            sent_at=now_iso(),
            change_set_id=change_set_id, intent_id=intent_id)
        self._store.send_message(msg)
        return asdict(msg)


class ConcurrencyModule:
    name = NAME

    def __init__(self, config: Config, task_registry: TaskRegistryPort | None = None) -> None:
        self._conn = db.connect(config.db_path(NAME))
        self._api = ConcurrencyPrimitives(self._conn, task_registry)

    def migrate(self, conn: sqlite3.Connection | None = None) -> None:
        self._api.migrate()

    def register_tools(self, server: Any, identity: Identity) -> list[str]:
        from .tools import register_tools
        return register_tools(server, self._api, identity)

    @property
    def api(self) -> ConcurrencyPrimitives:
        return self._api

    def close(self) -> None:
        self._conn.close()


def create_module(config: Config, task_registry: TaskRegistryPort | None = None) -> ConcurrencyModule:
    module = ConcurrencyModule(config, task_registry)
    module.migrate()
    return module
