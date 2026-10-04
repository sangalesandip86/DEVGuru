---
name: flaky-test-intelligence
description: Detect, rank, and quarantine flaky tests from JUnit XML results. Use when CI fails intermittently or before autonomy-gating a suite.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.8, §4.11"
  stage: TEST
  inputs: [test-suite]
  outputs: [review-verdict]
  repo_roles: [app, tests]
---

# Flaky Test Intelligence


## Purpose
Flaky tests make `VERIFIED` meaningless: a green run might be luck, a red run might be noise. This skill
measures flakiness so autonomy-gating (plan §4.11) and self-improvement's positive-signal gate can trust
— or discount — a suite.

## When this applies
- A CI job failed and passed on retry with no code change.
- Computing a repository's verification strength.
- A test is proposed for quarantine.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Repeated-run evidence.** At least two JUnit reports of the same commit, from CI retries or the new-test flake gate. A single run cannot establish flakiness.

Never proceed on a missing input silently.

## Procedure
1. **Collect runs** of the same commit: CI retries, a nightly repeat job, or a local repeat
   (`pytest --count=20` with pytest-repeat, `--repeat-each` in Playwright, `-Dsurefire.rerunFailingTestsCount`).
   Each run must produce JUnit XML.
2. **Detect**:
   ```bash
   python skills/testing/test-maintenance/flaky-test-intelligence/scripts/flaky-detector.py --dir reports/ --min-runs 2
   ```
   Output is JSON: per-test runs, passes, failures, in-run retries, `flake_rate`, plus `suite_flake_rate`
   and tests that failed consistently (real failures, not flakes). Exit 1 means flaky tests were found.
3. **Separate flake from regression**: a test failing in *every* run on the new commit and passing on the
   base commit is a regression, not a flake — never quarantine it.
4. **Diagnose** each flaky test with
   [`flaky-test-patterns.md`](../../web-ui-automation/playwright-expert/reference/flaky-test-patterns.md)
   (UI) or the same categories for backend tests (shared state, time, ordering, concurrency, external deps).
5. **Quarantine** only with owner + expiry, recorded as an `ASSUMPTION` with that expiry; quarantined tests
   run in a non-gating job and are excluded from changed-code coverage.
6. **Trend**: track `suite_flake_rate` per week. A rising rate lowers the repo's verification strength.

## Outputs
- Detector output → `FACT` (written by the PostToolUse hook from command output).
- Root-cause diagnosis → `INFERENCE` citing those entries; fix review → `REVIEWED`.
- The fix itself is `VERIFIED` only by a clean repeat run in CI.

## Enforcement
**Guideline only** — no enforcement point yet.

Guideline only — no enforcement point yet. Quarantine policy should become a CI check that fails on
`@quarantine` tags past their expiry.

## References
- [`scripts/flaky-detector.py`](scripts/flaky-detector.py) (tests: `scripts/test_flaky_detector.py`)
- [`../../../governance/autonomy-gating/reference/verification-strength.md`](../../../governance/autonomy-gating/reference/verification-strength.md)
- [`../../../self-improvement/failure-capture/`](../../../self-improvement/failure-capture/)
