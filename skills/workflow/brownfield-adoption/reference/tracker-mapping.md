# Tracker → plan mapping

`import_tracker.py` produces **suggestions**. story-writer and requirement-intake make the
final call when they promote an inbox item.

## Kind
| Tracker | Suggested kind |
|---|---|
| Issue type Epic / Initiative, or label `epic` | `epic` |
| Issue type Requirement / Feature request / Idea | `requirement` |
| Anything else | `story` |

## Story type
The issue type is checked first; then a label with a **higher tier floor** overrides it. A
generic label only fills the type when the issue type gave none.

| Source | Suggested type |
|---|---|
| Bug / Defect | `BUG_FIX` |
| Story / User story | `FEATURE_STORY` |
| Task / Sub-task / Tech debt | `TECHNICAL_STORY` |
| Spike | `SPIKE` |
| Improvement | `REFACTOR` |
| Label `security` (overrides) | `SECURITY_STORY` (floor HIGH) |
| Label `migration` (overrides) | `DATA_MIGRATION` (floor HIGH) |
| Label `api` / `contract` (overrides) | `API_CONTRACT` (floor HIGH) |
| Label `infra` (overrides) | `INFRASTRUCTURE` (floor MEDIUM) |
| Label `ui` / `frontend` | `UI_STORY` |
| Label `docs` / `documentation` | `DOCUMENTATION` |
| Label `refactor` | `REFACTOR` |
| Label `test` | `TEST_AUTOMATION` |

When in doubt, choose the type with the higher floor. That is fail-safe, because a type can
raise a tier but never lower it (§4.12).

## Fields
| Inbox field | Becomes, on promotion |
|---|---|
| `title` | `title` (rewritten if it names a solution rather than an outcome) |
| `untrusted_body` | Neutral restatement in `objective` / `statement`. Never copied verbatim. |
| `acceptance_criteria_candidates` | AC in Given/When/Then form with IDs, plus at least one `negative` AC |
| `source_ref` | `source_refs[0]`, trust `EXTERNAL_UNSTRUCTURED` |
| `tracker_parent` | `epic_id`, if the parent was promoted |
| `tracker_milestone` | A hint for milestone-planner. A sprint is not a milestone. |
| `tracker_state_at_import` | Ignored for status. Noted in the PR description only. |
| `labels` | Type hints and `touches` hints (ui, api_contracts, …) |
