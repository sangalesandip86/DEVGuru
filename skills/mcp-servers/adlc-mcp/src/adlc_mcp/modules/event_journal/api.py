"""Event Journal — public surface. The ONLY file other code may import from this module.

Actor identity (type, id, role) always comes from the authenticated :class:`Identity`, never from
tool arguments. Fail-safe: an unreadable journal raises ``JournalUnreadable`` (BLOCKED).
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

from .domain import JournalEntry
from .store import JournalStore, JournalUnreadable  # noqa: F401  (re-exported for callers)

NAME = "event_journal"


class EventJournal:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._store = JournalStore(conn)

    def migrate(self) -> list[str]:
        return self._store.migrate()

    def append_journal(self, identity: Identity, *, run_id: str, event_type: str,
                       payload: dict[str, Any] | None = None, change_set_id: str = "",
                       visibility: str = "INTERNAL", timestamp: str | None = None) -> dict[str, Any]:
        if not run_id:
            raise ValidationError("run_id is required")
        entry = JournalEntry(
            id=uuid.uuid4().hex, run_id=run_id, event_type=event_type, actor_type=identity.actor_type,
            actor_id=identity.actor_id, payload=dict(payload or {}), timestamp=timestamp or now_iso(),
            change_set_id=change_set_id or "", agent_role=identity.agent_role or "", visibility=visibility)
        self._store.append(entry)
        return asdict(entry)

    def fold_state(self, run_id: str) -> dict[str, Any]:
        if not run_id:
            raise ValidationError("run_id is required")
        return asdict(self._store.fold_state(run_id))

    def query_journal(self, *, run_id: str | None = None, change_set_id: str | None = None,
                      event_type: str | None = None, since: str | None = None, until: str | None = None,
                      limit: int = 100) -> list[dict[str, Any]]:
        return [asdict(e) for e in self._store.query(run_id, change_set_id, event_type, since, until, limit)]

    def heartbeat(self, identity: Identity, *, run_id: str, agent_role: str | None = None) -> dict[str, Any]:
        """Record session.heartbeat. ``agent_role`` is informational only; the credential's role is used."""
        return self.append_journal(identity, run_id=run_id, event_type="session.heartbeat",
                                   payload={"claimed_role": agent_role} if agent_role else {})

    def verify_chain(self, run_id: str) -> dict[str, Any]:
        ok, detail = self._store.verify_chain(run_id)
        return {"run_id": run_id, "ok": ok, "detail": detail}


class EventJournalModule:
    name = NAME

    def __init__(self, config: Config) -> None:
        self._conn = db.connect(config.db_path(NAME))
        self._api = EventJournal(self._conn)

    def migrate(self, conn: sqlite3.Connection | None = None) -> None:
        self._api.migrate()

    def register_tools(self, server: Any, identity: Identity) -> list[str]:
        from .tools import register_tools

        return register_tools(server, self._api, identity)

    @property
    def api(self) -> EventJournal:
        return self._api

    def close(self) -> None:
        self._conn.close()


def create_module(config: Config) -> EventJournalModule:
    module = EventJournalModule(config)
    module.migrate()
    return module
