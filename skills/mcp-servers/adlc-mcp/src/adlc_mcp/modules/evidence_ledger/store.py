"""Evidence Ledger persistence. Owns ``evidence_ledger.db``; no other module touches it.

Evidence payloads (migration 0002) live in ``evidence_content``, outside the hash chain; the
chained ``evidence`` row carries only a salted commitment (``content_hash``). See
``reference/mcp-server-design.md`` §4 "Retention".
"""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from adlc_mcp.kernel import db
from adlc_mcp.kernel.util import loads_or_none, parse_iso, sha256_hex

MODULE = "evidence_ledger"
MIGRATIONS = Path(__file__).parent / "migrations"
_JSON_COLS = ("input_references", "output_references", "decision_ids", "metadata", "evidence_refs",
              "verification_strength", "occurrences", "incident_refs", "sanitization_result")
_EVIDENCE_SELECT = (
    "SELECT e.*, c.content AS _payload, c.created_at AS _payload_created "
    "FROM evidence e LEFT JOIN evidence_content c ON c.entry_id = e.entry_id"
)


def _decode(row: sqlite3.Row | dict | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for col in _JSON_COLS:
        if col in out and isinstance(out[col], str):
            out[col] = loads_or_none(out[col])
    if "pattern_eligible" in out and out["pattern_eligible"] is not None:
        out["pattern_eligible"] = bool(out["pattern_eligible"])
    return out


def content_commitment(salt: str, content: str) -> str:
    return "sha256:" + sha256_hex(salt + content)


class EvidenceStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def migrate(self) -> list[str]:
        return db.run_migrations(self.conn, MODULE, MIGRATIONS)

    # settings ---------------------------------------------------------------------------
    def set_retention_days(self, days: int) -> None:
        self.conn.execute("UPDATE ledger_settings SET value = ? WHERE key = 'evidence_retention_days'", (str(days),))

    def retention_days(self) -> int:
        return int(self.conn.execute(
            "SELECT value FROM ledger_settings WHERE key = 'evidence_retention_days'").fetchone()["value"])

    # evidence ---------------------------------------------------------------------------
    def append_entry(self, row: dict[str, Any], content: str) -> dict[str, Any]:
        """Chain the row with a salted commitment; store the payload alongside, in one transaction."""
        salt = secrets.token_hex(16)
        created = row["timestamp"]
        row = dict(row, content="", content_hash=content_commitment(salt, content))

        def store_payload(conn: sqlite3.Connection, full: dict[str, Any]) -> None:
            conn.execute("INSERT INTO evidence_content (entry_id, salt, content, created_at) VALUES (?, ?, ?, ?)",
                         (full["entry_id"], salt, content, created))

        full = db.append_chained(self.conn, "evidence", row, after_insert=store_payload)
        return self.get_entry(full["entry_id"])

    def _materialize(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        out = _decode(row)
        if out is None:
            return None
        payload = out.pop("_payload", None)
        payload_created = out.pop("_payload_created", None)
        if out.get("content_hash") is None:
            out["content_status"] = "INLINE"            # written before migration 0002
        elif payload is not None and not self._expired(payload_created):
            out["content"], out["content_status"] = payload, "PRESENT"
        else:
            out["content"], out["content_status"] = None, "EXPIRED"
        return out

    def _expired(self, created: str | None) -> bool:
        if created is None:
            return True
        return parse_iso(created) < datetime.now(timezone.utc) - timedelta(days=self.retention_days())

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        return self._materialize(self.conn.execute(f"{_EVIDENCE_SELECT} WHERE e.entry_id = ?", (entry_id,)).fetchone())

    def get_entries(self, entry_ids: list[str]) -> list[dict[str, Any]]:
        if not entry_ids:
            return []
        marks = ",".join("?" for _ in entry_ids)
        rows = self.conn.execute(f"{_EVIDENCE_SELECT} WHERE e.entry_id IN ({marks})", entry_ids)
        return [self._materialize(r) for r in rows]

    def children_of(self, entry_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(f"{_EVIDENCE_SELECT} WHERE e.parent_entry_id = ? ORDER BY e.seq", (entry_id,))
        return [self._materialize(r) for r in rows]

    def query_entries(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        where, args = _where(filters, prefix="e.")
        rows = self.conn.execute(f"{_EVIDENCE_SELECT}{where} ORDER BY e.seq DESC LIMIT ?", (*args, limit))
        return [self._materialize(r) for r in rows]

    def purge_expired_content(self) -> int:
        """Delete payloads older than the retention period. The storage trigger refuses younger rows."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days())
        doomed = [r["entry_id"] for r in self.conn.execute("SELECT entry_id, created_at FROM evidence_content")
                  if parse_iso(r["created_at"]) < cutoff]
        for entry_id in doomed:
            self.conn.execute("DELETE FROM evidence_content WHERE entry_id = ?", (entry_id,))
        return len(doomed)

    def verify_content(self) -> dict[str, Any]:
        bad = [r["entry_id"] for r in self.conn.execute(
            "SELECT e.entry_id, e.content_hash, c.salt, c.content FROM evidence e "
            "JOIN evidence_content c ON c.entry_id = e.entry_id")
            if content_commitment(r["salt"], r["content"]) != r["content_hash"]]
        return {"table": "evidence_content", "ok": not bad, "mismatched_entry_ids": bad}

    # incidents / lessons ---------------------------------------------------------------
    def append_incident(self, row: dict[str, Any]) -> dict[str, Any]:
        return _decode(db.append_chained(self.conn, "incidents", row))

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone())

    def get_incidents(self, incident_ids: list[str]) -> list[dict[str, Any]]:
        if not incident_ids:
            return []
        marks = ",".join("?" for _ in incident_ids)
        return [_decode(r) for r in self.conn.execute(
            f"SELECT * FROM incidents WHERE incident_id IN ({marks})", incident_ids)]

    def query_incidents(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        where, args = _where(filters)
        rows = self.conn.execute(f"SELECT * FROM incidents{where} ORDER BY seq DESC LIMIT ?", (*args, limit))
        return [_decode(r) for r in rows]

    def last_incident_at(self, skill: str, step: str, failure_class: str) -> str | None:
        r = self.conn.execute(
            "SELECT MAX(timestamp) AS t FROM incidents WHERE skill = ? AND step = ? AND failure_class = ?",
            (skill, step, failure_class)).fetchone()
        return r["t"] if r else None

    def append_lesson(self, row: dict[str, Any]) -> dict[str, Any]:
        return _decode(db.append_chained(self.conn, "lessons", row))

    def get_lesson(self, lesson_id: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute("SELECT * FROM lessons WHERE lesson_id = ?", (lesson_id,)).fetchone())

    def query_lessons(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        where, args = _where(filters)
        rows = self.conn.execute(f"SELECT * FROM lessons{where} ORDER BY seq DESC LIMIT ?", (*args, limit))
        return [_decode(r) for r in rows]

    def verify(self) -> list[dict[str, Any]]:
        return [db.verify_chain(self.conn, t) for t in ("evidence", "incidents_v1", "incidents", "lessons")] + [
            self.verify_content()]


def _where(filters: dict[str, Any], prefix: str = "") -> tuple[str, list[Any]]:
    clauses, args = [], []
    for col, val in filters.items():
        if val is None:
            continue
        clauses.append(f"{prefix}{col} = ?")
        args.append(val)
    return ((" WHERE " + " AND ".join(clauses)) if clauses else ""), args

