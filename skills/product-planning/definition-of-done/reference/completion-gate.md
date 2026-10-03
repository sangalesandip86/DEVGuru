# Completion gate: item reference

Source of truth: [`../../policies/dod-policy.yaml`](../../policies/dod-policy.yaml), evaluated by
[`completion_gate.py`](../../../enforcement/ci-checks/planning-gates/completion_gate.py).
If this table and the policy disagree, the policy wins.

## Both variants

| Item | Kind | Passes when |
|---|---|---|
| `ready_at_current_ac` | STRUCTURAL | The readiness record says READY or later, **and** its AC hash equals the story's current hash |
| `no_blocking_questions` | STRUCTURAL | No OPEN blocking QUESTION |
| `no_risky_assumptions` | STRUCTURAL | No unexpired ASSUMPTION > LOW |

## Standard variant

| Item | Applies | Kind | Passes when |
|---|---|---|---|
| `change_sets_integrated` | always | STRUCTURAL | ≥1 Change Set has the story in `story_refs`, and all of them are INTEGRATED or RELEASED |
| `ac_covered` | always | STRUCTURAL | Every `automated` criterion is `passing` in the ac-coverage report |
| `manual_ac_verified` | always (vacuous with no manual AC) | JUDGMENT (qa-diagnose or human, AC-pinned, one per manual AC) | A REVIEWED/ACCEPT record with `ac: <id>` |
| `tier_gates_verified` | always | STRUCTURAL | Every gate in `tier_gates[effective tier]` is VERIFIED by SYSTEM |
| `secret_scan_clean` | not DOCUMENTATION | STRUCTURAL | `secret-scan` VERIFIED |
| `within_scope` | always | STRUCTURAL | Changed paths ⊆ `affected_paths` (when declared), and the path tier of the diff ≤ the effective tier |
| `code_review_accept` | always | JUDGMENT (code-reviewer) | ACCEPT |
| `contract_compatibility` | API_CONTRACT / `touches.api_contracts` | STRUCTURAL | `contract-compatibility` VERIFIED |
| `migration_rollback_tested` | DATA_MIGRATION / `touches.data_migration` | STRUCTURAL | `rollback-test` VERIFIED |
| `accessibility_checked` | UI_STORY / `touches.ui` | STRUCTURAL | `accessibility` VERIFIED |
| `security_review_accept` | SECURITY_STORY or tier ≥ HIGH | JUDGMENT (security-reviewer) | ACCEPT. A REJECT blocks, and only a human lifts it. |
| `observability_reviewed` | INFRASTRUCTURE or tier ≥ HIGH | JUDGMENT (code-reviewer) | ACCEPT |
| `docs_updated` | API_CONTRACT, DOCUMENTATION | JUDGMENT (code-reviewer) | ACCEPT |

## Spike variant

| Item | Kind | Passes when |
|---|---|---|
| `spike_decision_recorded` | STRUCTURAL | A DECISION for the story with `adr_ref` |
| `spike_follow_ups` | STRUCTURAL | ≥1 story in plans/ with `follow_up_of: <spike>` |
| `spike_no_production_code` | STRUCTURAL | Merged Change Sets touched only `docs/**`, `**/adr/**`, `**/*.md` or `plans/**` |

## DONE → ACCEPTED

| Item | Applies | Kind |
|---|---|---|
| `po_acceptance` | (FEATURE_STORY or UI_STORY) and tier ≥ MEDIUM; or tier ≥ HIGH and not SPIKE | APPROVAL `human:product-owner` |

## Results
- `NOT_DONE`: some DONE-stage item is not PASS. Exit code 1.
- `DONE` with `awaiting_acceptance: true`: everything passes except `po_acceptance`.
- `DONE` with `awaiting_acceptance: false`: no acceptance step applies, so DONE is terminal.
- `ACCEPTED`: everything passes, including the human acceptance.

## Why DONE is stricter than "tests pass"
- **Machine evidence for machine facts.** Every "passed" is a SYSTEM-ingested VERIFIED gate (plan §5.5), not an agent's statement in a PR.
- **Criteria actually exercised.** AC coverage ties tests to criteria. A green suite that never touches AC-3 does not make AC-3 done. This is also the positive-signal quality gate for self-improvement (plan §4.2).
- **Scope honesty.** `within_scope` catches both unplanned paths and a misdeclared type or tier.
- **Freeze.** A story whose criteria moved after READY cannot be DONE against the old reviews.
