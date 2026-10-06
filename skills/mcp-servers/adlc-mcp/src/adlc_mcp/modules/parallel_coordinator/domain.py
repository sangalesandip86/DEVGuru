"""Parallel Execution Coordinator domain types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_WORKERS = 8

WORKER_STATES = {"pending", "running", "completed", "failed", "stopped"}

ALLOWED_GIT_COMMANDS = frozenset({
    "git status",
    "git diff",
    "git diff --staged",
    "git log --oneline -20",
})

DENIED_GIT_PATTERN = r"^git\s+(push|force|reset|rebase|merge|checkout\s+(-b|--orphan))"

ENV_ALLOWLIST = frozenset({
    "HOME", "PATH", "LANG", "TERM", "EDITOR",
    "ADLC_SKILLS_ROOT", "ADLC_CHANGE_SET_ID",
    "ADLC_WORKER_ID", "ADLC_RISK_TIER",
    "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
})

AUTO_START_CONDITIONS = [
    "historical_calibration_exists",
    "standalone_task_budget_exists",
    "calibrated_effort_within_budget",
    "risk_tier_not_critical",
    "single_repository",
    "zero_sensitive_path_matches",
]


@dataclass
class WorkItem:
    item_id: str
    change_set_id: str
    description: str
    planned_files: list[str] = field(default_factory=list)
    role: str = "developer"
    state: str = "pending"
    worker_id: str = ""
    worktree_path: str = ""
    result: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParallelPlan:
    plan_id: str
    change_set_id: str
    items: list[WorkItem] = field(default_factory=list)
    max_workers: int = MAX_WORKERS
    auto_start_allowed: bool = False
    auto_start_reasons: list[str] = field(default_factory=list)


@dataclass
class WorkerStatus:
    worker_id: str
    item_id: str
    state: str = "pending"
    role: str = "developer"
    worktree_path: str = ""
    progress: str = ""
    error: str = ""
