---
name: story-writer
description: Writes typed, vertically sliced stories (plans/stories/ST-n.yaml) with acceptance criteria that meet the AC standard (ST-n/AC-n IDs, Given/When/Then, kind, verification), predicted affected paths and size. Use when turning a requirement, epic or feature into implementable work, or when a fix needs a story.
metadata:
  group: product-planning
  phase: 1
  binding: false
  plan-ref: "§4.12"
  stage: PLAN
  inputs: [requirement]
  outputs: [ready-story]
  repo_roles: [planning, app]
---

# Story Writer

## Purpose
A story is the upstream contract for everything downstream:
- qa-derive designs tests from its acceptance criteria without seeing code;
- developer implements against it;
- the completion gate checks that every criterion was exercised.

This skill writes stories that can carry that weight. Each story is **typed**, each criterion
is **traceable**, and the story is **sliced vertically** so it delivers observable value on its own.

## When this applies
- Decomposing a requirement directly (small request) or an epic (via [epic-decomposer](../epic-decomposer/SKILL.md)).
- Writing a follow-up story after a SPIKE or a SPLIT (`follow_up_of`).
- Any change at MEDIUM tier or above. A LOW-tier `BUG_FIX` or `DOCUMENTATION` change may use an inline story in the PR body, which the DoR gate still checks.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Stage PLAN.

- **Inputs:** requirements (and the epic, if any).
- **ADOPT:** existing tracker stories are converted to `plans/stories/ST-*.yaml` as DRAFT, keeping the original AC text as a source citation.
- **BACKFILL:** no requirement → propose `BACKFILL: INTAKE`.
- **Repo roles:** `planning` (output), `app` (read-only, to check declared paths).

## Procedure
1. **Pick the type** from [reference/story-types.md](reference/story-types.md). When in doubt between two types, pick the one with the higher tier floor.
   - The type selects conditional DoR/DoD items and a tier floor. It never lowers the tier.
   - A misdeclared type (say `DOCUMENTATION` touching code) is caught at DONE by the scope check.
2. **Write the objective, persona and value statement.**
   - Persona is required for `FEATURE_STORY` and `UI_STORY`.
   - Value is required except for `SPIKE` and `DOCUMENTATION`.
   - Each must trace to the requirement's `source_refs`. Do not invent a persona.
3. **Slice vertically** ([epic-decomposer/reference/slicing-patterns.md](../epic-decomposer/reference/slicing-patterns.md)). A story that delivers only "the database part" is a layer, not a story. Exceptions are `TECHNICAL_STORY`, `REFACTOR` and `INFRASTRUCTURE`, which are typed precisely so their missing user value is explicit.
4. **Write scope and out-of-scope.** Out-of-scope is mandatory, even when empty, because it is what the scope check at DONE and the reviewers hold the diff against.
5. **Write the acceptance criteria to the standard** ([reference/acceptance-criteria-standard.md](reference/acceptance-criteria-standard.md)):
   - IDs are `ST-n/AC-n` and never reused.
   - Every criterion has Given/When/Then, a `kind` and a `verification`.
   - At least one `negative` criterion (except `SPIKE`/`DOCUMENTATION`).
   - Every `nfr` criterion states a number.
   - Type-specific tags: `accessibility` (UI), `reproduction` (BUG_FIX), `no-behaviour-change` (REFACTOR/TECHNICAL_STORY), `rollback`/`data-integrity` (DATA_MIGRATION).
6. **Fill `touches`** (`ui`, `api_contracts`, `data_migration`, `infra`) and `data_classification`. These drive conditional DoR/DoD items. If unsure, set the flag. Over-including costs a check; under-including skips a gate.
7. **Predict `affected_paths`** as concrete paths or directory globs.
   - They feed the path-based risk tier at READY.
   - At DONE, the completion gate holds the actual diff against them.
   - Use [change-management/dependency-discovery](../../change-management/dependency-discovery/SKILL.md) scanners to find the real modules involved rather than guessing.
8. **Size it** with [story-refinement/reference/sizing-guide.md](../story-refinement/reference/sizing-guide.md). Record `size` and `size_basis`. Anything `L` must be split before it can be READY.
9. **Add type-specific fields:**
   - `ux` (UI), `rollback_plan` (DATA_MIGRATION/INFRASTRUCTURE), `threat_statement` (SECURITY_STORY), `spike.question` + `spike.timebox_days` (SPIKE);
   - `security_considerations` whenever the data is CONFIDENTIAL/RESTRICTED.
10. **Self-check** with [definition-of-ready](../definition-of-ready/SKILL.md), then hand off to [story-refinement](../story-refinement/SKILL.md). Never write `status:`. READY is computed by the gate.

## Outputs
- `plans/stories/ST-n.yaml`, validating against [`story.schema.json`](../schemas/story.schema.json). Field guide: [reference/story-schema.md](reference/story-schema.md).
- Ledger entries: QUESTION/ASSUMPTION for every gap, and a PROPOSAL for the size estimate. Calibration against the actual diff happens later.
- A PR containing the story file(s). One PR per coherent set, so reviewers see the slicing.

## Enforcement
- **AC standard, schema and references:** `plan_lint.py` on every PR.
- **AC freeze after READY:** `plan_lint.py` diffs the canonical AC hash (`ac_hash.py`). A change reports `REQUIRES_REFINING`, and the earlier qa-derive and developer reviews stop counting (plan §5.6 row "AC are frozen once READY").
- **READY itself:** `readiness_gate.py` against [`policies/dor-policy.yaml`](../policies/dor-policy.yaml).
- **Story-type floors:** [`policies/story-types.yaml`](../policies/story-types.yaml), applied by the gates. This is a control file, so agents cannot weaken it.

## References
- [reference/story-schema.md](reference/story-schema.md) · [reference/acceptance-criteria-standard.md](reference/acceptance-criteria-standard.md) · [reference/story-types.md](reference/story-types.md)
- [grounding/evidence-gate](../../grounding/evidence-gate/SKILL.md) · [grounding/ambiguity-escalation](../../grounding/ambiguity-escalation/SKILL.md)
- [story-refinement](../story-refinement/SKILL.md) · [definition-of-ready](../definition-of-ready/SKILL.md)
- Worked example: [examples/plans/stories](../../../examples/plans/stories/)
