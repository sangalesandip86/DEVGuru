---
name: bdd-step-binding
description: Bind .feature steps to code, reusing existing definitions, keeping steps thin over page objects. Use when features are added or changed.
metadata:
  group: testing
  phase: 1
  binding: false
  plan-ref: "§4.13 rule 6 (step dedup), REQ-QA-502"
  stage: TEST
  inputs: [test-design]
  outputs: [test-suite]
  repo_roles: [app, tests]
---

# BDD Step Binding

## Purpose
Every step in the frozen `.feature` files must resolve to **exactly one** step definition. A
`DuplicateStepDefinition` or ambiguous match breaks the build, and an undefined step silently
reports as "pending". The step layer stays thin: it translates domain language into page-object,
robot, builder and API-client calls. It holds no assertions logic beyond what the `Then` text states.

## When this applies
- `.feature` files were added or changed by qa-derive ([bdd-feature-authoring](../../test-design/bdd-feature-authoring/SKILL.md)),
  and the handoff lists `new_steps[]`.
- `cucumber --dry-run` reports undefined or ambiguous steps.

## Preflight
See [standard-preflight](../../../workflow/stage-preflight/reference/standard-preflight.md).
1. **Workspace.** Resolve the repo with `features/` and the step-definition glue (`app` or `tests`).
2. **Frozen feature files** at the story's current `ac_hash`:
   - SATISFIED: proceed. You may **read** feature files but never edit them; you are write-denied.
   - Missing: offer BACKFILL DESIGN via qa-derive, or characterization mode (ADR 0004 §3, scenarios tagged
     `@characterization`, with an ASSUMPTION recorded, never counted as AC verification). Don't write the
     feature files yourself.
   - Stale `ac_hash`: BLOCK.
3. **The catalogue** `test-assets.json` must be fresh. It has the full step index with file and line, and it is your
   dedup source. If it isn't fresh, run [test-repo-discovery](../../test-architecture/test-repo-discovery/SKILL.md).
4. **No BDD runner configured.** That is Mode C, which is its own story ([suite-authoring](../suite-authoring/SKILL.md)).

## Procedure
1. **Get the authoritative list.** Run the runner's dry run first:
   - `npx cucumber-js --dry-run --strict`
   - `mvn test -Dcucumber.execution.dry-run=true`
   - `behave --dry-run`
   - `dotnet test` with SpecFlow/Reqnroll dry-run
   - `godog --no-colors --format=progress -d`

   Undefined and ambiguous steps from the runner are ground truth. The catalogue regex can miss dynamic registrations.
2. **Dedup each undefined step.** Look for a definition to reuse:
   1. Normalize the phrase: parameters become `{}`, case and whitespace are folded. Compare it with the
      normalized patterns in `test-assets.json`.
   2. **Match:** the step text *should* already resolve. If it doesn't, the existing pattern is too narrow
      (for example `{int}` where the feature uses `100.00`). Widen it with a **parameter type**
      rather than adding a near-duplicate definition. Every existing user of the pattern must still
      resolve, so run the dry run again.
   3. **No match:** add one new definition in the file for that domain area (`steps/transfers.steps.ts`),
      never in a "misc" file.
3. **Parameter types for domain values.** Define `{amount}`, `{currency}`, `{persona}` and so on once, in
   `support/parameter-types.*`. They convert text to domain objects (a `Money`, a builder persona).
   Steps receive typed values.
4. **Keep steps thin:**
   ```ts
   When('she transfers {amount} to {string}', async function (amount: Money, target: string) {
     await this.transferPage.transfer({ amount, to: target })   // page object owns locators
   })
   Then('the transfer is {transferResult}', async function (expected: TransferResult) {
     await this.transferPage.expectResult(expected)             // assertion lives in the page object
   })
   ```
   - No locators in step files.
   - No sleeps.
   - No data literals beyond what the step text passes. Defaults come from builders.
5. **State between steps** goes on the World or scenario context object (`this`, `ScenarioContext`,
   `context`), reset per scenario. Never use module-level variables.
6. **Hooks.** `Before` and `After` hooks are tagged where possible (`@db`, `@e2e`), so unrelated scenarios
   don't pay for them. Teardown for E2E data lives in `After` and is verified ([test-data-management](../../test-maintenance/test-data-management/SKILL.md)).
7. **Re-run the dry run.** Zero undefined and zero ambiguous steps is required. Then run the tagged
   scenarios (`--tags "@ST-12"`).

## Organizing step definitions
```
features/
  transfers/transfer_limits.feature        # qa-derive
  support/
    world.ts                               # per-scenario context
    parameter-types.ts                     # {amount} {currency} {persona}
    hooks.ts                               # tagged Before/After
  step_definitions/
    transfers.steps.ts                     # one file per domain area, not per feature
    accounts.steps.ts
    common.steps.ts                        # navigation/auth only; keep it small
```

## Outputs
- Step definitions and parameter types (`REPO_WRITE`), plus the dry-run output (FACT via hooks).
- REVIEWED: binding fidelity, meaning every scenario resolves and each step does what its text says.

## Enforcement
**Enforced** — see rules below.

- `cucumber --dry-run --strict` CI job, `bdd-dry-run` in
  [workflow.example.yml](../../../enforcement/ci-checks/test-integrity/workflow.example.yml).
- test-engineer is write-denied on `**/*.feature` (role permissions; §5.6 row "Test expectations come from AC, not code").
- [no_fixed_sleep_check.py](../../../enforcement/ci-checks/test-integrity/no_fixed_sleep_check.py) scans step directories.

## References
- [bdd-feature-authoring](../../test-design/bdd-feature-authoring/SKILL.md), [suite-authoring](../suite-authoring/SKILL.md)
- [test-repo-discovery](../../test-architecture/test-repo-discovery/SKILL.md) (step index + duplicates)
- [gherkin-style-guide](../../test-design/bdd-feature-authoring/reference/gherkin-style-guide.md)
