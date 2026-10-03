---
name: token-budget-optimizer
description: Chooses which model runs and what context loads for each role and task, within budget, without ever reducing grounding. Use when planning a task, when context pressure appears, or when a budget threshold is hit.
metadata:
  group: skill-routing
  phase: 1
  binding: false
  plan-ref: "§4.4"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Token Budget Optimizer

## Purpose
Minimize cost and context use. **Accuracy wins over cost**: this skill decides *what loads* and
*which model runs*, never *whether grounding happens* (§1).

## When this applies
- Task planning (model and budget per role).
- Context use crosses the decomposition threshold.
- A cost-control threshold is reached.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Cross-cutting: this skill has no stage inputs of its own and is loaded alongside whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

- **Inputs:** the planned stage range, role and risk tier; budget decisions never remove grounding steps.
- **BACKFILL:** a long range (e.g. INTAKE → PLAN over many documents) is decomposed into per-stage runs with checkpoints rather than one oversized context.
- **Repo roles:** none required.

## Procedure
1. Pick a model tier per role from [model-tiering.md](reference/model-tiering.md).
2. Allocate context per [context-budget.md](reference/context-budget.md).
3. Load reference files on demand, not up front; delegate verbose exploration to subagents.
4. At the decomposition threshold, checkpoint and split ([context-compaction.md](reference/context-compaction.md)).
5. Apply [caching-strategy.md](reference/caching-strategy.md) for stable prefixes.
6. On budget exhaustion follow [budget-escalation.md](reference/budget-escalation.md) — escalate;
   never skip a gate or an evidence step to save tokens.

## Outputs
- `DECISION` entry: model per role and the budget policy values in effect.
- `RISK` entry when a budget constraint would force a weaker model on HIGH/CRITICAL work.

## Enforcement
Guideline only — no enforcement point yet. Caps in [cost-controls.md](reference/cost-controls.md)
become enforced once the orchestrator reads them.

## References
- [model-tiering.md](reference/model-tiering.md)
- [context-budget.md](reference/context-budget.md)
- [cost-controls.md](reference/cost-controls.md)
- [context-compaction.md](reference/context-compaction.md)
- [caching-strategy.md](reference/caching-strategy.md)
- [budget-escalation.md](reference/budget-escalation.md)
- [../../roles/reference/reviewer-diversity.md](../../roles/reference/reviewer-diversity.md)
