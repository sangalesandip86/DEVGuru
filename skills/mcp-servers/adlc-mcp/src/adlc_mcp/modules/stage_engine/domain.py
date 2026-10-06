"""Stage Transition Engine domain types.

Declarative transition graph defining allowed stage progressions,
required roles, required outputs, and gate checks for each stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STAGES = (
    "INTAKE", "ARCHITECTURE", "PLAN", "DESIGN",
    "IMPLEMENT", "TEST", "REVIEW", "INTEGRATE",
    "RELEASE", "LEARN",
)

SIDE_STATES = ("BLOCKED", "FAILED", "CANCELLED")

STAGE_SET = set(STAGES) | set(SIDE_STATES)

TRANSITION_GRAPH: dict[str, dict[str, Any]] = {
    "INTAKE": {
        "allowed_next": ["ARCHITECTURE", "PLAN"],
        "required_roles": ["product-owner"],
        "required_outputs": ["requirement_id"],
        "gate": "readiness_check",
    },
    "ARCHITECTURE": {
        "allowed_next": ["PLAN"],
        "required_roles": ["architect"],
        "required_outputs": ["design_decision"],
        "gate": "design_reviewed",
    },
    "PLAN": {
        "allowed_next": ["DESIGN", "IMPLEMENT"],
        "required_roles": ["product-planner"],
        "required_outputs": ["plan_id", "story_ids"],
        "gate": "plan_approved",
    },
    "DESIGN": {
        "allowed_next": ["IMPLEMENT"],
        "required_roles": ["architect"],
        "required_outputs": ["design_spec"],
        "gate": "design_reviewed",
    },
    "IMPLEMENT": {
        "allowed_next": ["TEST"],
        "required_roles": ["developer"],
        "required_outputs": ["implementation_commit"],
        "gate": "tests_pass",
    },
    "TEST": {
        "allowed_next": ["REVIEW"],
        "required_roles": ["qa-derive", "test-engineer"],
        "required_outputs": ["test_results"],
        "gate": "verification_pass",
    },
    "REVIEW": {
        "allowed_next": ["INTEGRATE", "IMPLEMENT"],
        "required_roles": ["code-reviewer", "security-reviewer"],
        "required_outputs": ["review_verdict"],
        "gate": "review_accepted",
    },
    "INTEGRATE": {
        "allowed_next": ["RELEASE"],
        "required_roles": ["developer"],
        "required_outputs": ["merge_event"],
        "gate": "integration_verified",
    },
    "RELEASE": {
        "allowed_next": ["LEARN"],
        "required_roles": ["human"],
        "required_outputs": ["deployment_record"],
        "gate": "release_approved",
    },
    "LEARN": {
        "allowed_next": [],
        "required_roles": ["qa-diagnose"],
        "required_outputs": ["retro_summary"],
        "gate": None,
    },
}

SIDE_STATE_RULES: dict[str, dict[str, Any]] = {
    "BLOCKED": {
        "returns_to": "previous_state",
        "triggers": ["gate_failure", "dependency_unmet", "escalation"],
    },
    "FAILED": {
        "triggers": ["retry_exhausted", "unrecoverable_error"],
    },
    "CANCELLED": {
        "triggers": ["human_decision"],
    },
}


@dataclass
class TransitionRequest:
    change_set_id: str
    from_stage: str
    to_stage: str
    actor_role: str
    outputs: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class TransitionResult:
    allowed: bool
    from_stage: str
    to_stage: str
    reason: str = ""
    missing_outputs: list[str] = field(default_factory=list)
    missing_roles: list[str] = field(default_factory=list)
    gate: str | None = None


@dataclass
class StageState:
    change_set_id: str
    current_stage: str = "INTAKE"
    previous_stage: str = ""
    transitions: list[dict[str, Any]] = field(default_factory=list)
    allowed_next: list[str] = field(default_factory=list)
    required_outputs: list[str] = field(default_factory=list)
    gate: str | None = None
