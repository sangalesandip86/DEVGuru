---
name: flutter-testing
description: Write Flutter tests -- unit/bloc, widget, golden, and integration_test. Use when stack.json reports ui_paradigm flutter.
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

# Flutter Testing

## Purpose
Write Flutter tests that are fast, deterministic and bound to stable finders. Expected outcomes
come from the frozen test design, never from reading the widget code
([suite-authoring](../../test-implementation/suite-authoring/SKILL.md)).

## When this applies
- `stack.json.ui_paradigm` contains `flutter` (`flutter_test`, `integration_test`, `bloc_test`, `mocktail`, `patrol`).

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve the `app` repo with `pubspec.yaml`. If there are several packages (melos or a mono-repo), pick the
   package whose `lib/` contains the target. If that's ambiguous, raise one QUESTION.
2. **Frozen design** at the current `ac_hash`: SATISFIED. If it's missing, offer BACKFILL DESIGN via qa-derive or
   **characterization mode** (ADR 0004 §3: tests tagged `characterization` via `tags: ['characterization']`
   with `dart_test.yaml` declaring the tag, an ASSUMPTION recorded, never AC verification). If stale, BLOCK.
3. **Tier available?**
   - No `integration_test` dependency for an E2E scenario: that's Mode C for that tier, as a separate story.
   - `flutter_test` is always present in a Flutter project.
4. **Discovery fresh?** Check robots, finders and builders in `test-assets.json`; reuse them.

## Procedure
1. **Unit and bloc tests.** Business logic, cubits and blocs.
   ```dart
   blocTest<TransferBloc, TransferState>(
     '[ST-12/SC-1] rejects amount above limit',
     build: () => TransferBloc(api: mockApi, clock: FixedClock(DateTime.utc(2024, 1, 1))),
     act: (b) => b.add(TransferSubmitted(aTransfer().withAmount(Money.eur('10000.01')).build())),
     expect: () => [const TransferState.rejected(TransferError.amountOutOfRange)],
     verify: (_) => verifyNever(() => mockApi.submit(any())),
   );
   ```
   Use `mocktail` with `registerFallbackValue` for custom types. Expect ordered state emissions exactly as
   the design states them.
2. **Widget tests** (component tier):
   - **Finders, in order of preference:**
     1. `find.bySemanticsLabel('Transfer')`, which also checks accessibility;
     2. `find.byKey(const Key('transfer-amount'))`;
     3. `find.widgetWithText(ElevatedButton, 'Transfer')`.

     Never use `find.byType` alone for an interactive element when several instances can exist.
   - **Missing Key or Semantics?** Write a `testability_requests` entry for developer. Never edit `lib/`.
   - **`pump` versus `pumpAndSettle`:**
     - `pumpAndSettle` waits until no frames are scheduled. It **hangs or times out with infinite animations**
       (`CircularProgressIndicator`, shimmer, repeating `AnimationController`).
     - In those cases use `pump()` plus `pump(const Duration(milliseconds: 300))` to advance *fake* time a known
       amount, or a `pumpUntilFound(finder)` helper that loops `pump(100ms)` with a deadline.
     - `tester.pump(duration)` advances fake time. It is **not** a sleep, and the sleep check allows it.
   - **Never `Future.delayed` or real timers in tests.** If code under test uses timers, wrap the test in
     `fakeAsync`, or use `tester.runAsync` *only* for genuinely real I/O (it's rare, and the reason must be stated).
   - Wrap with the repo's harness (golden sample), for example `pumpApp(widget, overrides: [...])`, to supply
     providers, `MaterialApp`, localizations, `MediaQuery` size and text scale.
3. **Golden tests.**
   - Use them for visual regressions, not for logic.
   - Pin fonts (`loadAppFonts` / `golden_toolkit`), devices and text scale.
   - Golden updates (`--update-goldens`) are snapshot updates: the integrity guard reviews any mass change.
4. **Integration tests.** `integration_test/` with `IntegrationTestWidgetsFlutterBinding.ensureInitialized()`, or Patrol
   for native dialogs and permissions.
   - Critical journeys only.
   - **Robots** encapsulate finders and actions (`TransferRobot(tester).enterAmount(...)`), and tests read as journeys.
   - Backend: an ephemeral preview environment or a local mock server. Credentials come from `--dart-define`
     names listed in `required-secrets.yaml`, never literal values.
5. **HTTP.** Inject clients. Stub with `http_mock_adapter` (Dio) or mocktail-mocked repositories. Validate stub
   payloads against the contract schema ([test-data-synthesis](../../test-data/test-data-synthesis/SKILL.md)).
6. **Run:**
   - `flutter test --test-randomize-ordering-seed=random --reporter=json` (or `--file-reporter junit:` through a converter);
   - integration: `flutter test integration_test -d <device>`.

## Outputs
Tests, robots and builders (`REPO_WRITE`). Run results are recorded as FACT by hooks; CI passing is VERIFIED; the binding is REVIEWED.

## Enforcement
**Guideline only** — no enforcement point yet.

- `Future.delayed` and `sleep(Duration)` in test paths fail [no_fixed_sleep_check.py](../../../enforcement/ci-checks/test-integrity/no_fixed_sleep_check.py).
- Weakening (skip, tolerance changes, golden mass updates) is caught by [test_integrity_guard.py](../../../enforcement/ci-checks/test-integrity/test_integrity_guard.py).
- Finder preference is guideline only.

## References
- [suite-authoring](../../test-implementation/suite-authoring/SKILL.md), [determinism-controls](../../test-implementation/suite-authoring/reference/determinism-controls.md)
- [device-matrix](../device-matrix/SKILL.md), [visual-regression](../../web-ui-automation/visual-regression/SKILL.md)
