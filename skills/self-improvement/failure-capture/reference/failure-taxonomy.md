# Failure Taxonomy

The closed list of `failure_class` values ([ADR 0006](../../../../docs/adr/0006-self-improvement-lessons.md)).
Each class is defined **in skill terms**: what the skill's output got wrong, never what the
project was about. Positive and efficiency signals carry `failure_class: null`.

`failure_class` is derived **deterministically** from the check that caught the failure, via
[failure-class-map.json](failure-class-map.json). Only judgment-only failures (a reviewer
REJECT or human override with no check behind it) have their class picked by the catching
reviewer or human, who also writes the ≤280-character `note`.

| # | Class | Definition | Example (skill terms) | Typical catching checks |
|---|---|---|---|---|
| 1 | `INCOMPLETE_ARTIFACT` | A required section or item of a produced artifact is missing or empty | story-writer emitted a story with no out-of-scope list; spike closed with no follow-up stories | DoR `objective_stated`, `scope_defined`, `ux_defined`; DoD `docs_updated`, `spike_follow_ups` |
| 2 | `UNTESTABLE_CRITERIA` | Acceptance criteria or NFRs cannot be turned into a test as written | AC "page loads fast" with no number; qa-derive could not derive a case | DoR `ac_standard`, `nfr_quantified`, `qa_testability` |
| 3 | `MISSING_NEGATIVE_CASE` | Only the happy path is specified or tested; invalid input, error, or denial paths absent | Input-validation story with AC only for valid input | DoR `negative_ac` |
| 4 | `TRACEABILITY_GAP` | A claim, criterion, or test is not linked to its source or its criterion | Story without `source_refs`; tests not tagged with `ST-n/AC-n`; automated AC with no covering test | DoR `traceability`; DoD `ac_covered`; ac-coverage `uncovered_automated`, `untagged_tests` |
| 5 | `UNRESOLVED_DEPENDENCY` | A dependency or contract was not identified, resolved, or checked for compatibility | Story touching an API with no contract listed; compatibility unknown at DoD | DoR `dependencies_resolved`, `contracts_identified`; DoD `contract_compatibility` |
| 6 | `UNRESOLVED_AMBIGUITY` | Work advanced past an open blocking QUESTION or an unexpired ASSUMPTION with impact > LOW | Story marked ready while a blocking QUESTION was OPEN | DoR/DoD `no_blocking_questions`, `no_risky_assumptions` |
| 7 | `OVERSIZED_CHANGE` | The unit of work exceeds the size budget and should have been decomposed | Story sized `L`; diff above the risk-tiering size cap | DoR `size_ok`; risk-tiering size cap |
| 8 | `MISSING_SAFEGUARD` | A tier- or data-required safety item is absent: security, threat, rollback, NFR, observability, accessibility | Data-migration story with no rollback plan; CONFIDENTIAL data with no security considerations | DoR `security_considerations`, `threat_statement`, `rollback_plan`, `nfrs_identified`; DoD `migration_rollback_tested`, `observability_reviewed`, `accessibility_checked`, `security_review_accept` |
| 9 | `UNDECLARED_DEVIATION` | A deviation from project standards (new dependency, major upgrade, new boundary) with no linked DECISION | Dependency manifest gained a package with no DECISION entry | dependency-decision-check `missing_decision` |
| 10 | `SCOPE_CREEP` | Output touches files, APIs, or repos outside the declared scope | Diff modifies a module not in the story's impact plan | DoD `within_scope`; scope check (`grounding/agent-failure-modes`); spike merged production code |
| 11 | `UNAUTHORIZED_ACTION` | The agent attempted an action its role is not permitted: control-file write, privileged state, denied tool | Developer agent tried to edit `.github/workflows/ci.yml` | control-file-guard deny; permission denial |
| 12 | `WEAKENED_TEST` | An existing test was made less able to fail: assertion removed, expectation changed, test skipped or deleted, tolerance loosened | Assertion removed to make a red test green | test-integrity `ASSERTION_REMOVED`, `SKIP_ADDED`, `EXPECTATION_CHANGED`, … |
| 13 | `INEFFECTIVE_TEST` | A new test cannot fail meaningfully: no assertions, or the system under test is mocked | Test calls the handler and asserts nothing | test-integrity `NO_ASSERTIONS`, `SUT_MOCKED` |
| 14 | `NONDETERMINISTIC_TEST` | A test depends on timing or ordering and can pass or fail without code changes | `waitForTimeout(2000)` instead of waiting on a condition | no-fixed-sleep rules (`js-wait-for-timeout`, `py-time-sleep`, …) |
| 15 | `SENSITIVE_DATA_EXPOSURE` | Real-looking personal data or secret material appeared in an artifact | Fixture contains a Luhn-valid non-test card number; secret scan hit | fixture-pii `EMAIL`, `PAN`, `IBAN`, `SSN`, `PHONE`, `PUBLIC_IP`, `SECRET_LIKE`; DoD `secret_scan_clean` |
| 16 | `UNSOURCED_CLAIM` | A claim in a structured artifact has no source and was not converted to a QUESTION or ASSUMPTION | Handoff states a latency figure with no ledger reference | evidence-gate `FAIL` |
| 17 | `INVALID_OUTPUT` | The output does not match the required shape (schema, handoff structure, plan lint) | Story YAML fails schema validation | DoR `schema_valid`; plan-lint errors; output validation gate |
| 18 | `INCORRECT_BEHAVIOR` | The produced change does not do what the criteria require: verified failing tests, production regression | Implementation fails the qa-derive cases; rollback after release | CI test failure on criteria tests; production CHALLENGED |
| 19 | `DESIGN_DEFECT` | Reviewer judgment: maintainability, structure, or architecture problem with no deterministic check | code-reviewer REJECT for duplicated logic across layers | DoD `code_review_accept`; DoR `architect_contract_review` (judgment) |
| 20 | `NON_CONVERGENCE` | The agent did not converge: attempt cap reached, handoff-cycle cap reached, or context exhausted mid-task | developer ↔ code-reviewer rejected 3 times | failure-modes `ITERATION_CAP`, `HANDOFF_CYCLE_CAP`, `CONTEXT_EXHAUSTED` |

## Rules
- The list is closed. A failure that fits nowhere is recorded with the closest class and a
  reviewer `note`. Proposing a new class is a change to this file (a control file) and goes
  through human approval.
- One incident carries exactly one class. A check that catches two distinct problems produces
  two incidents.
- Map entries with `"class": null` are checks that report **process state** (waiting for a
  human approval, aggregate gates), not a skill failure. They never produce an incident.
