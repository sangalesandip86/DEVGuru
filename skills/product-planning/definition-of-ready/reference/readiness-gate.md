# Readiness gate: item reference

Source of truth: [`../../policies/dor-policy.yaml`](../../policies/dor-policy.yaml), evaluated by
[`readiness_gate.py`](../../../enforcement/ci-checks/planning-gates/readiness_gate.py).
If this table and the policy disagree, the policy wins.

## Mandatory

| Item | Kind | Passes when |
|---|---|---|
| `schema_valid` | STRUCTURAL | The story validates against `story.schema.json`. A `status` field fails it. |
| `objective_stated` | STRUCTURAL | `objective` is non-empty |
| `scope_defined` | STRUCTURAL | `scope` is non-empty and `out_of_scope` is present (it may be `[]`) |
| `nfr_quantified` | STRUCTURAL | Every `nfr` criterion has a number in `then` |
| `traceability` | STRUCTURAL | `requirement_id` exists in plans/, and `source_refs` all carry a `trust_level` |
| `dependencies_resolved` | STRUCTURAL | No UNRESOLVED dependency, and every ACCEPTED_RISK has a `human:` owner |
| `no_blocking_questions` | STRUCTURAL | No OPEN `blocking: true` QUESTION linked to the story |
| `no_risky_assumptions` | STRUCTURAL | No unexpired ASSUMPTION with impact > LOW. An ASSUMPTION with no expiry counts as unexpired. |
| `size_ok` | STRUCTURAL | `size` ∈ XS, S, M |
| `developer_feasibility` | JUDGMENT (developer, AC-pinned) | developer REVIEWED/ACCEPT at the current AC hash |

## Conditional

| Item | Applies when | Kind | Passes when |
|---|---|---|---|
| `value_statement` | not SPIKE/DOCUMENTATION | STRUCTURAL | `value_statement` is non-empty |
| `persona_identified` | FEATURE_STORY, UI_STORY | STRUCTURAL | `persona` is non-empty |
| `ac_standard` | not SPIKE | STRUCTURAL | ≥1 criterion, and every criterion meets the [AC standard](../../story-writer/reference/acceptance-criteria-standard.md) |
| `negative_ac` | not SPIKE/DOCUMENTATION | STRUCTURAL | ≥1 `negative` criterion |
| `security_considerations` | SECURITY_STORY, or CONFIDENTIAL/RESTRICTED data | STRUCTURAL | field is non-empty |
| `threat_statement` | SECURITY_STORY | STRUCTURAL | field is non-empty |
| `contracts_identified` | API_CONTRACT, or `touches.api_contracts` | STRUCTURAL | ≥1 contract named |
| `ux_defined` | UI_STORY, or `touches.ui` | STRUCTURAL | `ux` is non-empty |
| `accessibility_ac` | UI_STORY, or `touches.ui` | STRUCTURAL | a criterion tagged `accessibility` |
| `rollback_plan` | DATA_MIGRATION/INFRASTRUCTURE, or `touches.data_migration`/`infra` | STRUCTURAL | `rollback_plan` is non-empty |
| `nfrs_identified` | effective tier ≥ HIGH, not SPIKE | STRUCTURAL | `nfrs` or an `nfr` criterion |
| `bug_reproduction` | BUG_FIX | STRUCTURAL | a criterion tagged `reproduction` |
| `no_behaviour_change_ac` | REFACTOR, TECHNICAL_STORY | STRUCTURAL | a criterion tagged `no-behaviour-change` |
| `spike_framed` | SPIKE | STRUCTURAL | `spike.question` is set, and `0.5 ≤ timebox_days ≤ 10` |
| `qa_testability` | not SPIKE/DOCUMENTATION | JUDGMENT (qa-derive, AC-pinned) | qa-derive REVIEWED/ACCEPT, produced code-blind |
| `architect_contract_review` | API_CONTRACT, or `touches.api_contracts` | JUDGMENT (architect, AC-pinned) | architect REVIEWED/ACCEPT |
| `security_design_review` | SECURITY_STORY, or RESTRICTED data | JUDGMENT (security-reviewer, AC-pinned) | security-reviewer REVIEWED/ACCEPT |
| `scope_approval` | effective tier ≥ HIGH | APPROVAL (`human:product-owner`) | an authenticated HUMAN approval event for this item |

## Reading a result

```json
{"story": "ST-2", "result": "NOT_READY", "effective_tier": {"tier": "HIGH",
  "sources": {"type_floor": "HIGH", "path_tier": "HIGH", "declared": null}},
 "items": [{"id": "qa_testability", "check": "JUDGMENT", "status": "MISSING",
            "detail": "needs REVIEWED/ACCEPT from qa-derive (SYSTEM evidence cannot satisfy a JUDGMENT)"}]}
```

| Status | Meaning | Next step |
|---|---|---|
| `PASS` | satisfied | — |
| `MISSING` | evidence is absent or stale | supply the field, the review or the approval |
| `FAIL` | a structural rule is violated | fix the story (e.g. split an `L`) |
| `REJECTED` | the role's latest valid verdict is REJECT | address it with the reviewer. A domain REJECT is lifted only by a human (conflict-resolution rule 1). |

## Scaling by risk (why a docs story is cheap)
A `DOCUMENTATION` story at LOW tier triggers about 11 items, and the only judgment among them
is developer feasibility. An `API_CONTRACT` story on CONFIDENTIAL data at HIGH triggers about
19, including three judgments and a human approval. The policy scales process to risk (plan §1)
through `applies`, not through separate checklists.
