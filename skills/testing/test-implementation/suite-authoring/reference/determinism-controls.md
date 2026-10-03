# Determinism controls by stack

A hermetic test must give the same result on any machine, in any order, at any time. The five
sources of nondeterminism are time, randomness, locale and timezone, network, and test order.
Each one needs an explicit control.

| Control | JS/TS (Jest/Vitest) | Playwright | Python (pytest) | JVM (JUnit 5) | Flutter | React Native (Jest + Detox) | Go |
|---|---|---|---|---|---|---|---|
| **Clock** | `vi.useFakeTimers(); vi.setSystemTime(...)` / `jest.useFakeTimers()` | `page.clock.install({ time })` | `freezegun` / `time-machine` | Inject `java.time.Clock` (`Clock.fixed`) | `fakeAsync` + `clock`, or inject a `Clock` | Jest fake timers; Detox: app launch arg for the fixed time | Inject a clock interface |
| **Randomness** | Seeded RNG injected; `faker.seed(n)` | Seeded data builders | `random.seed`, `Faker.seed()`, Hypothesis `@seed` | `new Random(seed)`; Instancio `withSeed` | `Random(seed)` injected | `faker.seed(n)` | `rand.New(rand.NewSource(n))` |
| **Locale / TZ** | `TZ=UTC` env; `Intl` pinned | `use: { locale: 'en-US', timezoneId: 'UTC' }` | `TZ=UTC`, `locale.setlocale` pinned | `-Duser.timezone=UTC -Duser.language=en` | `Intl.defaultLocale = 'en_US'`; inject TZ | Device locale set in the Detox config | `TZ=UTC` |
| **Network** | MSW (`setupServer`) / nock; unhandled requests = error | `page.route` for third parties; real backend only on preview | `responses` / `respx`; `pytest-socket --disable-socket` | WireMock; MockWebServer | `http_mock_adapter` / mocktail clients; no real HTTP in widget tests | MSW (Jest); Detox: mock server or `launchArgs` | `httptest.Server` |
| **Order** | `--sequence.shuffle` / `--randomize` | `fullyParallel: true` | `pytest-randomly` | `MethodOrderer.Random` | `--test-randomize-ordering-seed=random` | Jest `--randomize` | `-shuffle=on` |
| **Waits** | `await findBy*`, `waitFor` | Web-first assertions, `waitForResponse` | `expect(locator)` / polling with a deadline | Awaitility | `pumpAndSettle` (see the caveats in flutter-testing) | Detox auto-synchronization + `waitFor().withTimeout()` | `require.Eventually` |

## Rules
- **Unhandled network is a failure, not a pass-through.** Configure MSW with
  `onUnhandledRequest: 'error'`, `pytest-socket`, and so on.
- **Mocks come from contracts.** Generate them from OpenAPI examples or Pact interactions, or validate a
  hand-built mock against the schema in a test (`ajv`, `openapi-core`, `jsonschema`). A mock nobody
  validates drifts away from the real API.
- **Print the seed on failure** (Hypothesis does this; for others, log the seed in `beforeAll`). A
  failure you can't replay is worth half a failure.
- **No shared mutable module state between tests.** Reset singletons in `afterEach`, use per-test DB
  transactions with rollback, and use Testcontainers for integration.
- **Fixed sleeps are banned** (`no_fixed_sleep_check.py`). If a stack has no state-based wait
  for a condition, write a polling helper with a deadline *and a condition*. That is still not a sleep.
