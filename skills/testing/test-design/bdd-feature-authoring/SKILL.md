---
name: bdd-feature-authoring
description: Write declarative .feature files from ACs, reusing existing step phrasing. Use for BDD repos (Cucumber/behave/SpecFlow/godog).
metadata:
  group: testing
  phase: 1
  binding: false
  plan-ref: "§4.13 rule 6 (step dedup), ADR 0003 addition 7"
  stage: DESIGN
  inputs: [ready-story]
  outputs: [test-design]
  repo_roles: [app, tests, planning]
---

# BDD Feature Authoring

## Purpose
In a BDD repo, the `.feature` file **is** the frozen oracle. qa-derive writes it from the AC without
seeing the code, and test-engineer binds it to step definitions
([bdd-step-binding](../../test-implementation/bdd-step-binding/SKILL.md)). The goal is scenarios that a
product owner can read and that compile against the existing step library. A new step phrase is
the exception, not the default.

## When this applies
- `stack.json.bdd` is non-empty, or the team chose BDD for this tier ([test-strategy](../../test-architecture/test-strategy/SKILL.md)).
- A story is READY and its design is due ([test-case-design](../test-case-design/SKILL.md)). Feature files
  replace or accompany `plans/test-designs/ST-n.yaml`; scenario IDs are shared.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve the repo that holds `features/`. That is usually `tests`, or `app` when tests are
   co-located. If none is found and BDD isn't set up, stop and route to Mode C as its own
   `TEST_AUTOMATION` story. Do not scaffold Cucumber inside a feature story.
2. **Inputs.**
   - READY story at its current `ac_hash`: SATISFIED. If the story is still refining, write a design outline only.
   - `.adlc/catalog/step-patterns.json` present at the current snapshot: SATISFIED. Otherwise ask the
     coordinator or test-engineer to run [test-repo-discovery](../../test-architecture/test-repo-discovery/SKILL.md).
     qa-derive may read only `step-patterns.json`, never `test-assets.json` or the step bodies.
   - Existing `.feature` files for this capability (ADOPT): extend them in place, appending scenarios
     or `Examples:` rows. Never write a parallel feature file.

## Procedure
1. **One feature per capability**, not per story. Tag each scenario with its story and AC:
   `@ST-12 @ST-12/AC-1 @SC-1`. CI selection (`--tags`) and `ac_coverage.py` read these tags.
2. **Be declarative, not imperative.** Describe *what* the user achieves, not clicks:
   - Good: `When she transfers 100.00 EUR to "Savings"`.
   - Bad: `When she clicks "#amount" and types "100" and clicks "Submit"`.
   UI mechanics belong in step definitions and page objects.
3. **Reuse phrasing first.** For every step, look for an existing pattern in `step-patterns.json`
   (case-insensitive, with parameters normalized):
   - **Exact match:** use the existing wording verbatim, including the parameter style (`{string}` versus quotes).
   - **Near match:** rephrase your step to the existing wording if the meaning is the same.
   - **No match:** write a new step. List it under `new_steps` in the handoff so test-engineer binds it.
     Keep new steps parameterized (`I transfer {amount} {currency} to {string}`) so one definition serves many rows.
4. **Use Scenario Outlines for data.** Drive happy, boundary and negative partitions through one flow with
   `Examples:` tables. Use multiple named tables to keep valid and invalid rows apart:
   ```gherkin
   @ST-12 @ST-12/AC-1 @SC-1
   Scenario Outline: Transfer amount limits
     Given a funded EUR account
     When she transfers <amount> EUR to "Savings"
     Then the transfer is <result>

     Examples: within limits
       | amount   | result   |
       | 0.01     | accepted |
       | 10000.00 | accepted |
     Examples: outside limits
       | amount   | result                          |
       | 0.00     | rejected with AMOUNT_OUT_OF_RANGE |
       | 10000.01 | rejected with AMOUNT_OUT_OF_RANGE |
   ```
   Boundary rows come from `boundary_values.py`, applied to the partitions in your design.
5. **Updating.** New data cases **append rows**. Never duplicate a scenario to add a case. Removing a row
   or a scenario is flagged by the integrity guard (`EXAMPLE_ROWS_REMOVED`, `TEST_REMOVED`) and is
   allowed only when the AC changed.
6. **Background** holds only what *every* scenario in the file needs. Keep it to 3 steps or fewer.
7. **Keep data, secrets and environments out of the text.** No real names, emails or credentials in
   feature files. Use personas ("a funded EUR account", "Alice (retail customer)") that builders resolve.
8. **Self-check before the PR:**
   - every `automated` AC is tagged at least once;
   - there is at least one negative scenario;
   - no step contains UI selectors;
   - no `Then` step lacks an observable outcome.

## Outputs
- `.feature` files (`REPO_WRITE` via PR). The handoff lists `scenarios[]` (with IDs and AC refs) and `new_steps[]`.
- REVIEWED: test design ACCEPT, pinned to `ac_hash`.

## Enforcement
**Enforced** — see rules below.

- `cucumber --dry-run --strict` in CI fails on undefined or ambiguous steps
  ([workflow.example.yml](../../../enforcement/ci-checks/test-integrity/workflow.example.yml), job `bdd-dry-run`).
- test-engineer is write-denied on `**/*.feature`, so it cannot change the oracle (§5.6, row "Test expectations come from AC, not code").
- Removing rows or scenarios is caught by [test_integrity_guard.py](../../../enforcement/ci-checks/test-integrity/test_integrity_guard.py).
- AC tag coverage is checked by `ac_coverage.py` (§4.12).

## References
- [reference/gherkin-style-guide.md](reference/gherkin-style-guide.md)
- [test-case-design](../test-case-design/SKILL.md), [bdd-step-binding](../../test-implementation/bdd-step-binding/SKILL.md)
- [test-repo-discovery](../../test-architecture/test-repo-discovery/SKILL.md), which produces `step-patterns.json` (phrases only)
- [evidence-gate](../../../grounding/evidence-gate/SKILL.md)
