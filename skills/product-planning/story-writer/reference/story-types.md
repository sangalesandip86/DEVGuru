# Story types

The machine-readable source is [`../../policies/story-types.yaml`](../../policies/story-types.yaml),
a control file. This page explains how to choose a type.

| Type | Use when | Tier floor | Adds (DoR / DoD) |
|---|---|---|---|
| `FEATURE_STORY` | New or changed user-visible behaviour for a named persona | — | persona + value; PO acceptance at MEDIUM+ |
| `UI_STORY` | The primary surface is the UI | — | `ux`; an `accessibility` criterion; accessibility gate VERIFIED; PO acceptance at MEDIUM+ |
| `API_CONTRACT` | Adds or changes a public or shared API, event or schema | **HIGH** | `touches.api_contracts`; architect REVIEWED; contract-compatibility VERIFIED; docs updated |
| `DATA_MIGRATION` | Changes persisted data shape or content | **HIGH** | `rollback_plan`; rollback-test VERIFIED; data-integrity criteria |
| `SECURITY_STORY` | Implements or changes a control, or remediates a vulnerability | **HIGH** | `threat_statement`; security-reviewer REVIEWED at DoR and DoD |
| `INFRASTRUCTURE` | IaC, platform, network, runners, base images | MEDIUM | `rollback_plan`; observability review |
| `TECHNICAL_STORY` | Internal work with no intended user-visible change | — | a `no-behaviour-change` criterion |
| `REFACTOR` | Restructure without behaviour change | — | a `no-behaviour-change` criterion, backed by an unchanged test suite |
| `BUG_FIX` | Behaviour deviates from an accepted requirement | — | a `reproduction` criterion (failing test first) |
| `SPIKE` | Answer one question under a time-box | — | `spike.question` and `timebox_days ≤ 10`; **spike DoD** |
| `TEST_AUTOMATION` | Add or repair tests for existing criteria | — | criteria that name the AC ids being covered |
| `DOCUMENTATION` | Docs only | LOW | docs check |

## Choosing
- **Two types fit?** Pick the one with the higher floor. For example, a UI change that also adds an endpoint is an `API_CONTRACT` story with `touches.ui: true`. Better still, split it into two stories.
- **The type never lowers the tier.** `DOCUMENTATION` has floor LOW, but a "docs" story whose `affected_paths` include `services/payments/` is HIGH. The effective tier is always the maximum of the type floor, the path tier and the declared tier.
- **Type mismatch at DONE.** If the actual diff is riskier than the planned tier (a `DOCUMENTATION` story that changed code), the completion gate FAILs `within_scope`. The story must be re-tiered, which is a scope violation under plan §4.1. It is not quietly accepted.

## SPIKE in detail
A spike buys knowledge, not code:
- **Ready** when it states one answerable question and a time-box.
- **Done** when a DECISION entry and a merged ADR answer the question, follow-up stories exist with `follow_up_of: <spike>`, and **no production code was merged**. The completion gate checks that the merged paths are only docs, ADR or plan paths.
- Prototype code stays on the spike branch, or is rewritten under a READY follow-up story.
