# Flaky Test Patterns


A flaky test both passes and fails against the same code. Detect with
[`flaky-detector.py`](../../../test-maintenance/flaky-test-intelligence/scripts/flaky-detector.py);
diagnose with the table below. Every diagnosis is an `INFERENCE` citing the trace or log entry it rests on.

| # | Pattern | Symptom | Root cause | Fix |
|---|---|---|---|---|
| 1 | Fixed sleeps | Fails on slow CI runners | `waitForTimeout(2000)` guesses timing | Web-first assertion on the condition actually awaited |
| 2 | Non-retrying assertion | Text "wrong" intermittently | Read once with `textContent()`, then asserted | `await expect(locator).toHaveText()` |
| 3 | Shared state | Passes alone, fails in the suite or in parallel | Shared user/account/DB rows; order dependence | Per-test data via API seeding; unique ids; serial mode only as a last resort |
| 4 | Navigation race | Click lands on the old page | Asserting before navigation completes | `await expect(page).toHaveURL(...)` before the next step; `waitForResponse` for XHR-driven UI |
| 5 | Animation / transition | Click intercepted, element "not stable" | CSS transitions | Disable animations in the test env (`reducedMotion: 'reduce'`, CSS override) |
| 6 | Third-party dependency | Fails when an external service is slow | Real network to analytics or a payment sandbox | `page.route()` stub; contract-test the integration separately |
| 7 | Time and timezone | Fails near midnight, month end, DST | `new Date()` in app or test | `page.clock.install()`; fixed `timezoneId` in config |
| 8 | Randomness | Fails 1 in N | Random data hitting validation edges | Seeded faker; print the seed in test output |
| 9 | Resource exhaustion | Fails late in long runs | Leaked contexts, worker OOM | Close contexts; fewer `workers`; check runner size |
| 10 | Virtualized / lazy lists | Element "not found" | Not rendered yet | Let locator actions scroll; assert count after a load signal |
| 11 | Async backend processing | Asserts before a job completes | Eventual consistency | `expect.poll()` against an API with an explicit timeout |
| 12 | Fragile cleanup | Next test sees leftovers | `afterEach` cleanup that fails silently | Create-unique, don't clean; or transactional fixtures |

## Triage protocol
1. Reproduce: `npx playwright test <spec> --repeat-each=20 --workers=4`. The hook records the
   pass/fail counts as FACT.
2. Open the trace of a failing attempt (`npx playwright show-trace <zip>`) and find the first action
   that diverges from a passing trace.
3. Classify against the table. If nothing fits, record a `QUESTION` — don't force a fit.
4. Fix, then re-run `--repeat-each` with the same count. The fix is `VERIFIED` only when CI shows
   the repeat run clean.
5. **Quarantine** (tag `@quarantine`; excluded from the gating job, still run in a non-gating job)
   requires an owner and an expiry date, recorded as an `ASSUMPTION` with that expiry. A quarantined
   test does not count toward changed-code coverage for autonomy-gating.
