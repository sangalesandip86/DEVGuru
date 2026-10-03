# Story record (`plans/stories/ST-n.yaml`)

The normative schema is [`../../schemas/story.schema.json`](../../schemas/story.schema.json),
with `additionalProperties: false`. **No status field.** READY, DONE and ACCEPTED are derived by
the gates and recorded in the Evidence Ledger.

## Fields

| Field | Req. | Used by |
|---|---|---|
| `id` | yes | `ST-<n>`; must match the file name |
| `title` | yes | humans, tracker projection |
| `type` | yes | tier floor and conditional items ([story-types.md](story-types.md)) |
| `objective` | yes | DoR `objective_stated` |
| `persona` | FEATURE/UI | DoR `persona_identified` |
| `value_statement` | not SPIKE/DOCS | DoR `value_statement` |
| `requirement_id` | yes | traceability (DoR `traceability`, plan-lint) |
| `epic_id`, `feature_id` | — | scope tree. `feature_id` must belong to `epic_id`. |
| `milestone_ids` | — | time axis (many-to-many) |
| `follow_up_of` | — | set by SPIKE follow-ups and SPLIT children. Required for spike DoD. |
| `scope`, `out_of_scope` | yes | DoR `scope_defined`; reviewers' scope check |
| `affected_paths` | strongly recommended | path tier at READY (without it and without a floor, the tier is HIGH); `within_scope` at DONE |
| `acceptance_criteria` | yes (may be `[]` only for SPIKE) | [AC standard](acceptance-criteria-standard.md) |
| `nfrs` | HIGH+ | DoR `nfrs_identified` |
| `touches` | yes | `{ui, api_contracts[], data_migration, infra}`. Drives conditional items. |
| `data_classification` | yes | PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED. Drives security items. |
| `size`, `size_basis` | yes / — | XS/S/M/L ([sizing guide](../../story-refinement/reference/sizing-guide.md)) |
| `risk_tier` | — | declared tier. It can only raise the effective tier. |
| `source_refs` | yes, ≥1 | `{ref, trust_level}` |
| `dependencies` | — | `{ref, kind, status: RESOLVED/UNRESOLVED/ACCEPTED_RISK, evidence_level, owner}` |
| `security_considerations` | CONFIDENTIAL+ / SECURITY | DoR |
| `threat_statement` | SECURITY_STORY | DoR |
| `ux` | UI | DoR |
| `rollback_plan` | DATA_MIGRATION / INFRASTRUCTURE | DoR |
| `spike` | SPIKE | `{question, timebox_days ≤ 10, options[]}` |

## Effective tier
`effective = max(type floor, path tier of affected_paths, declared risk_tier)`. The
`affected_paths` are run through
[`path_tier_lookup.py`](../../../change-management/risk-tiering/scripts/path_tier_lookup.py).
If none of the three yields a value, the tier is **HIGH** (plan §5.3). That is why
`affected_paths` is worth predicting.

## Story ↔ Change Set
The relationship is many-to-many:
- A story can need several Change Sets (cross-repo).
- One Change Set can implement several stories, when a shared change serves both.

In Phase 1 (forge-native), the PR body declares `Implements: ST-101, ST-102`. Each Change Set
task carries `ac_refs[]` naming the criteria it addresses (see
[`tasks-and-checkpoints.md`](../../../change-management/change-set/reference/tasks-and-checkpoints.md)).
