# Acceptance-criteria standard

Acceptance criteria are the contract between the planner, qa-derive and developer. qa-derive
designs tests from them **before** seeing any implementation. The completion gate checks that
every automated criterion is exercised by a passing test. Criteria that are vague,
untraceable or unmeasurable break both of those things.

## The rules (checked by `plan_lint.py` and `readiness_gate.py`)

| # | Rule | Check |
|---|---|---|
| 1 | Every criterion has an id `ST-<story>/AC-<n>`, prefixed by its own story, unique, never reused after deletion | STRUCTURAL |
| 2 | `given`, `when`, `then` are all present and non-trivial | STRUCTURAL |
| 3 | `kind` ∈ `functional`, `negative`, `nfr` | STRUCTURAL |
| 4 | `verification` ∈ `automated`, `manual`. Manual criteria need a qa-diagnose or human verification record at DONE. | STRUCTURAL |
| 5 | At least one `negative` criterion (except SPIKE and DOCUMENTATION) | STRUCTURAL (`negative_ac`) |
| 6 | Every `nfr` criterion states a measurable number in `then` | STRUCTURAL (`nfr_quantified`) |
| 7 | Type-required tags are present (see below) | STRUCTURAL |
| 8 | The criteria are *testable* without seeing code | JUDGMENT: qa-derive (`qa_testability`) |

Rule 8 is a judgment, so no structural check can pass it. qa-derive passes it by producing a
test outline from the criteria alone.

**Tags:**
- `accessibility` on a UI story;
- `reproduction` on a BUG_FIX (a criterion that fails before the fix);
- `no-behaviour-change` on a REFACTOR or TECHNICAL_STORY;
- `rollback` and `data-integrity` on a DATA_MIGRATION;
- `security` and `observability` where they apply.

## Writing good criteria

**Observable outcomes.** `then` describes something a test or a person can observe at the
system boundary: UI text, an API response, an emitted event, a persisted record, a log line
with a request id. It never describes an implementation detail.

**Concrete data in `given`.** Name the example: book `EQ-LON-01`, VaR 1,250,000 USD at 10:42 UTC.
Concrete examples remove ambiguity and turn directly into test fixtures.

**One behaviour per criterion.** If `then` contains "and also", it is probably two criteria.

### Good and bad

| Bad | Why | Good |
|---|---|---|
| "The dashboard is fast" | no number; can't fail | `nfr`: Given 50 concurrent PMs, When the dashboard loads, Then p95 time-to-VaR-visible < 1.5 s |
| "Errors are handled" | which errors? observed how? | `negative`: Given the VaR API returns 503, When the PM opens the dashboard, Then the tile shows "VaR unavailable", shows no number, and logs the request id |
| "Use a Redis cache for VaR" | that's a solution, not acceptance | (move to developer notes; criterion: Then VaR is no older than 5 minutes) |
| "Works like the batch report" | references unstated behaviour | Given the same position snapshot, When intraday and batch VaR are computed, Then they differ by less than 1% |
| "Admin can manage users" | untestable scope | split per behaviour: create, deactivate, role change, each with its negative path |

### Example (from the worked example)

```yaml
acceptance_criteria:
  - id: ST-1/AC-2
    given: the latest VaR for the book is older than 15 minutes
    when: the PM views the tile
    then: the tile shows a "stale" badge and the age in minutes
    kind: negative
    verification: automated
  - id: ST-1/AC-4
    given: a screen-reader user on the dashboard
    when: focus reaches the VaR tile
    then: the figure, currency, as-of time and stale state are announced; contrast ratio is at least 4.5:1
    kind: nfr
    verification: manual
    tags: [accessibility]
```

## Linking tests to criteria
Tests reference criteria by id. [`ac_coverage.py`](../../../enforcement/ci-checks/planning-gates/ac_coverage.py)
accepts any one of these:
- the id in the test title: `it("shows VaR [ST-1/AC-1]", …)`. Function names can't contain `/`, so Python, Go and Java tests use the comment form below;
- an `@ac` comment or docstring on or just above the test: `# @ac ST-1/AC-2 ST-1/AC-3`;
- the id in the JUnit testcase name (parametrised or BDD scenarios).

## The AC freeze
When a story becomes READY, the gate records the canonical hash of its criteria
([`ac_hash.py`](../../../enforcement/ci-checks/planning-gates/ac_hash.py)):
- The hash covers semantic fields only. Reordering and re-wrapping don't change it.
- Any real change after READY returns the story to **REFINING**.
- The qa-derive and developer reviews pinned to the old hash stop counting.

This is what keeps qa-derive's "expected behaviour locked before seeing the implementation"
guarantee (plan §4.7) true when someone edits the criteria mid-flight.
