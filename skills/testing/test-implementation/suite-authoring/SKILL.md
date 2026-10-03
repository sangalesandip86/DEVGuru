---
name: suite-authoring
description: test-engineer's procedure for creating or surgically updating test suites from a frozen test design — chooses Mode A (surgical update), B (convention mirror) or C (greenfield, its own story), declares a CREATE/UPDATE/REUSE impact plan, binds scenarios to code via page objects/robots, builders and contract-validated mocks, and never changes an existing expectation unless the AC changed. Use for any unit, component/widget, contract, BDD-binding or E2E test-writing task.
metadata:
  group: testing
  phase: 1
  binding: true
  plan-ref: "§4.13 steps 2-6"
  stage: TEST
  inputs: [test-design, change-set]
  outputs: [test-suite]
  repo_roles: [app, tests, contracts]
---

# Suite Authoring

## Purpose
Turn a frozen test design into tests that are correct, follow the repository's conventions, are
deterministic, and are honest. `test-engineer` reads the code to **bind** each scenario: locators,
harness, DTO shapes, mocks. It never reads the code to decide **what to expect**. Expected outcomes
come from the design (ADR 0003).

## When this applies
- A story has a frozen design (`plans/test-designs/ST-n.yaml` or `.feature` files) and its tests must be
  written or updated.
- An implementation change broke existing tests and the suite must be brought in line.
- Read "Update rules" before touching anything; most damage happens here.

