---
name: test-strategy
description: Produce a risk-proportionate test strategy -- levels, environments, gates. Use when planning verification for a feature or HIGH change.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8"
  stage: DESIGN
  inputs: [ready-story, change-set]
  outputs: []
  repo_roles: [app, planning]
---

# Test Strategy


## Purpose
Decide *what* must be verified and *at which level* before anyone writes tests, scaled to the
Change Set's risk tier (plan §5.4) — a docs change and a payment migration do not get the same strategy.

## When this applies
- Change Set enters `PLANNED` and risk tier is MEDIUM or above.
- The repo has no test strategy recorded, or the change introduces a new boundary
  (new service, new external integration, new data store).
- qa-derive needs a frame for deriving test cases from acceptance criteria.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, planning]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`.
2. **Inputs** `[ready-story, change-set]`. Each resolves to one of:
   - SATISFIED;
   - ADOPT: it exists outside the platform, so import it as DRAFT with its source trust level;
   - BACKFILL: propose the smallest upstream run that produces it;
   - ASK: one batched QUESTION, never empty-handed;
   - BLOCK: a gate failed on existing evidence.
3. **Risk tier and story.** The Change Set's computed tier and the READY story's AC must resolve. If the story is not READY, BACKFILL PLAN (refinement): never write a strategy against an unrefined request. Read `stack.json` ([test-repo-discovery](../../test-architecture/test-repo-discovery/SKILL.md)) to see which tiers and frameworks exist.

Never proceed on a missing input silently.

## Procedure
1. Read the requirement, acceptance criteria, risk tier, and snapshot. Cite each as a source.
2. Inventory existing verification: test frameworks present, CI jobs, coverage on the paths
   in scope (run the coverage tool if available — the hook records the output as FACT).
3. Map each acceptance criterion to the **lowest test level that can prove it**:
   unit → component/integration → contract → end-to-end → manual/exploratory.
   E2E is for critical journeys only ([test-pyramid-advisor](../test-pyramid-advisor/SKILL.md)). The scenario-level
   design (techniques, partitions, expected outcomes) belongs to qa-derive in
   [test-case-design](../../test-design/test-case-design/SKILL.md). The strategy sets levels and gates; it does not
   write scenarios.
4. Add tier-driven obligations:

   | Tier | Minimum verification |
   |---|---|
   | LOW | Existing suite green; docs/link check for docs changes |
   | MEDIUM | New/changed behavior has unit or integration tests; changed-code coverage reported; new tests pass the red/green check and the new-test flake gate; diff-scoped mutation score meets the DoD threshold |
   | HIGH | + contract tests for every changed interface; security-testing scans; negative-path tests |
   | CRITICAL | + migration rehearsal on a production-like snapshot, rollback test, staged rollout checks, performance baseline comparison |

5. Name environments and data needs. Data generation is handled by [test-data-synthesis](../../test-data/test-data-synthesis/SKILL.md);
   environment seeding and teardown by [test-data-management](../../test-maintenance/test-data-management/SKILL.md).
   Say which runs need shared staging, because those are **CI-only**.
5a. If the repo has no framework for a needed tier, record a **Mode C** follow-up `TEST_AUTOMATION`
   story ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). Never fold a framework setup into the feature story.
6. List what will **not** be tested and why, each as an `ASSUMPTION` with impact and expiry,
   or a `QUESTION` if the gap is material.
7. Emit the strategy as a `PROPOSAL` in the handoff.

## Outputs
- `PROPOSAL`: the strategy (criterion → level → owner → gate).
- `ASSUMPTION` / `QUESTION` for each deliberate gap.
- `RISK` for untestable criteria.
- Lifecycle: the strategy can reach `REVIEWED` (by code-reviewer or architect). It is never
  `VERIFIED` — only executed checks are.

## Enforcement
**Guideline only** — no enforcement point yet.

Guideline only — no enforcement point yet. Tier gates themselves are enforced by risk-tiering
and the approval matrix (`../../../change-management/`).

## References
- [`../test-pyramid-advisor/SKILL.md`](../test-pyramid-advisor/SKILL.md)
- [`../../../grounding/evidence-gate/SKILL.md`](../../../grounding/evidence-gate/SKILL.md)
- [`../../../change-management/risk-tiering/`](../../../change-management/risk-tiering/)
- [`../../../governance/autonomy-gating/`](../../../governance/autonomy-gating/) — weak verification keeps a repo in assist mode
