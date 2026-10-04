---
name: dependency-mapper
description: Map story and epic dependencies with evidence levels; unconfirmed stays UNRESOLVED. Use during decomposition, refinement, and milestones.
metadata:
  group: product-planning
  phase: 2
  binding: false
  plan-ref: "§4.12, §4.5, §5.3"
  stage: PLAN
  inputs: [ready-story]
  outputs: []
  repo_roles: [planning, app, contracts]
---

# Dependency Mapper

## Purpose
Find out what each story needs from outside itself, and say how sure we are. A dependency
the planner didn't find is a dependency the developer finds mid-implementation, which is the
most expensive time to find it.

This skill is the **planning-level** view. It reuses the code-level scanners from
[change-management/dependency-discovery](../../change-management/dependency-discovery/SKILL.md)
and does not duplicate them.

## When this applies
- Epic decomposition and story writing (first pass).
- Refinement, when developer or qa-derive raise a hidden dependency.
- Milestone planning, for cross-story ordering and risks.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md). Stage PLAN.

- **Inputs:** stories and the resolved repos they touch.
- **ASK:** a dependency pointing at an unresolved repo produces one QUESTION with candidates; it stays UNRESOLVED until answered.
- **Repo roles:** `planning`, `app`, `contracts`.

## Procedure
1. **Story → story / epic.** For each story, ask what must exist first: data, an endpoint, a decision, a spike's answer. Record `{ref: ST-n, kind: story, status, evidence_level: DECLARED}`.
2. **Story → code.** Run the scanners over the repos and paths in `affected_paths`:
   ```bash
   python skills/change-management/dependency-discovery/scripts/scan-imports.py <repo-root> --files <files under affected_paths>
   python skills/change-management/dependency-discovery/scripts/scan-api-calls.py --repo <name>=<repo-root> [--repo <other>=<path> ...]
   ```
   Callers of changed modules and outbound API calls become `kind: contract` or `kind: external` dependencies with `evidence_level: STATIC`. Anything the scanners report as unresolved stays `UNRESOLVED`.
3. **Story → contract.** For any contract in `touches.api_contracts`, list its consumers (contract registry, Phase 3; before that, scanner output plus asking the owners). Each consumer is a dependency or a risk.
4. **Story → environment, data or team.** Feeds, credentials, environments, approvals from other teams. These are `DECLARED` until someone confirms them.
5. **Set the status, fail-safe** (plan §5.3):
   - `RESOLVED`: confirmed, with a source (a merged story, a ledger statement from the owning team, an observed deployment).
   - `UNRESOLVED`: the default for anything unconfirmed. It **blocks READY** (DoR `dependencies_resolved`).
   - `ACCEPTED_RISK`: a human (`owner: human:<role>`) decided to proceed anyway. This is recorded as that human's DECISION.
   - Never record "no dependency" because a scan found nothing. A scanner can't see dynamic dispatch, config-driven URLs or message topics. Absence of evidence stays a QUESTION when the story's type or tier suggests a dependency should exist.
6. **Check for cycles.** If ST-a depends on ST-b and ST-b depends on ST-a, the slicing is wrong. Re-slice; don't paper over it.
7. **Write the dependencies** into the story and epic files through a PR, and record an INFERENCE entry summarising the dependency graph for the milestone-planner.

## Outputs
- `dependencies[]` entries in story and epic files, each with `kind`, `status`, `evidence_level` and `owner` when `ACCEPTED_RISK`.
- Ledger: INFERENCE (the graph summary), QUESTIONs for suspected but unconfirmed dependencies, and RISKs for dependencies on unowned systems.

## Enforcement
**Guideline only** — no enforcement point yet.

- **UNRESOLVED blocks READY:** `readiness_gate.py` (DoR item `dependencies_resolved`).
- **ACCEPTED_RISK needs a human owner, and referenced stories and epics must exist:** `plan_lint.py`.
- **Completeness of discovery** is a guideline: static analysis is bounded. The backstops are the developer feasibility review and the snapshot staleness rules at execution time.

## References
- [change-management/dependency-discovery](../../change-management/dependency-discovery/SKILL.md)
- [grounding/ambiguity-escalation/reference/fail-safe-defaults.md](../../grounding/ambiguity-escalation/reference/fail-safe-defaults.md)
- [milestone-planner](../milestone-planner/SKILL.md) · [story-refinement](../story-refinement/SKILL.md)
