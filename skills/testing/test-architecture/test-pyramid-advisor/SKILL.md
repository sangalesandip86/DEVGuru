---
name: test-pyramid-advisor
description: Analyzes a repository's test distribution across unit, integration, contract, and end-to-end levels and recommends rebalancing. Use when a suite is slow, flaky, E2E-heavy, or when proposing where new tests should live.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8"
  stage: ARCHITECTURE
  inputs: [test-suite]
  outputs: [review-verdict]
  repo_roles: [app, tests]
---

# Test Pyramid Advisor

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Keep verification fast and trustworthy by placing each test at the cheapest level that still
proves the behavior. An inverted pyramid (many E2E, few unit) makes `VERIFIED` slow and flaky,
which erodes autonomy-gating.

## When this applies
- CI wall-clock for the suite exceeds the team's budget, or flake rate is rising.
- A Change Set proposes new E2E tests for logic that could be unit-tested.
- test-strategy asks for a level recommendation.

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`.
2. **Inputs** `[test-suite]`. Each resolves to one of:
   - SATISFIED;
   - ADOPT: it exists outside the platform, so import it as DRAFT with its source trust level;
   - BACKFILL: propose the smallest upstream run that produces it;
   - ASK: one batched QUESTION, never empty-handed;
   - BLOCK: a gate failed on existing evidence.
3. **Evidence.** This needs `stack.json` and `test-assets.json` ([test-repo-discovery](../../test-architecture/test-repo-discovery/SKILL.md)), plus CI timing and flaky-detector output. Without timing data, the shape diagnosis is an INFERENCE from counts only; say so.

Never proceed on a missing input silently.

## Procedure
1. Count tests per level. Use directory and naming heuristics, then confirm by reading a sample:
   - unit: no I/O, no network, mocks at the boundary;
   - integration: real DB/queue via containers (Testcontainers), in-process service;
   - contract: Pact / schema validation;
   - E2E: browser/device/full deployed stack.
2. Collect duration and flake data per level (CI timing reports;
   `../../test-maintenance/flaky-test-intelligence/scripts/flaky-detector.py`).
3. Compare against a target shape. Defaults, tuned per repo:
   unit ≥ 70%, integration 15–25%, contract per interface, E2E ≤ 10% and limited to critical user journeys.
4. For each E2E test, ask: *what single behavior does it prove, and could a lower level prove it?*
   Recommend push-down candidates with the replacement test sketched.
5. Flag gaps the other way too: integration seams with only mocked tests (a mock that never
   meets reality is an ASSUMPTION about the dependency).
6. **Contract is its own tier**, not a flavour of integration. Every interface the Change Set changes
   needs a contract test (Pact or schema validation, [api-contract-testing](../../api-contract-testing/)),
   and hermetic mocks must be validated against the same contract. That stops mocked unit tests from passing
   against an API that no longer exists.
7. **BDD is a notation, not a tier.** A `.feature` scenario binds to the lowest tier that proves it:
   a component harness on PRs, and a live driver only for critical journeys.
8. **E2E covers critical journeys only.** These are the revenue, safety or compliance paths named in the strategy.
   Each E2E journey uses a per-journey assertion strategy: persistence and reload checks only where the AC is
   about persistence. Everything else is pushed down.

## Outputs
- `FACT`: counts and durations (from command output, recorded by hooks).
- `INFERENCE`: shape diagnosis, citing those FACT entries.
- `PROPOSAL`: push-down / pull-up list with estimated CI time saved.
- Lifecycle: `REVIEWED` at most — this is a judgment.

## Enforcement
Guideline only — no enforcement point yet.

## References
- [`../test-strategy/SKILL.md`](../test-strategy/SKILL.md)
- [`../../web-ui-automation/playwright-expert/reference/flaky-test-patterns.md`](../../web-ui-automation/playwright-expert/reference/flaky-test-patterns.md)
