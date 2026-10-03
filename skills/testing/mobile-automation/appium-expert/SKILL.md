---
name: appium-expert
description: Writes and stabilizes cross-platform mobile UI tests with Appium 2 (UiAutomator2 and XCUITest drivers) for native, hybrid, and mobile-web apps. Use when one test suite must cover both iOS and Android, or the repo already uses Appium/WebdriverIO.
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

# Appium Expert

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Cross-platform mobile E2E that is stable enough to gate on. Platform-native frameworks are faster
and less flaky; Appium earns its place when one suite must span both platforms or the team is
black-box testing a binary it doesn't build.

## When this applies
- Repo has `appium` / `webdriverio` with `appium:` capabilities, or `Appium-Python-Client` / `java-client`.
- The test strategy calls for E2E on both mobile platforms.

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Driver and devices.** Appium config and capabilities are present. Devices are selected through [device-matrix](../device-matrix/SKILL.md). For Flutter or RN, prefer [flutter-testing](../flutter-testing/SKILL.md) or [detox-react-native](../detox-react-native/SKILL.md), unless black-box cross-app testing is required.

Never proceed on a missing input silently.

## Procedure
1. **Appium 2 architecture**: drivers are installed separately and pinned
   (`appium driver install uiautomator2@<ver>`, `xcuitest@<ver>`). Record server and driver versions
   in the run evidence.
2. **Capabilities** use the `appium:` vendor prefix:
   ```json
   {
     "platformName": "Android",
     "appium:automationName": "UiAutomator2",
     "appium:app": "/builds/app-debug.apk",
     "appium:noReset": false,
     "appium:newCommandTimeout": 120
   }
   ```
3. **Locators**: accessibility id first (`~checkout-button` → `contentDescription` on Android,
   `accessibilityIdentifier` on iOS). Then platform-native selectors (`-android uiautomator`,
   `-ios predicate string`, `-ios class chain`). XPath is a last resort — slow on large trees, brittle.
   Ask developers to add accessibility ids; that is the mobile equivalent of `data-testid`.
4. **Waits**: explicit waits on element state; no sleeps. Disable device animations
   (`settings put global *_animation_scale 0` on Android emulators).
5. **State**: reset app state per test (`noReset: false` or a deep-link to a known state). Seed
   backend data through the API.
6. **Contexts**: for hybrid apps switch with `driver.switchContext('WEBVIEW_<pkg>')` and back;
   assert you are in the expected context before acting.
7. **Execution**: emulators/simulators for the gating suite; real devices (device farm) per
   [`../device-matrix/SKILL.md`](../device-matrix/SKILL.md), usually nightly.
8. On failure capture a screenshot, page source XML, device logs (`logcat` / `syslog`), and the Appium
   server log.

## Outputs
- Tests (`REPO_WRITE`). Device-run pass/fail from CI → `VERIFIED`. Diagnoses → `REVIEWED`.

## Enforcement
Pass/fail is machine evidence from CI. Practices are guideline only.

## References
- [`../ios-xcuitest/SKILL.md`](../ios-xcuitest/SKILL.md), [`../android-espresso/SKILL.md`](../android-espresso/SKILL.md)
- [`../../web-ui-automation/playwright-expert/reference/flaky-test-patterns.md`](../../web-ui-automation/playwright-expert/reference/flaky-test-patterns.md)
