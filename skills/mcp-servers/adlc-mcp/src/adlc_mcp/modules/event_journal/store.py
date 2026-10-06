"""Event Journal persistence. Owns ``event_journal.db``; no other module touches it.

Entries are append-only and hash-chained per ``run_id``:
``entry_hash = SHA-256(prev_hash + id + canonical_json(payload))``; the first entry of a run
chains from ``GENESIS_HASH``. Fail-safe: any unreadable/corrupt journal raises
:class:`JournalUnreadable` (callers must treat that as BLOCKED, never as "empty").
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from adlc_mcp.kernel import db
from adlc_mcp.kernel.errors import AdlcError, ValidationError
from adlc_mcp.kernel.util import GENESIS_HASH, canonical_json, now_iso, parse_iso, sha256_hex

from .domain import ACTOR_TYPES, EVENT_TYPES, JournalEntry, WorkState, liveness

MODULE = "event_journal"
MIGRATIONS = Path(__file__).parent / "migrations"
_COLS = ("id", "run_id", "change_set_id", "event_type", "actor_type", "actor_id", "agent_role",
         "payload", "prev_hash", "entry_hash", "timestamp", "visibility")


class JournalUnreadable(AdlcError):
    """The journal cannot be read or parsed. BLOCKED: do not proceed as if it were empty."""


def compute_hash(prev_hash: str, entry_id: str, payload: dict[str, Any]) -> str:
    return sha256_hex(prev_hash + entry_id + canonical_json(payload))


def _norm_ts(value: str) -> str:
    return parse_iso(value).isoformat(timespec="microseconds")


def _to_entry(row: sqlite3.Row) -> JournalEntry:
    d = {c: row[c] for c in _COLS}
    try:
        d["payload"] = json.loads(d["payload"])
    except (TypeError, ValueError) as exc:
        raise JournalUnreadable(f"BLOCKED: journal entry {d['id']} has an unreadable payload") from exc
    return JournalEntry(**d)


class JournalStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def migrate(self) -> list[str]:
        return db.run_migrations(self.conn, MODULE, MIGRATIONS)

    # ------------------------------------------------------------------ write
    def append(self, entry: JournalEntry) -> str:
        """Validate, chain and insert ``entry``; returns its id. prev_hash/entry_hash are computed here."""
        if entry.event_type not in EVENT_TYPES:
            raise ValidationError(f"unknown event_type {entry.event_type!r}")
        if entry.actor_type not in ACTOR_TYPES:
            raise ValidationError(f"invalid actor_type {entry.actor_type!r}")
        if not entry.run_id or not entry.id:
            raise ValidationError("run_id and id are required")
        if not isinstance(entry.payload, dict):
            raise ValidationError("payload must be an object")
        try:
            payload_json = canonical_json(entry.payload)
            entry.timestamp = _norm_ts(entry.timestamp)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"invalid payload or timestamp: {exc}") from exc
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                prev = self._last_hash(entry.run_id)
                entry.prev_hash = prev
                entry.entry_hash = compute_hash(prev, entry.id, entry.payload)
                row = {**entry.__dict__, "payload": payload_json}
                self.conn.execute(
                    f"INSERT INTO journal_entries ({', '.join(_COLS)}) VALUES ({', '.join('?' for _ in _COLS)})",
                    [row[c] for c in _COLS])
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
        except sqlite3.Error as exc:
            raise JournalUnreadable(f"BLOCKED: journal not writable: {exc}") from exc
        return entry.id

    # ------------------------------------------------------------------ read
    def _last_hash(self, run_id: str | None = None) -> str:
        if run_id is None:
            r = self.conn.execute("SELECT entry_hash FROM journal_entries ORDER BY seq DESC LIMIT 1").fetchone()
        else:
            r = self.conn.execute("SELECT entry_hash FROM journal_entries WHERE run_id = ? ORDER BY seq DESC LIMIT 1",
                                  (run_id,)).fetchone()
        return r["entry_hash"] if r else GENESIS_HASH

    def last_hash(self, run_id: str | None = None) -> str:
        """Hash of the newest entry (of ``run_id`` if given, else of the whole journal)."""
        try:
            return self._last_hash(run_id)
        except sqlite3.Error as exc:
            raise JournalUnreadable(f"BLOCKED: journal unreadable: {exc}") from exc

    def query(self, run_id: str | None = None, change_set_id: str | None = None, event_type: str | None = None,
              since: str | None = None, until: str | None = None, limit: int = 100) -> list[JournalEntry]:
        """Newest-last list of up to ``limit`` most recent matching entries (since inclusive, until exclusive)."""
        clauses, args = [], []
        for col, val in (("run_id", run_id), ("change_set_id", change_set_id), ("event_type", event_type)):
            if val:
                clauses.append(f"{col} = ?")
                args.append(val)
        try:
            if since:
                clauses.append("timestamp >= ?")
                args.append(_norm_ts(since))
            if until:
                clauses.append("timestamp < ?")
                args.append(_norm_ts(until))
        except ValueError as exc:
            raise ValidationError(f"invalid timestamp: {exc}") from exc
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            rows = self.conn.execute(
                f"SELECT * FROM journal_entries{where} ORDER BY seq DESC LIMIT ?", (*args, max(1, int(limit)))).fetchall()
        except sqlite3.Error as exc:
            raise JournalUnreadable(f"BLOCKED: journal unreadable: {exc}") from exc
        return [_to_entry(r) for r in reversed(rows)]

    def _all(self, run_id: str) -> list[JournalEntry]:
        try:
            rows = self.conn.execute("SELECT * FROM journal_entries WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
        except sqlite3.Error as exc:
            raise JournalUnreadable(f"BLOCKED: journal unreadable: {exc}") from exc
        return [_to_entry(r) for r in rows]

    def verify_chain(self, run_id: str) -> tuple[bool, str]:
        prev = GENESIS_HASH
        count = 0
        for e in self._all(run_id):
            if e.prev_hash != prev:
                return False, f"entry {e.id}: prev_hash does not match previous entry (gap, reorder or deletion)"
            if compute_hash(prev, e.id, e.payload) != e.entry_hash:
                return False, f"entry {e.id}: entry_hash mismatch (content altered)"
            prev = e.entry_hash
            count += 1
        return True, f"ok: {count} entries verified"

    def fold_state(self, run_id: str, now: datetime | None = None) -> WorkState:
        """O(n) reconstruction of the run's work state from its events."""
        return fold(self._all(run_id), now)


