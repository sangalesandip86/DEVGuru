# Red/green check: proving a new test can detect the change

Plan §4.13 rule 6 and ADR 0003, addition 2.

## Rule
A test added for a `BUG_FIX`, or for a newly added acceptance criterion, must:

1. **fail on the base SHA**, the target branch before the change, and
2. **pass on the head SHA**.

A test that passes on both SHAs proves nothing about the change. Its expected values may have
been read from the implementation, or it may assert too little. In either case the check fails,
and the test goes back to test-engineer.

The check is deterministic and runs as the SYSTEM identity, so its result is VERIFIED evidence
(§5.5). No agent can produce or overrule it.

## Which tests count as "new"
- Test declarations that the integrity guard reports as added (`added_decls`), restricted to tests
  tagged with an AC ID that is new in this story, or tagged `@regression ST-n` for a BUG_FIX.
- Tests that only got new rows in a `Scenario Outline`: only the new rows are run.
- Exempt: `REFACTOR` and `TECHNICAL_STORY` stories. Their AC is "no behaviour change", so new
  tests there are characterization tests and are *expected* to pass on base. For these, the check
  asserts **green on both SHAs** instead.

## Workflow
```
1. checkout head; collect the new test IDs:
     test_integrity_guard.py --base <base-co> --head <head-co>   (added declarations)
     ∩ tests tagged with ST-n/AC-n where AC-n is new in plans/ (plan_lint output)
2. checkout base; copy the NEW TEST FILES ONLY from head onto base
   (production code stays at base; shared fixtures/page objects come from head)
3. run only those tests on base   → expect: FAIL (each one)
     - "fail" means assertion failure. Compile or import errors because the new API does not
       exist yet also count, but the result records them as RED_BY_COMPILE so a reviewer
       can tell them apart from RED_BY_ASSERTION.
4. checkout head; run the same tests → expect: PASS
5. emit evidence (FACT → server sets VERIFIED):
     {"test": "...", "ac_refs": [...], "base": "RED_BY_ASSERTION|RED_BY_COMPILE|GREEN",
      "head": "GREEN|RED", "verdict": "PROVEN|NOT_PROVEN"}
```

## Outcomes
| base | head | verdict | Meaning |
|---|---|---|---|
| RED_BY_ASSERTION | GREEN | **PROVEN** | The test detects the change |
| RED_BY_COMPILE | GREEN | **PROVEN (weak)** | Accepted. Mutation testing (diff-scoped) is the backstop for assertion strength. |
| GREEN | GREEN | **NOT_PROVEN** | Tautological, or asserting too little. Blocks DONE (DoD item). |
| any | RED | **FAILING** | Ordinary failure. qa-diagnose investigates. |

## Runner notes
| Stack | Run selected tests |
|---|---|
| Playwright | `npx playwright test --grep "ST-12/AC-4"` |
| Jest / Vitest | `npx vitest run -t "ST-12/AC-4"` / `npx jest -t ...` |
| pytest | `pytest -k "ST_12_AC_4"`, or a marker `@pytest.mark.ac("ST-12/AC-4")` with `-m` |
| JUnit 5 | `@Tag("ST-12_AC-4")` with `-Dgroups=` (Gradle `--tests` for a class) |
| Flutter | `flutter test --plain-name "ST-12/AC-4"` |
| Go | `go test -run 'TestST12AC4'` |
| Cucumber | `--tags "@ST-12/AC-4"` |

Use the runner's JUnit reporter. Results are parsed from JUnit XML, never from console text.
