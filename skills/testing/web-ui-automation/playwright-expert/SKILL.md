---
name: playwright-expert
description: Write and stabilize Playwright E2E tests with user-facing locators and web-first assertions. Use for Playwright test authoring or review.
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

# Playwright Expert


## Purpose
Produce Playwright tests that prove user-visible behavior and stay stable across runs.

## When this applies
- Repo contains `playwright.config.*` or a `@playwright/test` / `pytest-playwright` dependency.
- A Change Set touches a critical user journey that the test strategy assigns to E2E.
- A Playwright test is reported flaky.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Runner present.** `stack.json.e2e_driver` contains `playwright` and a `playwright.config.*` exists. The target environment is an ephemeral preview; shared staging is CI-only.

Never proceed on a missing input silently.

## Procedure
1. **Locate by user-facing semantics** — see [`reference/selectors-best-practices.md`](reference/selectors-best-practices.md).
   Priority: `getByRole` → `getByLabel` → `getByPlaceholder`/`getByText` → `getByTestId` → CSS (last resort, justify it).
2. **Assert with web-first assertions** that auto-retry: `await expect(locator).toHaveText(...)`,
   `toBeVisible()`, `toHaveURL()`. Never `expect(await locator.textContent())` or a fixed `waitForTimeout`.
3. **Isolate state**: each test gets a fresh `BrowserContext` (the default). Authenticate once via a
   setup project and `storageState`; seed data through the API, not the UI.
   ```ts
   // playwright.config.ts
   projects: [
     { name: 'setup', testMatch: /auth\.setup\.ts/ },
     { name: 'chromium', use: { ...devices['Desktop Chrome'], storageState: '.auth/user.json' },
       dependencies: ['setup'] },
   ],
   ```
4. **Control the network where the test is not about the network**: `page.route()` to stub third
   parties; never stub the system under test.
5. **Make failures diagnosable**: `trace: 'on-first-retry'`, `screenshot: 'only-on-failure'`,
   `video: 'retain-on-failure'`. Attach the trace path to the evidence.
6. **Retries are a diagnostic, not a fix**: `retries: 2` in CI is acceptable only if
   flaky-test-intelligence tracks every test that needed a retry. A pass-on-retry is a flake signal.
7. For flake triage follow [`reference/flaky-test-patterns.md`](reference/flaky-test-patterns.md).
8. **Expected outcomes come from the frozen test design**, never from reading the component. Each test
   carries its scenario and AC (`test('[ST-12/SC-1] [ST-12/AC-1] …')` or `test.info().annotations`), so
   `ac_coverage.py` and CI tag selection (`--grep`) can find it ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)).
9. **Time and network are controlled.** Use `page.clock.install({ time })` for time-dependent UI, and
   `use: { locale, timezoneId }` pinned in config. Use `page.route()` only for third parties; the real backend runs on an
   **ephemeral preview environment**. Runs against shared staging are **CI-only**.
10. **Waits are state-based only.** Use `expect(locator)` matchers, `waitForResponse`, `waitForURL` and `expect.poll`.
    `waitForTimeout` fails CI ([no_fixed_sleep_check.py](../../../enforcement/ci-checks/test-integrity/no_fixed_sleep_check.py)).
    Raising an `expect` `timeout` to make a test pass is flagged as `TIMEOUT_OR_TOLERANCE_LOOSENED`.

## Outputs
- Test files and config changes (`REPO_WRITE` on the Change Set branch).
- CI results → the server sets `VERIFIED` for the run. The agent never claims the suite passed on
  its own say-so; the hook-recorded command output is the FACT.
- Review comments and flake diagnoses → `REVIEWED`.

## Enforcement
**Guideline only** — no enforcement point yet.

Test pass/fail is machine evidence ingested from CI (plan §5.5, §5.10). Fixed waits fail
[no_fixed_sleep_check.py](../../../enforcement/ci-checks/test-integrity/no_fixed_sleep_check.py) (and the
`playwright/no-wait-for-timeout` lint rule). Skips, `.only`, loosened timeouts and changed expectations
are flagged by [test_integrity_guard.py](../../../enforcement/ci-checks/test-integrity/test_integrity_guard.py).
Locator ranking is guideline only.

## References
- [`reference/selectors-best-practices.md`](reference/selectors-best-practices.md)
- [`reference/flaky-test-patterns.md`](reference/flaky-test-patterns.md)
- [`../visual-regression/SKILL.md`](../visual-regression/SKILL.md)
- [`../../test-maintenance/flaky-test-intelligence/SKILL.md`](../../test-maintenance/flaky-test-intelligence/SKILL.md)
- [`../../../grounding/evidence-gate/SKILL.md`](../../../grounding/evidence-gate/SKILL.md)
