---
name: epic-decomposer
description: Breaks a large requirement into an epic (plans/epics/EPIC-n.yaml) and a set of vertically sliced stories, optionally grouped into features, using named slicing patterns (SPIDR and friends). Use when a requirement is too big for one or two stories or spans several outcomes, repos or teams.
metadata:
  group: product-planning
  phase: 2
  binding: false
  plan-ref: "§4.12"
  stage: PLAN
  inputs: [requirement, architecture-package]
  outputs: [epic, ready-story]
  repo_roles: [planning]
---

# Epic Decomposer

## Purpose
Turn one large requirement into an epic and a first set of stories. Each story should deliver
an observable increment on its own, and together they should cover the epic's scope with
nothing hidden in "and also…". The epic is a level of the **scope tree**. Time-based
grouping is the [milestone-planner](../milestone-planner/SKILL.md)'s job.

## When this applies
- The requirement would produce more than about three stories, or more than one `M`.
- It spans several repos, teams or contracts.
- Its outcome needs several independently releasable increments.

For a small requirement, go straight to [story-writer](../story-writer/SKILL.md).

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Stage PLAN; slices follow the architecture's service boundaries.

- **Inputs:** requirements plus the architecture package.
- **ADOPT:** existing epics from the tracker are imported as DRAFT and re-sliced only with human agreement.
- **BACKFILL:** no architecture package → propose `BACKFILL: ARCHITECTURE` (a LOW-tier single-service requirement may proceed on a recorded ASSUMPTION).
- **Repo roles:** `planning`.

## Procedure
1. **Anchor on the outcome.** Copy `business_outcome` and `success_metrics` from the requirement and source them. An epic without a measurable outcome is a bucket, not an epic.
2. **Draw the scope boundary.** Write `scope` and `out_of_scope` as one list each, then check them against the requirement's `out_of_scope` and `constraints`.
3. **Map the flow.** List the user or system journey end to end (trigger → steps → result). Features, when used, are the large chunks of this journey. Features are optional: use them only when the epic has more than about 8 stories.
4. **Slice vertically** with [reference/slicing-patterns.md](reference/slicing-patterns.md):
   - Start with the **walking skeleton**, the thinnest end-to-end path that delivers the core outcome for the simplest case.
   - Each further slice adds a path, a rule, a data variation or a quality.
5. **Isolate unknowns as SPIKEs.** For each "we don't know whether…", write a SPIKE with one question and a time-box, then make the dependent stories depend on it. Do not size stories you cannot understand yet.
6. **Write each story** with [story-writer](../story-writer/SKILL.md). Stories carry `epic_id` and optional `feature_id`.
7. **Check coverage.** Every `scope` line of the epic maps to at least one story, and no story falls outside the scope. Put the mapping in the PR description.
8. **Map dependencies** with [dependency-mapper](../dependency-mapper/SKILL.md). Ordering decisions belong to the milestone-planner and the human product owner.
9. **Open one PR** with the epic and its first stories. Stories can be refined independently afterwards.

## Outputs
- `plans/epics/EPIC-n.yaml` ([reference/epic-schema.md](reference/epic-schema.md), [`epic.schema.json`](../schemas/epic.schema.json)).
- `plans/stories/ST-*.yaml` slices, including SPIKEs for unknowns.
- REVIEWED on decomposition quality, recorded by the product-planner role. Ledger QUESTIONs for gaps.

## Enforcement
- **Schema and referential integrity** (feature belongs to epic, story → epic → requirement): `plan_lint.py`.
- **Slice quality** (vertical, independent, valuable) is a **guideline**, reviewed in the plan PR and through refinement. Layer-shaped stories show up as missing value statements and failing DoR items.

## References
- [reference/slicing-patterns.md](reference/slicing-patterns.md) · [reference/epic-schema.md](reference/epic-schema.md)
- [story-writer](../story-writer/SKILL.md) · [dependency-mapper](../dependency-mapper/SKILL.md) · [milestone-planner](../milestone-planner/SKILL.md)
- [grounding/evidence-gate](../../grounding/evidence-gate/SKILL.md)
