---
name: selenium-expert
description: Write Selenium WebDriver tests with explicit waits, page objects, and Grid execution. Use when the repo uses Selenium or needs Grid.
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

# Selenium Expert


## Purpose
Keep Selenium suites reliable and maintainable; recommend migration only with evidence.

## When this applies
- Repo depends on `selenium-java`, `selenium` (PyPI), `Selenium.WebDriver`, or `selenium-webdriver` (npm).
- The cross-browser matrix includes browsers or real-device clouds served via Grid.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Runner present.** Selenium/WebDriver bindings are in the manifest and a grid or driver config exists. If the repo also has Playwright, follow the golden sample's driver; don't introduce a second one.

Never proceed on a missing input silently.

## Procedure
1. **Selenium 4+ only.** Use Selenium Manager for drivers; no checked-in driver binaries.
2. **Waits**: never mix implicit and explicit waits — the combined timeouts are unpredictable. Keep the
   implicit wait at 0 and use explicit waits:
   ```java
   new WebDriverWait(driver, Duration.ofSeconds(10))
       .until(ExpectedConditions.elementToBeClickable(By.cssSelector("[data-testid=submit]")))
       .click();
   ```
   `Thread.sleep` / `time.sleep` is a review blocker.
3. **Locators**: follow [`selectors-best-practices.md`](../playwright-expert/reference/selectors-best-practices.md).
   In Selenium the practical ranking is `data-testid` → id → name → accessible CSS → XPath by text.
4. **Page Object Model**: pages expose intent (`checkout.placeOrder()`), not raw elements. Assertions
   live in tests, not page objects.
5. **Driver lifecycle**: one driver per test (or per class with a full state reset); always `quit()`
   in teardown. Parallelize through the test runner plus Grid — never share a driver across threads.
6. **Grid**: Selenium Grid 4 (`selenium/standalone-*` Docker images locally; hub/node or Kubernetes in CI).
   Record the browser version of each run in the evidence.
7. **Diagnostics**: on failure, capture a screenshot, page source, and browser console logs and attach them.
8. **Migration advice** (e.g. Selenium → Playwright) is a `PROPOSAL` backed by measured flake rate and
   runtime, never a default recommendation.

## Outputs
- Tests (`REPO_WRITE`). CI pass/fail → server-set `VERIFIED`. Reviews and diagnoses → `REVIEWED`.

## Enforcement
**Guideline only** — no enforcement point yet.

Pass/fail is machine evidence from CI. Style rules are guideline only.

## References
- [`../playwright-expert/reference/flaky-test-patterns.md`](../playwright-expert/reference/flaky-test-patterns.md)
- [`../headless-vs-headed/SKILL.md`](../headless-vs-headed/SKILL.md)
