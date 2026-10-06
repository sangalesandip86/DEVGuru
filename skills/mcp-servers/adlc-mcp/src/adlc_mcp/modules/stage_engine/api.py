"""Stage Transition Engine — public surface.

Validates and records stage transitions. The engine is advisory + audit:
it validates transitions but does not execute them. Invalid transitions are
logged as VIOLATION events.
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

from .domain import STAGE_SET, TransitionRequest
from .store import StageEngineStore

NAME = "stage_engine"


class StageEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._store = StageEngineStore(conn)

    def migrate(self) -> list[str]:
        return self._store.migrate()

    def get_transition_graph(self) -> dict[str, Any]:
        return self._store.get_transition_graph()

    def validate_transition(self, *, change_set_id: str, from_stage: str,
                            to_stage: str, actor_role: str,
                            outputs: list[str] | None = None) -> dict[str, Any]:
        if not change_set_id:
            raise ValidationError("change_set_id is required")
        if from_stage not in STAGE_SET:
            raise ValidationError(f"unknown from_stage: {from_stage}")
        if to_stage not in STAGE_SET:
            raise ValidationError(f"unknown to_stage: {to_stage}")

        req = TransitionRequest(
            change_set_id=change_set_id, from_stage=from_stage,
            to_stage=to_stage, actor_role=actor_role,
            outputs=list(outputs or []))
        result = self._store.validate_transition(req)
        return asdict(result)

    def record_transition(self, identity: Identity, *, change_set_id: str,
                          from_stage: str, to_stage: str,
                          outputs: list[str] | None = None,
                          evidence_ids: list[str] | None = None) -> dict[str, Any]:
        if not change_set_id:
            raise ValidationError("change_set_id is required")

        req = TransitionRequest(
            change_set_id=change_set_id, from_stage=from_stage,
            to_stage=to_stage, actor_role=identity.agent_role or "unknown",
            outputs=list(outputs or []),
            evidence_ids=list(evidence_ids or []))

        result = self._store.validate_transition(req)

        entry_id = uuid.uuid4().hex
        ts = now_iso()

        if not result.allowed:
            self._store.record_transition(
                entry_id, req, result,
                identity.actor_type, identity.actor_id, ts)
            return {"id": entry_id, "allowed": False, "reason": result.reason,
                    "missing_outputs": result.missing_outputs,
                    "missing_roles": result.missing_roles,
                    "recorded_as": "VIOLATION"}

        self._store.record_transition(
            entry_id, req, result,
            identity.actor_type, identity.actor_id, ts)
        return {"id": entry_id, "allowed": True,
                "from_stage": from_stage, "to_stage": to_stage,
                "gate": result.gate}

    def get_current_stage(self, *, change_set_id: str) -> dict[str, Any]:
        if not change_set_id:
            raise ValidationError("change_set_id is required")
        return asdict(self._store.get_current_stage(change_set_id))


class StageEngineModule:
    name = NAME

    def __init__(self, config: Config) -> None:
        self._conn = db.connect(config.db_path(NAME))
        self._api = StageEngine(self._conn)

    def migrate(self, conn: sqlite3.Connection | None = None) -> None:
        self._api.migrate()

    def register_tools(self, server: Any, identity: Identity) -> list[str]:
        from .tools import register_tools
        return register_tools(server, self._api, identity)

    @property
    def api(self) -> StageEngine:
        return self._api

    def close(self) -> None:
        self._conn.close()


def create_module(config: Config) -> StageEngineModule:
    module = StageEngineModule(config)
    module.migrate()
    return module
