---
name: skill-router
description: Decides which skills load for a task — mandatory bindings by policy, contextual skills by analysis — in two phases. Use at the start of every Change Set or task, and again after risk tier and dependency scan are known.
metadata:
  group: skill-routing
  phase: 1
  binding: true
  plan-ref: "§4.4"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Skill Router

## Purpose
Select the skills an agent session loads. Mandatory skills are loaded **by policy, not by LLM
judgment** (plan §1). Contextual skills are added from analysis. Routing is two-phase so the
deeper second pass can catch mandatory triggers the cheap first pass missed.

## When this applies
- At task start (Phase 1 — coarse routing).
- After initial analysis produces a risk tier, a dependency scan, or a changed-file list
  (Phase 2 — refined routing).
- Again whenever the changed-file set grows during execution.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Cross-cutting: this skill has no stage inputs of its own and is loaded alongside whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

- **Inputs:** the requested start and end stages, requirement text, file paths, and (Phase 2 routing) the stack fingerprint FACT.
- **ADOPT:** if `.adlc/catalog/stack.json` exists for the current snapshot, use it; if missing or stale, over-include stack skills and request re-discovery.
- **Repo roles:** whatever the resolved workspace contains; routing reads the repo map to apply path-based bindings.

## Procedure
1. Always load the binding cross-cutting skills: everything under `grounding/` and `core/`,
   plus `self-improvement/failure-capture` from Phase 1 onward.
2. **Phase 1 — coarse:** match requirement text, repo names, and file paths against the
   mandatory triggers in [scope-matrix.md](reference/scope-matrix.md). Over-include when in doubt.
3. Compute an initial risk tier with the Phase 0 lookup
   (`../../change-management/risk-tiering/scripts/path_tier_lookup.py`). If it cannot be
   computed, use `HIGH` (fail-safe, §5.3).
4. **Phase 2 — refined:** once analysis exists, re-run the *mandatory* binding computation
   against the deeper understanding (domain of the code, not only keywords), then add contextual
   skills. See [two-phase-routing.md](reference/two-phase-routing.md).
5. If Phase 2 finds a mandatory trigger Phase 1 missed, apply the binding retroactively for the
   rest of the task and record a near-miss incident.
6. Never remove a binding skill Phase 1 included.
7. If a required skill or role is not yet built in the current phase, route to the named human
   standing in for it (Degraded Mode, §2) and record that human as the handoff target.

## Outputs
- `DECISION` entry: the routed skill set, citing the Phase 1 and Phase 2 trigger matches as sources.
- `INFERENCE` entry for any Phase 2 domain classification (`input_references` → the evidence used).
- Incident record (`record_incident`) for each near-miss.

## Enforcement
Mandatory loading is enforced by the orchestrator / managed settings that inject the binding skill
set; this skill documents the selection logic. Near-miss logging is guideline only until the
orchestrator emits it automatically.

## References
- [reference/scope-matrix.md](reference/scope-matrix.md)
- [reference/two-phase-routing.md](reference/two-phase-routing.md)
- [../binding-vs-advisory/SKILL.md](../binding-vs-advisory/SKILL.md)
- [../token-budget-optimizer/SKILL.md](../token-budget-optimizer/SKILL.md)
- [../../change-management/risk-tiering/SKILL.md](../../change-management/risk-tiering/SKILL.md)
