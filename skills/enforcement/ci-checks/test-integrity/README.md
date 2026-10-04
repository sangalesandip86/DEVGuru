# Test-integrity CI checks

Plan v3.1 §4.13 rule 6 and [ADR 0003](../../../../docs/adr/0003-test-engineering-and-data.md).
These are **enforcement artifacts, not skills**. They run in CI as the SYSTEM identity, their
output is ingested as FACT, and the server sets VERIFIED. An agent can run them locally
to self-check, but a local run is never evidence.

| Check | File | Blocks on | §5.6 row |
|---|---|---|---|
| Test integrity guard | [test_integrity_guard.py](test_integrity_guard.py) | Weakened tests; any changed expectation not covered by a changed AC | "Agents don't weaken tests to go green" |
| Fixture PII scan | [fixture_pii_scan.py](fixture_pii_scan.py) | Real-looking emails, card numbers, IBANs or SSNs in test assets | "No real PII / production data / secrets in fixtures" |
| No fixed sleeps | [no_fixed_sleep_check.py](no_fixed_sleep_check.py) | `waitForTimeout`, `time.sleep`, `Thread.sleep`, `Future.delayed`… in test paths | "No fixed sleeps in tests" |
| Red/green proof | [red_green_check.py](red_green_check.py) | A new test that passes on the base SHA | "New tests actually detect the change" |
| New-test flake gate | [flake_gate.py](flake_gate.py) | New or changed tests flaky over 5 random-order reruns | (part of §4.13 rule 6) |
| Impact plan check | [impact_plan_check.py](impact_plan_check.py) | Undeclared or missing test files vs the declared impact plan | "Test scope matches the plan" |
| BDD dry run | `cucumber --dry-run --strict` ([workflow.example.yml](workflow.example.yml)) | Undefined or ambiguous steps | (step deduplication) |
| Diff-scoped mutation | Runner adapters in [mutation_adapters.json](mutation_adapters.json); Stryker, PIT, mutmut or cargo-mutants | A score below the tier threshold in `dod-policy.yaml` | "New tests actually detect the change" |

## Integrity guard finding types
| Type | Severity | AC-coverable? |
|---|---|---|
| `TEST_FILE_DELETED`, `TEST_REMOVED` | block | no. Needs a REVIEWED override. |
| `TEST_RENAMED_OR_REPLACED` | warn | — |
| `EXPECTATION_CHANGED` | block | **yes**, when every AC tag on the test is in `--ac-changed` |
| `ASSERTION_REMOVED`, `EXAMPLE_ROWS_REMOVED` | block | yes |
| `SKIP_ADDED`, `FOCUS_ADDED`, `SWALLOWED_ASSERTION`, `TIMEOUT_OR_TOLERANCE_LOOSENED`, `SNAPSHOT_MASS_UPDATE`, `NO_ASSERTIONS` | block | no |
| `SUT_MOCKED` | warn (heuristic) | — |

**Overrides.** A blocking finding becomes `accepted` only through `--overrides`. That is a JSON list of
`{finding_id, ledger_entry}` pairs, where each ledger entry is a REVIEWED acceptance by qa-diagnose (plus an
authenticated human at HIGH or CRITICAL). There are no inline suppression comments in any of these checks,
because an agent could simply add one.

**AC tags.** Tests are tagged `ST-n/AC-n` in the test name, a preceding comment, an annotation or a Gherkin
tag. With `--head` or `--head-root`, tags are looked up per test: on the declaration line and up to 3 lines above it.
In diff-only mode they are looked up per file. An untagged test can never be AC-covered.

## Heuristic limits (known, deliberate)
- Pairing a removed assertion with an added one uses a literal-insensitive "skeleton". Different-shaped
  replacements within a hunk are paired in order. In a hunk that both rewrites one test and adds another,
  the pairing may therefore misattribute. It errs toward flagging, and a reviewer resolves it.
- `NO_ASSERTIONS` needs the head file (`--base/--head` or `--head-root`) to see the whole test body. In
  diff-only mode it is reported only when the hunk contains the whole body.
- `SUT_MOCKED` matches the test file's subject name against mock targets. It is a warning only.
- Detecting loosened tolerances compares numbers on paired lines. A changed matcher
  (`toBeCloseTo(x, 2)` → `toBeCloseTo(x, 1)` lowers precision with a *smaller* number) is caught as
  `EXPECTATION_CHANGED` rather than `LOOSENED`.

## Tests
```bash
python -m unittest discover -s skills/enforcement/ci-checks/test-integrity/tests
```
