"""Change Management persistence. Owns ``change_management.db``; no other module touches it."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from adlc_mcp.kernel import db
from adlc_mcp.kernel.util import dumps_or_none, loads_or_none, now_iso

MODULE = "change_management"
MIGRATIONS = Path(__file__).parent / "migrations"
_JSON = ("requirements", "repositories", "contracts", "environments", "depends_on", "checkpoint", "payload",
         "story_refs", "ac_refs",
         "reason_codes", "detail")


def _decode(row: sqlite3.Row | dict | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for c in _JSON:
        if c in out and isinstance(out[c], str):
            out[c] = loads_or_none(out[c])
    return out


class ChangeStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def migrate(self) -> list[str]:
        return db.run_migrations(self.conn, MODULE, MIGRATIONS)

    # change sets ------------------------------------------------------------------------
    def insert_change_set(self, row: dict[str, Any]) -> None:
        row = {k: (dumps_or_none(v) if k in _JSON else v) for k, v in row.items()}
        cols = ", ".join(row)
        self.conn.execute(f"INSERT INTO change_sets ({cols}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))

    def get_change_set(self, cs_id: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute("SELECT * FROM change_sets WHERE id = ?", (cs_id,)).fetchone())

    def set_status(self, cs_id: str, status: str, blocked_from: str | None, block_kind: str | None) -> None:
        self.conn.execute(
            "UPDATE change_sets SET status = ?, blocked_from = ?, block_kind = ?, updated_at = ? WHERE id = ?",
            (status, blocked_from, block_kind, now_iso(), cs_id),
        )

    def set_risk_tier(self, cs_id: str, tier: str) -> None:
        self.conn.execute("UPDATE change_sets SET risk_tier = ?, updated_at = ? WHERE id = ?", (tier, now_iso(), cs_id))

    def append_history(self, row: dict[str, Any]) -> dict[str, Any]:
        return db.append_chained(self.conn, "status_history", row)

    def history(self, cs_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM status_history WHERE change_set_id = ? ORDER BY seq", (cs_id,))]

    # tasks ------------------------------------------------------------------------------
    def upsert_task(self, row: dict[str, Any]) -> None:
        row = {k: (dumps_or_none(v) if k in _JSON else v) for k, v in row.items()}
        cols = ", ".join(row)
        updates = ", ".join(f"{k} = excluded.{k}" for k in row if k not in ("change_set_id", "id"))
        self.conn.execute(
            f"INSERT INTO tasks ({cols}) VALUES ({', '.join('?' for _ in row)}) "
            f"ON CONFLICT (change_set_id, id) DO UPDATE SET {updates}",
            list(row.values()),
        )

    def get_task(self, cs_id: str, task_id: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute(
            "SELECT * FROM tasks WHERE change_set_id = ? AND id = ?", (cs_id, task_id)).fetchone())

    def tasks(self, cs_id: str) -> list[dict[str, Any]]:
        return [_decode(r) for r in self.conn.execute(
            "SELECT * FROM tasks WHERE change_set_id = ? ORDER BY id", (cs_id,))]

    def tasks_using_worktree(self, worktree: str) -> list[dict[str, Any]]:
        return [_decode(r) for r in self.conn.execute(
            "SELECT * FROM tasks WHERE worktree = ? AND status = 'IN_PROGRESS'", (worktree,))]

    # snapshots --------------------------------------------------------------------------
    def insert_snapshot(self, row: dict[str, Any]) -> None:
        row = {k: (dumps_or_none(v) if k in ("repositories", "contracts", "environments") else v) for k, v in row.items()}
        self.conn.execute(
            f"INSERT INTO snapshots ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))

    def get_snapshot(self, snap_id: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute("SELECT * FROM snapshots WHERE id = ?", (snap_id,)).fetchone())

    def latest_snapshot(self, cs_id: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute(
            "SELECT * FROM snapshots WHERE change_set_id = ? ORDER BY created_at DESC LIMIT 1", (cs_id,)).fetchone())

    # dependencies -----------------------------------------------------------------------
    def insert_dependency(self, row: dict[str, Any]) -> None:
        self.conn.execute(
            f"INSERT INTO dependencies ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))

    def dependencies(self, cs_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM dependencies WHERE change_set_id = ? ORDER BY timestamp", (cs_id,))]

    # risk / handoffs / forge events -----------------------------------------------------
    def append_risk(self, row: dict[str, Any]) -> dict[str, Any]:
        return _decode(db.append_chained(self.conn, "risk_assessments", row))

    def risk_history(self, cs_id: str) -> list[dict[str, Any]]:
        return [_decode(r) for r in self.conn.execute(
            "SELECT * FROM risk_assessments WHERE change_set_id = ? ORDER BY seq", (cs_id,))]

    def all_overrides(self) -> list[dict[str, Any]]:
        return [_decode(r) for r in self.conn.execute(
            "SELECT * FROM risk_assessments WHERE kind = 'HUMAN_OVERRIDE' ORDER BY seq")]

    def append_handoff(self, row: dict[str, Any]) -> dict[str, Any]:
        return _decode(db.append_chained(self.conn, "handoffs", row))

    def handoffs(self, cs_id: str) -> list[dict[str, Any]]:
        return [_decode(r) for r in self.conn.execute(
            "SELECT * FROM handoffs WHERE change_set_id = ? ORDER BY seq", (cs_id,))]

    def append_forge_event(self, row: dict[str, Any]) -> dict[str, Any]:
        return _decode(db.append_chained(self.conn, "forge_events", row))

    def forge_events(self, cs_id: str) -> list[dict[str, Any]]:
        return [_decode(r) for r in self.conn.execute(
            "SELECT * FROM forge_events WHERE change_set_id = ? ORDER BY seq", (cs_id,))]

    def verify(self) -> list[dict[str, Any]]:
        return [db.verify_chain(self.conn, t) for t in ("status_history", "risk_assessments", "handoffs", "forge_events")]
