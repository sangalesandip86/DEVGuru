# New-test flake gate

Plan §4.13 rule 6 and ADR 0003, addition 4.

## Rule
Before a PR can merge, every **new or changed** test runs **N = 5** times in **random order**.
`flaky-detector.py` must then report `flaky_count == 0` for those tests.

A flaky new test is a defect in the test. It is not acceptable noise. The gate result is FACT,
which the server turns into VERIFIED. It also feeds the self-improvement signal stream (§4.2).

## Workflow
```
1. test IDs = integrity guard added/changed declarations (head)
2. for i in 1..5:
      run those tests with random order + a fresh seed, JUnit XML → reports/run-$i.xml
        Jest:        --randomize --seed=$RANDOM
        Vitest:      --sequence.shuffle --sequence.seed=$RANDOM
        pytest:      -p random_order --random-order-seed=$RANDOM   (pytest-randomly also works)
        JUnit 5:     junit.jupiter.testmethod.order.default=org.junit.jupiter.api.MethodOrderer$Random
        Playwright:  --repeat-each=5 --workers=4 (parallelism exposes shared-state bugs)
        Flutter:     flutter test --test-randomize-ordering-seed=random
        Go:          go test -shuffle=on -count=1
3. python skills/testing/test-maintenance/flaky-test-intelligence/scripts/flaky-detector.py reports/run-*.xml
4. exit code 1 (flaky found) → the gate fails; post the flaky list to the PR
```

## Policy values (defaults, tunable from ledger data)
| Tier | Repeats | Parallel workers |
|---|---|---|
| LOW / MEDIUM | 5 | runner default |
| HIGH / CRITICAL | 10 | at least 4, to expose shared-state races |

E2E tests against shared staging are **not** repeated by this gate, because they would mutate
shared state. They run on an ephemeral preview environment instead. If none exists, they are
listed in the gate output as `not-gated` for a reviewer to see.

## Why random order matters
Order-dependent tests pass reliably in file order and fail when run in parallel or under test
sharding. These are the most common hidden flakes in AI-generated suites, because leaked module
state or a shared fixture is mutated by one test and read by another.
