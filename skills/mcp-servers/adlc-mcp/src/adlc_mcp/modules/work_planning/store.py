"""Work Planning persistence. Owns ``work_planning.db``; no other module touches it."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from adlc_mcp.kernel import db
from adlc_mcp.kernel.util import canonical_json, loads_or_none, now_iso

MODULE = "work_planning"
MIGRATIONS = Path(__file__).parent / "migrations"


def _decode(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for c in ("data", "payload"):
        if c in out and isinstance(out[c], str):
            out[c] = loads_or_none(out[c])
    return out


class PlanningStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def migrate(self) -> list[str]:
        return db.run_migrations(self.conn, MODULE, MIGRATIONS)

    def append_commit(self, row: dict[str, Any]) -> dict[str, Any]:
        return db.append_chained(self.conn, "plan_commits", row)

    def last_commit(self) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT * FROM plan_commits ORDER BY seq DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    def upsert_item(self, row: dict[str, Any]) -> None:
        row = dict(row, data=canonical_json(row["data"]))
        cols = ", ".join(row)
        updates = ", ".join(f"{k} = excluded.{k}" for k in row if k != "id")
        self.conn.execute(f"INSERT INTO items ({cols}) VALUES ({', '.join('?' for _ in row)}) "
                          f"ON CONFLICT (id) DO UPDATE SET {updates}", list(row.values()))

    def mark_removed_except(self, repository: str, keep: set[str]) -> None:
        for r in self.conn.execute("SELECT id FROM items WHERE repository = ? AND removed = 0", (repository,)).fetchall():
            if r["id"] not in keep:
                self.conn.execute("UPDATE items SET removed = 1, updated_at = ? WHERE id = ?", (now_iso(), r["id"]))

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())

    def stories(self) -> list[dict[str, Any]]:
        return [_decode(r) for r in self.conn.execute("SELECT * FROM items WHERE kind = 'story' AND removed = 0")]

    def replace_edges(self, src_ids: set[str], edges: set[tuple[str, str, str]]) -> None:
        for s in src_ids:
            self.conn.execute("DELETE FROM edges WHERE src = ?", (s,))
        self.conn.executemany("INSERT OR IGNORE INTO edges (src, dst, relation) VALUES (?, ?, ?)", sorted(edges))

    def edges_touching(self, item_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM edges WHERE src = ? OR dst = ?", (item_id, item_id))]

    def add_link(self, row: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO links (story_id, change_set_id, declared_in, linked_by, timestamp) "
            "VALUES (:story_id, :change_set_id, :declared_in, :linked_by, :timestamp)", row)

    def links_for_story(self, story_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM links WHERE story_id = ?", (story_id,))]

    def links_for_change_set(self, cs_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM links WHERE change_set_id = ?", (cs_id,))]

    def append_event(self, row: dict[str, Any]) -> dict[str, Any]:
        return _decode(db.append_chained(self.conn, "work_events", dict(row, payload=canonical_json(row["payload"]))))

    def events_for(self, story_id: str) -> list[dict[str, Any]]:
        return [_decode(r) for r in self.conn.execute(
            "SELECT * FROM work_events WHERE story_id = ? ORDER BY seq", (story_id,))]

    def cached_status(self, story_id: str) -> str | None:
        r = self.conn.execute("SELECT status FROM story_status WHERE story_id = ?", (story_id,)).fetchone()
        return r["status"] if r else None

    def set_status(self, story_id: str, previous: str | None, status: str, reason: str) -> None:
        self.conn.execute(
            "INSERT INTO story_status (story_id, status, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (story_id) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at",
            (story_id, status, now_iso()))
        db.append_chained(self.conn, "status_history", {
            "story_id": story_id, "from_status": previous, "to_status": status, "reason": reason,
            "timestamp": now_iso()})

    def verify(self) -> list[dict[str, Any]]:
        return [db.verify_chain(self.conn, t) for t in ("plan_commits", "work_events", "status_history")]
