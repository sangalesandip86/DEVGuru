# Reviewer Diversity

Plan ref: §4.7, §2 Phase 1.

## Rule

For **HIGH** and **CRITICAL** tiers, at least one reviewer — security-reviewer, code-reviewer, or
architect — must either:

- run on a model from a **different family** than the implementing developer agent, or
- be a **deterministic tool** (SAST, type checker, contract checker, linter) rather than an LLM.

LOW and MEDIUM tiers have no diversity requirement.

## Why

Same-family models correlate in their blind spots more than different families do. The platform
already spans Claude Code and GitHub Copilot, so arranging a different-family reviewer costs nothing
extra.

## How it is checked

- Each ledger entry records `model_id` (plan §4.3). The orchestrator compares the developer's
  `model_id` family against the reviewers' for the Change Set.
- If no qualifying reviewer exists, the reviewing role records a `RISK` entry and the Change Set
  cannot satisfy its gates for that tier until one is added (or a human stands in — Degraded Mode, §2).
- Role specs declare `model_family_constraint: different-from-implementer-for-HIGH-CRITICAL`; the
  generator surfaces it in the generated agent description so whoever launches the reviewer sees it.

## Enforcement

Guideline only until the orchestrator implements the `model_id` family comparison as a gate check.
Track it in the §5.6 enforcement table when it lands.
