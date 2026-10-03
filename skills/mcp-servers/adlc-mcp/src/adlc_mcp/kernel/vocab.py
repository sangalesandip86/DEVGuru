"""Platform vocabulary (docs/authoring-conventions.md). Do not invent variants."""
from __future__ import annotations

from typing import Iterable

CLASSIFICATIONS = ("FACT", "INFERENCE", "ASSUMPTION", "PROPOSAL", "QUESTION", "DECISION", "RISK")
LIFECYCLE_STATES = ("DRAFT", "PROPOSED", "REVIEWED", "VERIFIED", "APPROVED", "REJECTED")
TRUST_LEVELS = ("SYSTEM", "ORGANIZATIONAL", "REPOSITORY", "EXTERNAL_STRUCTURED", "EXTERNAL_UNSTRUCTURED")
ACTOR_TYPES = ("HUMAN", "AGENT", "SYSTEM")
RISK_TIERS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
CHANGE_SET_STATES = (
    "DRAFT", "SCOPED", "PLANNED", "PLAN_APPROVED", "EXECUTING", "VERIFYING", "INTEGRATED", "RELEASED",
    "BLOCKED", "FAILED", "CANCELLED", "ROLLED_BACK",
)
OPERATION_CLASSES = ("READ", "WORKSPACE_WRITE", "REPO_WRITE", "EXTERNAL_MUTATION", "DEPLOY")
RETRY_POLICIES = ("RETRY", "STOP", "ESCALATE", "REPLAN", "RESUME")
ESCALATION_REASON_CODES = ("UNRESOLVED_DEPENDENCY", "UNKNOWN_BLAST_RADIUS", "SENSITIVE_PATH", "COMPATIBILITY_UNKNOWN")
HUMAN_APPROVERS = ("human:tech-lead", "human:security-lead", "human:product-owner", "human:release-manager")
AGENT_ROLES = (
    "product-owner", "architect", "developer", "qa-derive", "qa-diagnose", "security-reviewer", "code-reviewer",
)
# `ci` and `server` are used only by SYSTEM actors (CI ingesters, the server itself).
TOOLS = ("claude-code", "copilot", "ci", "server")

# Lower index = more trusted.
TRUST_ORDER = {t: i for i, t in enumerate(TRUST_LEVELS)}


def lowest_trust(levels: Iterable[str]) -> str:
    """The least-trusted level in ``levels`` (fail-safe: nothing → EXTERNAL_UNSTRUCTURED)."""
    levels = list(levels)
    return max(levels, key=lambda t: TRUST_ORDER[t]) if levels else "EXTERNAL_UNSTRUCTURED"


def tier_index(tier: str) -> int:
    return RISK_TIERS.index(tier)


def max_tier(tiers: Iterable[str]) -> str:
    return max(tiers, key=tier_index)
