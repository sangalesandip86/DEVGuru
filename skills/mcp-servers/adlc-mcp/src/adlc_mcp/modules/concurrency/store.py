"""Concurrency Primitives persistence layer.

Hard task claims use SQLite's UNIQUE constraint as an exclusive mutex.
Soft file intents are advisory — conflicts are reported, not blocked.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .domain import (
    TaskClaim, FileIntent, Conflict, CoordMessage,
    DEFAULT_INTENT_TTL_MINUTES, STALE_CLAIM_SECONDS,
)

_MIGRATION_DIR = Path(__file__).parent / "migrations"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _expires_seconds(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class ConcurrencyStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.execute("PRAGMA journal_mode=WAL")

    def migrate(self) -> list[str]:
        applied: list[str] = []
        for sql_file in sorted(_MIGRATION_DIR.glob("*.sql")):
            self._conn.executescript(sql_file.read_text(encoding="utf-8"))
            applied.append(sql_file.name)
        return applied

    def _cleanup_expired_claims(self) -> None:
        now = _now_iso()
        self._conn.execute("DELETE FROM task_claims WHERE expires_at < ?", (now,))

    def _cleanup_expired_intents(self) -> None:
        now = _now_iso()
        self._conn.execute("DELETE FROM file_intents WHERE expires_at < ?", (now,))

    def claim_task(self, task_id: str, actor_id: str) -> tuple[bool, TaskClaim | None]:
        self._cleanup_expired_claims()
        now = _now_iso()
        expires = _expires_seconds(STALE_CLAIM_SECONDS)
        try:
            self._conn.execute(
                "INSERT INTO task_claims (task_id, actor_id, claimed_at, expires_at) "
                "VALUES (?, ?, ?, ?)", (task_id, actor_id, now, expires))
            self._conn.commit()
            return True, TaskClaim(task_id=task_id, actor_id=actor_id,
                                   claimed_at=now, expires_at=expires)
        except sqlite3.IntegrityError:
            row = self._conn.execute(
                "SELECT actor_id, claimed_at, expires_at FROM task_claims WHERE task_id = ?",
                (task_id,)).fetchone()
            if row:
                return False, TaskClaim(task_id=task_id, actor_id=row[0],
                                        claimed_at=row[1], expires_at=row[2])
            return False, None

    def release_task(self, task_id: str, actor_id: str) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM task_claims WHERE task_id = ? AND actor_id = ?",
            (task_id, actor_id))
        self._conn.commit()
        return cursor.rowcount > 0

    def declare_file_intent(self, intent_id: str, actor_id: str, agent_role: str,
                            files: list[str], ttl_minutes: int = DEFAULT_INTENT_TTL_MINUTES,
                            change_set_id: str = "") -> FileIntent:
        self._cleanup_expired_intents()
        now = _now_iso()
        expires = _expires(ttl_minutes)
        self._conn.execute(
            "INSERT OR REPLACE INTO file_intents "
            "(intent_id, actor_id, agent_role, files, declared_at, expires_at, change_set_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (intent_id, actor_id, agent_role, json.dumps(files), now, expires, change_set_id))
        self._conn.commit()
        return FileIntent(intent_id=intent_id, actor_id=actor_id, agent_role=agent_role,
                          files=files, declared_at=now, expires_at=expires,
                          change_set_id=change_set_id)

    def check_conflicts(self, actor_id: str, planned_files: list[str]) -> list[Conflict]:
        self._cleanup_expired_intents()
        conflicts: list[Conflict] = []
        planned_set = set(planned_files)
        planned_dirs = {str(Path(f).parent) for f in planned_files}

        for row in self._conn.execute(
                "SELECT intent_id, actor_id, agent_role, files FROM file_intents "
                "WHERE actor_id != ?", (actor_id,)):
            other_files = json.loads(row[3])
            other_dirs = {str(Path(f).parent) for f in other_files}

            for f in other_files:
                if f in planned_set:
                    conflicts.append(Conflict(
                        file_path=f, this_actor=actor_id,
                        other_actor=row[1], other_role=row[2],
                        other_intent_id=row[0], conflict_type="file_overlap"))

            dir_overlap = planned_dirs & other_dirs
            for d in dir_overlap:
                this_in_dir = [f for f in planned_files if str(Path(f).parent) == d]
                other_in_dir = [f for f in other_files if str(Path(f).parent) == d]
                if not any(f in planned_set for f in other_files):
                    for f in this_in_dir:
                        conflicts.append(Conflict(
                            file_path=f, this_actor=actor_id,
                            other_actor=row[1], other_role=row[2],
                            other_intent_id=row[0], conflict_type="directory_overlap"))
        return conflicts

    def send_message(self, msg: CoordMessage) -> None:
        self._conn.execute(
            "INSERT INTO coord_messages "
            "(message_id, from_actor, from_role, to_actor, content, sent_at, change_set_id, intent_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (msg.message_id, msg.from_actor, msg.from_role, msg.to_actor,
             msg.content, msg.sent_at, msg.change_set_id, msg.intent_id))
        self._conn.commit()

    def get_messages(self, actor_id: str, limit: int = 50) -> list[CoordMessage]:
        rows = self._conn.execute(
            "SELECT message_id, from_actor, from_role, to_actor, content, sent_at, "
            "change_set_id, intent_id FROM coord_messages WHERE to_actor = ? "
            "ORDER BY sent_at DESC LIMIT ?", (actor_id, limit)).fetchall()
        return [CoordMessage(message_id=r[0], from_actor=r[1], from_role=r[2],
                             to_actor=r[3], content=r[4], sent_at=r[5],
                             change_set_id=r[6], intent_id=r[7]) for r in rows]