def fold(entries: list[JournalEntry], now: datetime | None = None) -> WorkState:
    """Pure fold of ordered entries into a WorkState. ``now`` (default: current time) only affects liveness."""
    ref = now or parse_iso(now_iso())
    s = WorkState()
    for e in entries:
        p, t, actor = e.payload, e.event_type, e.actor_id
        if t in ("session.join", "session.heartbeat"):
            sess = s.active_sessions.setdefault(actor, {"actor_type": e.actor_type, "joined_at": e.timestamp})
            sess.update(agent_role=e.agent_role, last_seen=e.timestamp)
        elif t == "session.leave":
            s.active_sessions.pop(actor, None)
        elif t in ("task.start", "task.claim", "task.checkpoint"):
            tid = str(p.get("task_id") or e.id)
            task = s.active_tasks.setdefault(tid, {"task_id": tid, "started_at": e.timestamp})
            task.update(owner=actor, last_event=t, updated_at=e.timestamp)
            if t == "task.checkpoint":
                task["checkpoint"] = p.get("checkpoint", p)
        elif t in ("task.deliver", "task.abandon"):
            s.active_tasks.pop(str(p.get("task_id") or ""), None)
        elif t == "stage.enter":
            s.current_stage = str(p.get("stage", ""))
            s.stage_history.append({"event": t, "stage": s.current_stage, "at": e.timestamp})
        elif t in ("stage.exit", "stage.gate_pass", "stage.gate_fail"):
            s.stage_history.append({"event": t, "stage": str(p.get("stage", s.current_stage)), "at": e.timestamp,
                                    **({"gate": p["gate"]} if "gate" in p else {})})
            if t == "stage.exit" and s.current_stage == p.get("stage", s.current_stage):
                s.current_stage = ""
        elif t == "evidence.decision":
            s.decisions.append({"id": e.id, "actor_id": actor, "at": e.timestamp, **p})
        elif t == "coord.intent_claim":
            iid = str(p.get("intent_id") or e.id)
            s.open_intents[iid] = {"intent_id": iid, "owner": actor, "claimed_at": e.timestamp,
                                   "target": p.get("target")}
        elif t == "coord.intent_release":
            s.open_intents.pop(str(p.get("intent_id") or ""), None)
        elif t == "system.halt":
            s.halted, s.halt_reason = True, str(p.get("reason", ""))
        elif t == "system.resume":
            s.halted, s.halt_reason = False, ""
    for sess in s.active_sessions.values():
        age = (ref - parse_iso(sess["last_seen"])).total_seconds()
        sess["liveness"] = liveness(max(age, 0.0))
    return s
