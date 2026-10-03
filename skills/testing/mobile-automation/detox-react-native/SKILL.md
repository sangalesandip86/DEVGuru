---
name: detox-react-native
description: React Native testing expertise — component tests with React Native Testing Library and Jest, and gray-box E2E with Detox using testID/accessibilityLabel matchers, Detox's automatic synchronization and waitFor().withTimeout() instead of sleeps, launch-arg based configuration and screen robots. Use when stack.json reports ui_paradigm react-native.
metadata:
  group: testing
  phase: progressive
  binding: false
  plan-ref: "§4.13 step 5 (tier matrix)"
  stage: TEST
  inputs: [test-design]
  outputs: [test-suite]
  repo_roles: [app]
---

# Detox and React Native Testing

## Purpose
Deterministic RN tests at two tiers:
- **component tests:** Jest plus `@testing-library/react-native`, hermetic;
- **E2E tests:** Detox, gray-box, on a simulator or emulator.

Detox synchronizes with the app's main thread, network and animations, so **sleeps are never needed**.
When a test seems to need one, the cause is an app-side idle problem to fix, not a timer to add.

## When this applies
- `stack.json.ui_paradigm` contains `react-native`, or `e2e_driver` contains `detox`.

## Preflight
Run the standard preflight first: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and
[`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve the `app` repo with `package.json` (and `ios/`, `android/`). If there's an Expo or bare-workflow
   ambiguity, read it from the manifest; don't guess.
2. **Frozen design** at the current `ac_hash`: SATISFIED. If it's missing, offer BACKFILL DESIGN via qa-derive or
   characterization mode (ADR 0004 §3: `describe('[characterization] …')`, an ASSUMPTION recorded, never AC
   verification). If stale, BLOCK.
3. **Detox configured?**
   - `.detoxrc*` and a build configuration per platform must exist for E2E scenarios.
   - If they don't, that's Mode C for the E2E tier, as its own story. Native build and CI changes are tier-gated, and CI is a control file.
4. **Discovery fresh?** Reuse the robots and builders listed in `test-assets.json`.

## Procedure
1. **Component tests** (RNTL):
   - Query with `getByRole('button', { name: 'Transfer' })` or `getByLabelText`, then `getByTestId` as the fallback.
   - Use `await findBy…` for async UI.
   - Mock network with MSW (`msw/native`) or injected API clients. Unhandled requests are errors.
   - Fake timers (`jest.useFakeTimers()`) for debounce and countdowns.
2. **E2E matchers** (Detox): `by.id('transfer-submit')` on `testID`, or `by.label('Transfer')` on `accessibilityLabel`.
   - Avoid `by.text` for buttons, because copy changes and locales break it.
   - Missing `testID`? Write a `testability_requests` entry for developer. Never edit app source.
3. **Synchronization:**
   - Rely on automatic sync, and use `await waitFor(element(by.id('receipt'))).toBeVisible().withTimeout(10000)` for
     long backend operations. **No `setTimeout` or `sleep`.**
   - If sync never idles (polling, websockets, looping animations), configure
     `device.setURLBlacklist([...])`, disable looping animations in test builds through a launch arg, or use
     `device.disableSynchronization()` *scoped* around the specific step, re-enabled right after, with
     the reason written down.
4. **App state and configuration** come from launch args, not UI setup:
   ```js
   await device.launchApp({ newInstance: true, launchArgs: { mockServer: 'http://localhost:9091', fixedNow: '2024-01-01T00:00:00Z' } })
   ```
   Credentials are environment variable names from `required-secrets.yaml`, read in the Detox config. Never put literals in tests.
5. **Robots** encapsulate matchers and actions (`transferRobot.enterAmount('100.00')`). Specs read as journeys,
   tagged `[ST-n/SC-n]`.
6. **Data.** Seed through the API or the mock server with run-namespaced IDs. Teardown happens in `afterAll` and is
   verified ([test-data-management](../../test-maintenance/test-data-management/SKILL.md)).
7. **Run:** `detox build -c ios.sim.release && detox test -c ios.sim.release --record-logs failing --artifacts-location artifacts/`.
   Use JUnit output (`jest-junit`) for the evidence pipeline.

## Outputs
Tests, robots and builders (`REPO_WRITE`). Results are FACT via hooks; CI passing is VERIFIED; the binding is REVIEWED.

## Enforcement
- [no_fixed_sleep_check.py](../../../enforcement/ci-checks/test-integrity/no_fixed_sleep_check.py) (the `js-settimeout` rule).
- [test_integrity_guard.py](../../../enforcement/ci-checks/test-integrity/test_integrity_guard.py), which catches loosened `withTimeout` values and skips.
- Matcher preference is guideline only.

## References
- [suite-authoring](../../test-implementation/suite-authoring/SKILL.md), [determinism-controls](../../test-implementation/suite-authoring/reference/determinism-controls.md)
- [appium-expert](../appium-expert/SKILL.md) (for black-box cross-platform needs), [device-matrix](../device-matrix/SKILL.md)
