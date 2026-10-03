# Epic record (`plans/epics/EPIC-n.yaml`)

The normative schema is [`../../schemas/epic.schema.json`](../../schemas/epic.schema.json).
There is **no status field**. An epic's progress is derived from its stories' derived statuses.

| Field | Req. | Notes |
|---|---|---|
| `id` | yes | `EPIC-<n>`; matches the file name |
| `title` | yes | Names the outcome ("Intraday VaR for portfolio managers"), not the tech ("VaR Kafka pipeline") |
| `requirement_id` | yes | Exactly one parent requirement (scope tree) |
| `objective` | yes | One sentence |
| `business_outcome` | yes | From the requirement. Observable and measurable. |
| `success_metrics` | — | Numbers with a population |
| `scope` / `out_of_scope` | yes | Each scope line must map to ≥1 story (checked in PR review) |
| `features[]` | — | Optional `{id: FEAT-n, title, description}`. They live **inside** the epic and have no file of their own. |
| `milestone_ids` | — | Time axis (many-to-many) |
| `dependencies` | — | Epic-level, same shape as story dependencies |
| `risks` | — | Each traceable to a source, or recorded as a RISK entry |
| `source_refs` | — | Inherited from the requirement when omitted |

## Why features have no files
Features are an optional grouping, added only when an epic is large. Giving them files and a
lifecycle would add a fourth status machine that nobody needs (ADR 0002). If features later
need their own lifecycle, that gets a new ADR.

## Sizing an epic
An epic has no size estimate. Its size is the sum of its stories, and the stories are what
get calibrated. An epic that keeps growing past about 15 stories should probably be two
epics, or should be cut back to its outcome.
