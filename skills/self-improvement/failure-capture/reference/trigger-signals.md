# Trigger Signals

Each trigger produces at most one incident per failing skill step. The incident carries the
signal and ledger pointers only ([incident-schema.md](incident-schema.md)).

| Type | Trigger | `signal_source` | `check_id` → `failure_class` |
|---|---|---|---|
| **Negative (deterministic)** | DoR item fails at the readiness gate | AGENT | `dor:<item>` (e.g. `dor:negative_ac` → MISSING_NEGATIVE_CASE) |
| | DoD item fails at the completion gate | AGENT | `dod:<item>` (e.g. `dod:within_scope` → SCOPE_CREEP) |
| | Test-integrity guard finding | AGENT | `test-integrity:<CODE>` (e.g. `ASSERTION_REMOVED` → WEAKENED_TEST) |
| | Fixed-sleep check rule hit | AGENT | `no-fixed-sleep:<rule>` → NONDETERMINISTIC_TEST |
| | Fixture PII scan finding | AGENT | `fixture-pii:<TYPE>` → SENSITIVE_DATA_EXPOSURE |
| | ac-coverage: uncovered automated AC / untagged tests | AGENT | `ac-coverage:<status>` → TRACEABILITY_GAP |
| | Plan lint error / freeze violation | AGENT | `plan-lint:error` → INVALID_OUTPUT, `plan-lint:freeze_violations` → SCOPE_CREEP |
| | Manifest change with no linked DECISION | AGENT | `dependency-decision:missing_decision` → UNDECLARED_DEVIATION |
| | Control-file write denied / control file changed in a PR | AGENT | `control-file-guard:deny`, `control-file-policy:control_files_changed` → UNAUTHORIZED_ACTION |
| | Evidence-gate failure in a structured artifact | REVIEWER | `evidence-gate:FAIL` → UNSOURCED_CLAIM |
| | Agent-failure-modes event (scope violation, permission denial, attempt cap, handoff-cycle cap, context exhaustion, invalid output) | AGENT | `failure-mode:<EVENT>` (catalog in `grounding/agent-failure-modes`) |
| | Criteria tests fail in CI | AGENT | `ci-tests:criteria_test_failed` → INCORRECT_BEHAVIOR |
| | Diff over the risk-tiering size cap | AGENT | `risk-tiering:size_cap_exceeded` → OVERSIZED_CHANGE |
| | Routing near-miss (Phase 2 routing applied a mandatory binding Phase 1 missed) | AGENT | `skill-router:mandatory_near_miss` → INCOMPLETE_ARTIFACT (skill `skill-routing/skill-router`) |
| **Negative (judgment-only)** | Reviewer REJECT with no deterministic check behind it | REVIEWER | `null`; class + ≤280-char note by the reviewer |
| | Human override of an agent recommendation, or downgrade of an escalated risk tier | HUMAN | `null`; class + note by the human |
| **Positive** | First-pass acceptance with ac-coverage VERIFIED and changed-code coverage recorded | REVIEWER | `failure_class: null`, `pattern_eligible: true` |
| | Same, with weak verification | — | `signal_type: unverified-positive`, `pattern_eligible: false` |
| **Efficiency** | Token/cost budget overrun, REPLAN, success only after ≥2 attempts | AGENT | `failure_class: null` (persistent tool failures and crashes map to `null` too) |
| **Production** | Incident, rollback, or performance regression linked to a Change Set | PRODUCTION | `production:<incident\|rollback\|perf_regression>` → INCORRECT_BEHAVIOR (see [production-feedback.md](production-feedback.md)) |
| **Negative (input hygiene)** | User pasted a secret value into a session | HUMAN | `trust-boundaries:secret_pasted` → SENSITIVE_DATA_EXPOSURE; skill `grounding/trust-boundaries`; the evidence entry records the secret's kind/name only, never the value |

## Portable detection core
Hook-based detection uses only events common to Claude Code and Copilot: `sessionStart`,
`sessionEnd`, `userPromptSubmitted`, `preToolUse`, `postToolUse`, `errorOccurred`. Gate and
CI results arrive as SYSTEM ledger entries. Any extra Claude Code event is an enhancement,
not a dependency (§8).

## Adding a trigger
A new check must add its finding IDs to `failure-class-map.json` in the same PR.
`tests/test_failure_class_map.py` fails while any DoR/DoD item, integrity code, or fixed-sleep
rule in the repo is unmapped.
