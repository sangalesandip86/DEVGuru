"""Concurrency Primitives domain types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_INTENT_TTL_MINUTES = 30
STALE_CLAIM_SECONDS = 10
MAX_BACKOFF_MS = 640


@dataclass
class TaskClaim:
    task_id: str
    actor_id: str
    claimed_at: str
    expires_at: str


@dataclass
class FileIntent:
    intent_id: str
    actor_id: str
    agent_role: str
    files: list[str]
    declared_at: str
    expires_at: str
    change_set_id: str = ""


@dataclass
class Conflict:
    file_path: str
    this_actor: str
    other_actor: str
    other_role: str
    other_intent_id: str
    conflict_type: str = "file_overlap"


@dataclass
class CoordMessage:
    message_id: str
    from_actor: str
    from_role: str
    to_actor: str
    content: str
    sent_at: str
    change_set_id: str = ""
    intent_id: str = ""
