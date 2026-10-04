---
name: ios-xcuitest
description: Write native iOS UI tests with XCUITest and unit tests with XCTest/Swift Testing. Use for iOS apps in the same repo.
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

# iOS XCUITest


## Purpose
Fast, stable iOS UI verification using Apple's own framework.

## When this applies
- The repo contains an `.xcodeproj` / `.xcworkspace` / `Package.swift` with a UI test target.
- A Change Set changes iOS UI flows.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`. If there is no test framework for this tier, that is **Mode C, as its own `TEST_AUTOMATION` story** ([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)). It is never scaffolded inside a feature story.
2. **Frozen test design** (`plans/test-designs/ST-n.yaml` or `.feature` at the story's current `ac_hash`): SATISFIED. If it's missing, offer **BACKFILL** (DESIGN via qa-derive, [test-case-design](../../test-design/test-case-design/SKILL.md)) or **characterization mode** ([ADR 0004 §3](../../../../docs/adr/0004-workflow-stages-and-workspace.md)): tests tagged `characterization`, an ASSUMPTION "current behaviour is intended" recorded, and they never count as AC verification or VERIFIED. If the `ac_hash` is stale, BLOCK.
3. **Target present.** A `*UITests` target exists in the Xcode project (`stack.json.e2e_driver` contains `xcuitest`). Elements need an `accessibilityIdentifier`; missing ones become `testability_requests` to developer.

Never proceed on a missing input silently.

## Procedure
1. **Identifiers**: set `accessibilityIdentifier` on interactive views (SwiftUI: `.accessibilityIdentifier("checkout.pay")`).
   Query by identifier: `app.buttons["checkout.pay"]`.
2. **Waiting**: `XCTAssertTrue(element.waitForExistence(timeout: 5))`, or `XCTNSPredicateExpectation`
   for state changes. Never `sleep()`.
3. **Launch state**: control via `app.launchArguments` / `launchEnvironment`
   (e.g. `-uitesting`, a stub backend URL, animations disabled with `UIView.setAnimationsEnabled(false)`
   behind that flag). Reset state per test.
4. **System alerts**: handle with `addUIInterruptionMonitor`, or pre-grant permissions with
   `xcrun simctl privacy <device> grant <service> <bundle-id>`.
5. **Run in CI**:
   ```bash
   xcodebuild test -scheme App -testPlan UITests \
     -destination 'platform=iOS Simulator,name=iPhone 16,OS=latest' \
     -resultBundlePath build/UITests.xcresult -parallel-testing-enabled YES
   ```
   Convert `.xcresult` to JUnit (e.g. `xcresultparser` or `trainer`) so flaky-test-intelligence can read it.
6. Use **test plans** for configurations (locale, region, sanitizers) and
   `-retry-tests-on-failure` only with flake tracking enabled.
7. Keep logic tests in XCTest / Swift Testing; UI tests cover journeys only.

## Outputs
- Tests (`REPO_WRITE`). CI result bundle → `VERIFIED`. Diagnoses → `REVIEWED`.

## Enforcement
**Guideline only** — no enforcement point yet.

Pass/fail is machine evidence from CI. Practices are guideline only.

## References
- [`../device-matrix/SKILL.md`](../device-matrix/SKILL.md)
- [`../../test-maintenance/flaky-test-intelligence/SKILL.md`](../../test-maintenance/flaky-test-intelligence/SKILL.md)
