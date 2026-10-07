"""Event Journal domain types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EVENT_TYPES = {
    "session.join", "session.leave", "session.heartbeat",
    "task.start", "task.claim", "task.deliver", "task.abandon", "task.checkpoint",
    "stage.enter", "stage.exit", "stage.gate_pass", "stage.gate_fail",
    "evidence.fact", "evidence.inference", "evidence.decision",
    "coord.intent_claim", "coord.intent_release", "coord.conflict", "coord.message",
    "system.halt", "system.resume", "system.error",
    "session.tool_call", "session.prompt",
}

ACTOR_TYPES = {"HUMAN", "AGENT", "SYSTEM"}

LIVENESS_THRESHOLDS = {
    "active": 120,      # < 2 minutes
    "idle": 1800,       # 2-30 minutes
    "quiet": 86400,     # 30 min - 24 hours
    "dropped": None,    # > 24 hours
}


def liveness(age_seconds: float) -> str:
    """Classify seconds since last heartbeat/activity."""
    for name in ("active", "idle", "quiet"):
        if age_seconds < LIVENESS_THRESHOLDS[name]:
            return name
    return "dropped"


@dataclass
class JournalEntry:
    id: str
    run_id: str
    event_type: str
    actor_type: str
    actor_id: str
    payload: dict[str, Any]
    timestamp: str
    change_set_id: str = ""
    agent_role: str = ""
    prev_hash: str = ""
    entry_hash: str = ""
    visibility: str = "INTERNAL"


@dataclass
class WorkState:
    active_sessions: dict[str, dict] = field(default_factory=dict)
    active_tasks: dict[str, dict] = field(default_factory=dict)
    current_stage: str = ""
    stage_history: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    open_intents: dict[str, dict] = field(default_factory=dict)
    halted: bool = False
    halt_reason: str = ""
