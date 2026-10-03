---
name: self-healing-locators
description: Repairs broken UI test locators after UI changes by proposing replacement locators with evidence, without ever silently changing what a test asserts. Use when UI tests fail with element-not-found after a front-end change.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8"
  stage: TEST
  inputs: [test-suite]
  outputs: [test-suite]
  repo_roles: [app, tests]
---

# Self-Healing Locators

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Cut the maintenance cost of UI suites while preserving their meaning. "Self-healing" that quietly
re-targets a locator at whatever element now exists can turn a real regression into a green test —
so every heal is a reviewed proposal, never a silent runtime substitution.

## When this applies
- Failure is element-not-found / strict-mode violation after a UI change, and the user journey still exists.

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Evidence of a locator break.** You need the last passing and the current failing trace or DOM snapshot of the same journey. Without both, treat it as a product failure until shown otherwise.

Never proceed on a missing input silently.

## Procedure
1. **Confirm it's a locator break, not a product break.** Compare the failing trace/DOM snapshot with the last
   passing one. If the element is gone because the feature is broken or removed, stop — that is a real failure.
2. **Find candidates** in the new DOM using the same priority as
   [`selectors-best-practices.md`](../../web-ui-automation/playwright-expert/reference/selectors-best-practices.md):
   same role + accessible name → same label → same test id → similar text → structural position.
3. **Score** each candidate on how many attributes of the old element it preserves (role, name, test id,
   text, container). Accept automatically only a unique candidate that matches role *and* accessible name or test id.
4. **Propose, don't apply silently**: patch the locator on the branch, with a handoff entry containing old
   locator, new locator, matched attributes, and DOM evidence (`repo@sha:path` + content hash).
5. **Never edit assertions** as part of a heal. If expected text or values changed, that's a requirement
   question for qa-derive, not a locator fix.
6. Runtime healing libraries (Healenium etc.) may run only in **report mode**. Their suggestions feed step 4.
   A library that rewrites locators at runtime and keeps going hides a regression inside a green run.
   Self-heal-and-continue mode is forbidden in CI.
7. Repeated heals in the same area → ask developers for stable test ids (`RISK` to the developer role).

## Outputs
- Locator patch → `PROPOSAL`; reviewer acceptance → `REVIEWED`; re-run green in CI → `VERIFIED`.

## Enforcement
- A heal is never auto-committed by a runtime library or a bot. It is a PROPOSAL on the branch, and qa-diagnose or code-reviewer
  must record REVIEWED before merge.
- A heal that touches an assertion, an expectation or a skip marker is caught by
  [test_integrity_guard.py](../../../enforcement/ci-checks/test-integrity/test_integrity_guard.py)
  (`EXPECTATION_CHANGED`, `ASSERTION_REMOVED`, `SKIP_ADDED`). Without an AC-hash change, it blocks the PR.
- qa-derive's implementation-path denial keeps expected behaviour independent of the healed implementation.
- Candidate scoring is guideline only.

## References
- [`../../web-ui-automation/playwright-expert/SKILL.md`](../../web-ui-automation/playwright-expert/SKILL.md)
- [`../../../roles/qa-diagnose/`](../../../roles/qa-diagnose/)
