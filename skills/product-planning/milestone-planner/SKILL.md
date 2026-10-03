---
name: milestone-planner
description: Defines outcome-based milestones (plans/milestones/MS-n.yaml) with measurable success and exit criteria, groups epics/stories into them many-to-many, maps them to releases, and produces an advisory, sourced prioritization PROPOSAL for a human to decide. Use when sequencing work across epics toward a release or business checkpoint.
metadata:
  group: product-planning
  phase: 2
  binding: false
  plan-ref: "§4.12"
  stage: PLAN
  inputs: [epic]
  outputs: [milestone]
  repo_roles: [planning]
---

# Milestone Planner

## Purpose
A milestone is an **outcome checkpoint on the time axis**. It is the point where a user or the
business can do or observe something new, checked by exit criteria. It is **not** a level of
the scope tree, and **not** a technical layer. It groups epics and stories from anywhere in
the tree, many-to-many.

This skill also produces a **prioritization PROPOSAL**. Ordering and commitment are human
decisions. The platform does not plan iterations, capacity or velocity.

## When this applies
- Several epics or stories need sequencing toward a release or a business date.
- A stakeholder asks "what will be usable by when?".
- An existing milestone's scope changes. Edit the file through a PR so the change is reviewable.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Stage PLAN.

- **Inputs:** epics and stories.
- **ADOPT:** existing tracker milestones are imported as DRAFT; their scope is re-validated against outcomes, not copied.
- **Repo roles:** `planning`.

## Procedure
1. **State the outcome first.** Write `business_outcome` as something a named user can do or observe. Check it against the anti-examples in [reference/milestone-schema.md](reference/milestone-schema.md). If the name reads like "Backend done", start again.
2. **Make success measurable.** `success_criteria` have numbers and a population, sourced from the requirement or epic metrics.
3. **Pick the stories, not the layers.** Include the smallest set of stories (and SPIKEs) that achieves the outcome end to end. Usually that is the walking skeleton plus its most important failure paths.
4. **Write exit criteria**, each with a check kind:
   - `STRUCTURAL`: derivable from gates. "ST-1 and ST-2 are DONE", "no OPEN blocking QUESTION on any member story".
   - `JUDGMENT`: a named role. "architect REVIEWED the end-to-end design".
   - `APPROVAL`: a `human:` approver. "Pilot PMs confirm usability".
5. **Write entry criteria.** What must be true before work toward it starts (for example "spike ST-3 answered").
6. **Map dependencies** across member stories with [dependency-mapper](../dependency-mapper/SKILL.md). Any UNRESOLVED dependency becomes a milestone risk.
7. **Propose an order** with [reference/prioritization-guide.md](reference/prioritization-guide.md). The output is a PROPOSAL entry with sourced inputs. A human decides, and the decision is recorded as a DECISION entry by that human.
8. **Map to a release** (`target_release`, optional `target_date`). Dates are commitments made by humans. Never present a date as a FACT unless a human committed to it, and cite that commitment.

## Outputs
- `plans/milestones/MS-n.yaml` ([`milestone.schema.json`](../schemas/milestone.schema.json)) and back-references in member stories' `milestone_ids` where helpful.
- A PROPOSAL ledger entry with the prioritization and its inputs; RISK entries for unresolved dependencies.

## Enforcement
- **Schema, membership references and exit-criterion shape:** `plan_lint.py`, which also **warns on layer-shaped milestone names**.
- **Exit-criteria evaluation** is a Phase 2 milestone gate, built as part of the `work_planning` module. Until then, exit criteria are checked by a human at milestone review, using the per-story gate results.
- **Prioritization is advisory by construction:** the planner has no tool to set order in the tracker, and the human owns the DECISION.

## References
- [reference/milestone-schema.md](reference/milestone-schema.md) · [reference/prioritization-guide.md](reference/prioritization-guide.md)
- [epic-decomposer](../epic-decomposer/SKILL.md) · [dependency-mapper](../dependency-mapper/SKILL.md)
- Release states come from forge and CI events: [change-management/change-set/reference/approval-matrix.md](../../change-management/change-set/reference/approval-matrix.md)