## Preflight
Run the standard preflight first: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and
[`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve `app`, plus `tests` (separate E2E repo) and `contracts` where they apply. Every
   path you write must be in Change Set scope.
2. **Frozen design for the story at its current `ac_hash`:**
   - SATISFIED: proceed.
   - **Missing:** offer
     - (A) **BACKFILL DESIGN** through qa-derive ([test-case-design](../../test-design/test-case-design/SKILL.md)), or
     - (B) **characterization mode** (ADR 0004 §3): tests tagged `characterization` (`@characterization`
       or a `characterization` marker or describe-prefix), and an ASSUMPTION "current behaviour is
       intended" recorded. These tests **never count as AC verification or VERIFIED for any story**.
       Choose B only for legacy coverage work with no story.
   - **Stale** (`ac_hash` mismatch): BLOCK. The story is back in REFINING, and the design must be redone first.
3. **Discovery.** `stack.json`, `test-assets.json` and `step-patterns.json` must be fresh for the snapshot.
   If not, run [test-repo-discovery](../../test-architecture/test-repo-discovery/SKILL.md).
4. **No framework for the needed tier** (`has_tests: false`, or no runner for the tier). Use **Mode C**,
   which is its own `TEST_AUTOMATION` or `INFRASTRUCTURE` story through workspace-resolver and planning.
   **Stop here** for the current feature story. Never scaffold a framework inside it.

## Procedure
1. **Choose the mode:**

   | Mode | Condition | What you do |
   |---|---|---|
   | `A_SURGICAL` | A suite already covers the target | Edit in place. Smallest diff. Reuse every existing helper. |
   | `B_MIRROR` | The framework exists; the target is untested | New files following the top golden sample's placement, naming, wrapper and setup |
   | `C_GREENFIELD` | No framework for the tier | Separate story. The framework choice is a DECISION by the architect (or a human in Degraded Mode) and an ADR. Dependency and CI files follow the tier rules, and CI config is a **control file (CRITICAL)**. |

2. **Write the impact plan before any file write** ([reference/impact-plan.schema.json](reference/impact-plan.schema.json), example in
   [reference/impact-plan-example.yaml](reference/impact-plan-example.yaml)):
   - every file marked `CREATE`, `UPDATE` or `REUSE`, by kind: fixture, builder, page-object, robot,
     step-def, spec, mock, config;
   - for each `UPDATE` to a shared asset, the **usage scan** listing every dependent test;
   - the scenario → test mapping (`ST-n/SC-n` → file::test name).

   CI compares the plan with the diff. An undeclared file is a scope violation (§4.1).
3. **Order of work.**
   1. Fixtures and builders ([test-data-synthesis](../../test-data/test-data-synthesis/SKILL.md)).
   2. Page objects and robots: locators and actions live there. Specs and steps call them.
   3. Mocks and stubs: **contract-validated**, generated from or checked against the OpenAPI, Pact or
      schema in `/contracts`, never invented.
   4. Specs and step definitions ([bdd-step-binding](../bdd-step-binding/SKILL.md)).
4. **Bind each scenario.** Each test:
   - names or tags its scenario and AC (`[ST-12/SC-1] [ST-12/AC-1] …` or the runner's tag mechanism);
   - asserts **the design's expected outcome**: observable, specific, and with exact error codes;
   - uses the lowest tier the design hints.
5. **Choose locators in this order.** See
   [selectors-best-practices](../../web-ui-automation/playwright-expert/reference/selectors-best-practices.md).
   1. Role, label or accessible name (`getByRole('button', {name: 'Transfer'})`, Flutter `find.bySemanticsLabel`,
      RN `accessibilityLabel`).
   2. Test ID or key (`data-testid`, `Key('transfer-submit')`, `testID`, `accessibilityIdentifier`).
   3. Never CSS or XPath structure in new tests.

   If no stable hook exists, **propose** the testability change to `developer`, for example
   "add `Key('transfer-submit')` to `TransferForm`'s ElevatedButton". It goes in the story's Change Set or as a
   TECHNICAL_STORY. You never edit app source; you are write-denied there.
6. **Apply the determinism controls for the stack** ([reference/determinism-controls.md](reference/determinism-controls.md)):
   fake clock, fixed seeds, pinned locale and timezone, stubbed network, random order on. No fixed
   sleeps; waits are state-based.
7. **E2E specifics.**
   - Critical journeys only.
   - A pre-test health check.
   - Idempotent, run-namespaced seed data.
   - A per-journey assertion strategy: check persistence and reload only where the AC is about persistence.
   - Verified teardown.
   - You run E2E only against **ephemeral preview environments**. Shared staging runs are **CI-only**.
8. **Run locally.** Run the affected hermetic tiers (`WORKSPACE_WRITE`). The fact-writer hooks record results as FACT.
   Then self-check against the integrity guard locally:
   ```bash
   python skills/enforcement/ci-checks/test-integrity/test_integrity_guard.py --base <base-checkout> --head .
   ```

## Update rules (Mode A)
- **An expectation changes only when the AC changes.** You may change an existing assertion's expected
  value only if the linked story's AC hash changed. Cite the AC ID in the commit or PR.
  Otherwise a failing existing test is a **defect**: record it, hand it to `developer` (via qa-diagnose for
  diagnosis), and **leave the test unchanged**.
- **Don't**:
  - delete or skip a test, or add `only`, `xfail` or `@Disabled`;
  - loosen a timeout or tolerance;
  - mass-update snapshots;
  - wrap assertions in try/catch;
  - mock the unit under test.

  Each of these is flagged by the guard. When one is genuinely needed, for example deleting a test for a
  feature the story removes, cite the AC and ask qa-diagnose for a REVIEWED acceptance; a human is also
  needed at HIGH or CRITICAL.
- **Heal locators, not meaning.** A broken locator after a UI change is fixed in the page object
  ([self-healing-locators](../../test-maintenance/self-healing-locators/SKILL.md)). The assertions stay.
- **Golden-sample precedence.** Mirror the samples' style. Never mirror their violations of platform rules.

## Outputs
- Test code, fixtures, page objects and mocks (`REPO_WRITE`), plus the impact plan (PROPOSAL, checked against the diff).
- REVIEWED: implementation fidelity (scenario → test mapping complete, assertions match the design).
  **Never VERIFIED.** CI results are VERIFIED by the server.
- QUESTION or defect: spec-versus-code discrepancies, reported to qa-derive or developer, never resolved in the test.

## Enforcement
- [test_integrity_guard.py](../../../enforcement/ci-checks/test-integrity/test_integrity_guard.py): an expectation change requires an AC-hash
  change, and weakening is flagged (§5.6 row "Agents don't weaken tests to go green").
- [red_green_check.md](../../../enforcement/ci-checks/test-integrity/red_green_check.md) and diff-scoped mutation testing
  (§5.6 row "New tests actually detect the change").
- [new_test_flake_gate.md](../../../enforcement/ci-checks/test-integrity/new_test_flake_gate.md), [no_fixed_sleep_check.py](../../../enforcement/ci-checks/test-integrity/no_fixed_sleep_check.py).
- Oracle protection: test-engineer is write-denied on `plans/test-designs/**`, `**/*.feature` and app source (role permissions).
- Impact-plan versus diff: scope check (§4.1). The diff comparison is a CI job; see the workflow example.

## References
- [reference/impact-plan.schema.json](reference/impact-plan.schema.json), [reference/impact-plan-example.yaml](reference/impact-plan-example.yaml), [reference/determinism-controls.md](reference/determinism-controls.md)
- [test-repo-discovery](../../test-architecture/test-repo-discovery/SKILL.md), [test-data-synthesis](../../test-data/test-data-synthesis/SKILL.md), [bdd-step-binding](../bdd-step-binding/SKILL.md)
- Stack skills: [playwright-expert](../../web-ui-automation/playwright-expert/SKILL.md), [flutter-testing](../../mobile-automation/flutter-testing/SKILL.md), [detox-react-native](../../mobile-automation/detox-react-native/SKILL.md), [pact-consumer-driven](../../api-contract-testing/pact-consumer-driven/SKILL.md)
- [evidence-gate](../../../grounding/evidence-gate/SKILL.md), [agent-failure-modes](../../../grounding/agent-failure-modes/SKILL.md)
