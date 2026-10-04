---
name: visual-regression
description: Set up visual regression testing (Playwright screenshots, Percy, Chromatic). Use when a change affects UI rendering or CSS.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8"
  stage: TEST
  inputs: [test-design]
  outputs: [test-suite]
  repo_roles: [app, tests]
---

# Visual Regression


## Purpose
Catch unintended rendering changes that functional assertions miss, without burying reviewers in
pixel noise.

## When this applies
- The change touches CSS, design tokens, shared UI components, layout, or fonts.
- The repo has Storybook (prefer component-level snapshots) or an existing screenshot setup.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Baselines.** Baseline images exist for the target and were produced in the same pinned environment (OS, fonts, viewport). Missing baselines are created as their own reviewed change, never alongside a behaviour change.

Never proceed on a missing input silently.

## Procedure
1. **Pick the level**: component snapshots (Storybook + Chromatic, or Playwright component tests)
   over full pages. Full-page snapshots only for a few critical pages.
2. **Stabilize rendering before capture**:
   - pinned browser version and OS image — rendering differs across OSes, so generate baselines in
     the same container CI uses (e.g. the official Playwright Docker image);
   - bundled fonts, disabled animations, hidden caret;
   - masked dynamic regions: `await expect(page).toHaveScreenshot({ mask: [page.getByTestId('timestamp')] })`;
   - deterministic data and a frozen clock.
3. **Tolerance**: start at `maxDiffPixelRatio: 0.01`; tune per test from evidence. Never loosen it
   globally to make a diff pass.
4. **Baseline updates are approvals, not test fixes.** An agent may *propose* new baselines
   (`--update-snapshots`) on the branch with a side-by-side diff in the handoff, but a changed baseline
   asserts an intended visual change and needs human sign-off on the PR. CODEOWNERS on the snapshot
   directory is recommended. An agent never regenerates baselines to turn a red run green.
5. Report each diff as: component, viewport, diff %, and intended (cite the requirement) or unintended.

## Outputs
- Snapshot run with no diffs above tolerance → `VERIFIED` (from CI).
- Classifying a diff as intended/unintended → `REVIEWED`, with the diff image as evidence.
- Baseline update → `PROPOSAL` awaiting human approval.

## Enforcement
**Guideline only** — no enforcement point yet.

Diff detection is machine evidence. "Agents don't silently update baselines" is guideline only unless
snapshot directories are CODEOWNERS-protected — recommend that protection.

## References
- [`../playwright-expert/SKILL.md`](../playwright-expert/SKILL.md)
- [`../../../roles/reference/conflict-resolution.md`](../../../roles/reference/conflict-resolution.md)
