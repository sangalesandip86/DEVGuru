"""Stage Transition Engine persistence layer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .domain import (
    TRANSITION_GRAPH, SIDE_STATE_RULES, STAGE_SET,
    TransitionRequest, TransitionResult, StageState,
)

_MIGRATION_DIR = Path(__file__).parent / "migrations"


class StageEngineStore:
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

    def validate_transition(self, req: TransitionRequest) -> TransitionResult:
        if req.from_stage not in TRANSITION_GRAPH:
            if req.from_stage in STAGE_SET:
                return TransitionResult(
                    allowed=False, from_stage=req.from_stage, to_stage=req.to_stage,
                    reason=f"cannot transition from side state {req.from_stage}")
            return TransitionResult(
                allowed=False, from_stage=req.from_stage, to_stage=req.to_stage,
                reason=f"unknown stage: {req.from_stage}")

        if req.to_stage not in STAGE_SET:
            return TransitionResult(
                allowed=False, from_stage=req.from_stage, to_stage=req.to_stage,
                reason=f"unknown target stage: {req.to_stage}")

        graph_entry = TRANSITION_GRAPH[req.from_stage]

        if req.to_stage in ("BLOCKED", "FAILED", "CANCELLED"):
            return TransitionResult(
                allowed=True, from_stage=req.from_stage, to_stage=req.to_stage,
                reason=f"side-state transition to {req.to_stage}")

        if req.to_stage not in graph_entry["allowed_next"]:
            return TransitionResult(
                allowed=False, from_stage=req.from_stage, to_stage=req.to_stage,
                reason=f"transition {req.from_stage} -> {req.to_stage} not allowed; "
                       f"allowed: {graph_entry['allowed_next']}")

        missing_outputs = [o for o in graph_entry["required_outputs"] if o not in req.outputs]

        role_check = graph_entry["required_roles"]
        missing_roles = [] if req.actor_role in role_check else [
            r for r in role_check if r != req.actor_role]

        if missing_outputs or missing_roles:
            return TransitionResult(
                allowed=False, from_stage=req.from_stage, to_stage=req.to_stage,
                reason="missing requirements",
                missing_outputs=missing_outputs,
                missing_roles=missing_roles,
                gate=graph_entry.get("gate"))

        return TransitionResult(
            allowed=True, from_stage=req.from_stage, to_stage=req.to_stage,
            gate=graph_entry.get("gate"))

    def record_transition(self, entry_id: str, req: TransitionRequest,
                          result: TransitionResult, actor_type: str, actor_id: str,
                          timestamp: str) -> dict[str, Any]:
        self._conn.execute(
            "INSERT INTO stage_transitions "
            "(id, change_set_id, from_stage, to_stage, actor_type, actor_id, actor_role, "
            "outputs, evidence_ids, gate_result, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_id, req.change_set_id, req.from_stage, req.to_stage,
             actor_type, actor_id, req.actor_role,
             json.dumps(req.outputs), json.dumps(req.evidence_ids),
             result.gate, timestamp))

        self._conn.execute(
            "INSERT INTO stage_current (change_set_id, current_stage, previous_stage, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(change_set_id) DO UPDATE SET "
            "current_stage=excluded.current_stage, previous_stage=excluded.previous_stage, "
            "updated_at=excluded.updated_at",
            (req.change_set_id, req.to_stage, req.from_stage, timestamp))

        self._conn.commit()
        return {"id": entry_id, "change_set_id": req.change_set_id,
                "from_stage": req.from_stage, "to_stage": req.to_stage,
                "allowed": result.allowed, "gate": result.gate}


    def record_violation(self, entry_id: str, req: TransitionRequest,
                         result: TransitionResult, actor_type: str, actor_id: str,
                         timestamp: str) -> None:
        """Record a VIOLATION without updating stage_current."""
        self._conn.execute(
            "INSERT INTO stage_transitions "
            "(id, change_set_id, from_stage, to_stage, actor_type, actor_id, actor_role, "
            "outputs, evidence_ids, gate_result, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_id, req.change_set_id, req.from_stage, req.to_stage,
             actor_type, actor_id, req.actor_role,
             json.dumps(req.outputs), json.dumps(req.evidence_ids),
             "VIOLATION", timestamp))
        self._conn.commit()

    def get_current_stage(self, change_set_id: str) -> StageState:
        row = self._conn.execute(
            "SELECT current_stage, previous_stage FROM stage_current WHERE change_set_id = ?",
            (change_set_id,)).fetchone()

        if row is None:
            stage = "INTAKE"
            prev = ""
        else:
            stage, prev = row

        graph_entry = TRANSITION_GRAPH.get(stage, {})
        transitions = []
        for r in self._conn.execute(
                "SELECT id, from_stage, to_stage, actor_role, gate_result, timestamp "
                "FROM stage_transitions WHERE change_set_id = ? ORDER BY seq",
                (change_set_id,)):
            transitions.append({
                "id": r[0], "from": r[1], "to": r[2],
                "role": r[3], "gate": r[4], "at": r[5]})

        return StageState(
            change_set_id=change_set_id,
            current_stage=stage,
            previous_stage=prev,
            transitions=transitions,
            allowed_next=graph_entry.get("allowed_next", []),
            required_outputs=graph_entry.get("required_outputs", []),
            gate=graph_entry.get("gate"))

    def get_transition_graph(self) -> dict[str, Any]:
        return {
            "stages": {k: {**v} for k, v in TRANSITION_GRAPH.items()},
            "side_states": {k: {**v} for k, v in SIDE_STATE_RULES.items()},
            "stage_order": list(TRANSITION_GRAPH.keys()),
        }
