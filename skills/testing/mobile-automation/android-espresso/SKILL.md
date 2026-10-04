---
name: android-espresso
description: Write native Android UI tests with Espresso and Compose UI Test. Use for Android apps when stack.json reports android.
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

# Android Espresso / Compose UI Test


## Purpose
Fast, synchronized Android UI verification. Espresso waits for the main thread and registered idling
resources, removing most timing flakes by construction.

## When this applies
- `androidTest` source set exists, or the app uses Jetpack Compose / Views with UI behavior changes.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Target present.** An `androidTest` source set with Espresso or Compose test dependencies exists (`stack.json.e2e_driver` contains `espresso`). Idling resources are registered for async work.

Never proceed on a missing input silently.

## Procedure
1. **Views (Espresso)**:
   ```kotlin
   onView(withId(R.id.pay_button)).perform(click())
   onView(withText(R.string.order_confirmed)).check(matches(isDisplayed()))
   ```
   **Compose**:
   ```kotlin
   composeTestRule.onNodeWithTag("checkout.pay").performClick()
   composeTestRule.onNodeWithText("Order confirmed").assertIsDisplayed()
   ```
   Use `Modifier.testTag` for test ids.
2. **Synchronization**: register `IdlingResource`s (or `CountingIdlingResource`) for background work
   Espresso can't see — custom executors, coroutines on non-main dispatchers, network. For Compose use
   `waitUntil { ... }` with a timeout. `Thread.sleep` is a review blocker.
3. **Isolation**: enable Android Test Orchestrator with `clearPackageData` so every test starts clean:
   ```kotlin
   testOptions {
     execution = "ANDROIDX_TEST_ORCHESTRATOR"
     animationsDisabled = true
   }
   defaultConfig { testInstrumentationRunnerArguments["clearPackageData"] = "true" }
   ```
4. **Devices in CI**: Gradle Managed Devices (`./gradlew pixel6api34DebugAndroidTest`) for reproducible
   emulators; real devices per [`../device-matrix/SKILL.md`](../device-matrix/SKILL.md).
5. **Network**: point the app at MockWebServer or a stub backend via a test build flavor or DI override.
6. Prefer Robolectric for logic-heavy UI tests that don't need a device — push them down the pyramid.

## Outputs
- Tests (`REPO_WRITE`). JUnit XML from `build/outputs/androidTest-results` → `VERIFIED` via CI. Diagnoses → `REVIEWED`.

## Enforcement
**Guideline only** — no enforcement point yet.

Pass/fail is machine evidence from CI. Practices are guideline only.

## References
- [`../appium-expert/SKILL.md`](../appium-expert/SKILL.md)
- [`../../test-architecture/test-pyramid-advisor/SKILL.md`](../../test-architecture/test-pyramid-advisor/SKILL.md)
