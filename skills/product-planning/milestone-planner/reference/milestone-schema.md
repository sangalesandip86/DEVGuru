# Milestone record (`plans/milestones/MS-n.yaml`)

The normative schema is [`../../schemas/milestone.schema.json`](../../schemas/milestone.schema.json).
There is **no status field**.

| Field | Req. | Notes |
|---|---|---|
| `id` | yes | `MS-<n>` |
| `name` | yes | Names the outcome. plan-lint warns on layer-shaped names. |
| `objective` | yes | One sentence |
| `business_outcome` | yes | What a named user or the business can do or observe once it is reached |
| `success_criteria` | yes, ≥1 | Measurable, with a population |
| `epic_ids`, `story_ids` | — | Members (many-to-many; a story may belong to several milestones) |
| `out_of_scope` | — | What people might assume is included but isn't |
| `entry_criteria` | — | Preconditions before work toward it starts |
| `exit_criteria` | yes, ≥1 | `{id: MS-n/EX-n, description, check: STRUCTURAL/JUDGMENT/APPROVAL, role?, approver?}` |
| `target_release`, `target_date` | — | Human commitments, not predictions |
| `dependencies`, `risks` | — | As for stories |

## Outcome, not layer

| Anti-example (layer or activity) | Why it's wrong | Outcome-shaped |
|---|---|---|
| "Data ingestion foundation" | Nothing a user can observe; it hides integration risk | "Risk analysts can see intraday positions for equity books in the risk UI" |
| "Risk calculation engine" | Engine done ≠ anyone using it | "PMs see intraday VaR for equity books" |
| "API and integration" | A layer | "Limit monitoring consumes intraday VaR for equity books" |
| "UI and user workflows" | The last layer: every risk lands here | (UI slices belong inside each outcome milestone) |
| "Production readiness" | A hardening phase at the end | NFR slices inside each milestone, plus an exit criterion "staged rollout VERIFIED" |
| "Sprint 14 work" | An iteration, which is a time box owned by humans | Iterations are read from the tracker, never modelled as milestones |

An outcome-shaped sequence for the same requirement:
1. **MS-1:** PMs see intraday VaR for equity books.
2. **MS-2:** PMs see intraday VaR for FX books, and limit monitoring consumes it.
3. **MS-3:** PMs are alerted before limits are breached.

Each milestone is releasable and demonstrable. Each one cuts through all the layers it needs.

## Exit criteria examples
```yaml
exit_criteria:
  - id: MS-1/EX-1
    description: ST-1 and ST-2 are DONE
    check: STRUCTURAL
  - id: MS-1/EX-2
    description: Staged rollout to the equity desk VERIFIED with no rollback
    check: STRUCTURAL
  - id: MS-1/EX-3
    description: Pilot PMs confirm the figure is usable for intraday decisions
    check: APPROVAL
    approver: human:product-owner
```
