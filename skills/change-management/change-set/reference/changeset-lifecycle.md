# Change Set Lifecycle

```
DRAFT → SCOPED → PLANNED → PLAN_APPROVED → EXECUTING → VERIFYING → INTEGRATED → RELEASED

Side states:
  BLOCKED   — a gate failed, a dependency is unmet, or escalation triggered
              (returns to the state recorded in status_before_blocked once resolved)
  FAILED    — unrecoverable error after exhausting retry/replan options
  CANCELLED — abandoned by human decision

Reachable only from RELEASED:
  ROLLED_BACK — was RELEASED but reverted due to a production issue
```

## Transition table

| From | To | Who may trigger | Condition |
|---|---|---|---|
| DRAFT | SCOPED | agent (product-owner) | Requirements + repositories listed; snapshot pinned |
| SCOPED | PLANNED | agent (architect/developer) | `tasks[]` defined; tier computed |
| PLANNED | PLAN_APPROVED | **server**, from VERIFIED evidence (LOW/MEDIUM) or an authenticated human approval event (HIGH/CRITICAL) | Per [approval-matrix.md](approval-matrix.md) |
| PLAN_APPROVED | EXECUTING | agent (developer) | |
| EXECUTING | VERIFYING | agent (developer) | All tasks `DONE` |
| VERIFYING | EXECUTING | agent / server | Verification failed and retry budget remains |
| VERIFYING | INTEGRATED | **server only**, via `ingest_forge_event` (observed merge) | [completion-criteria.md](completion-criteria.md) all hold |
| INTEGRATED | RELEASED | **server only** — observed deployment record + environment approval | Per approval matrix |
| RELEASED | ROLLED_BACK | **server only** — observed rollback/revert deployment | |
| any active | BLOCKED | agent / server | Gate failure, unmet dependency, escalation, expired blocking ASSUMPTION |
| BLOCKED | `status_before_blocked` | server / human | Blocking condition resolved (evidence entry required) |
| any active | FAILED | server | Retry/replan exhausted (`grounding/agent-failure-modes`) |
| any non-terminal | CANCELLED | **authenticated human** | |

"Active" = SCOPED … VERIFYING. Terminal = RELEASED, ROLLED_BACK, FAILED, CANCELLED (RELEASED is
terminal except for ROLLED_BACK).

## Rules
- `PLAN_APPROVED` replaces v2's `APPROVED` state name, which collided with the entry-level
  `APPROVED` lifecycle_state and with release approval.
- `ROLLED_BACK` is reachable only from `RELEASED` — you cannot roll back something never released.
- `BLOCKED` stores `status_before_blocked`; it never returns to an earlier state than that.
- Invalid transitions are rejected by the change_management module of the adlc MCP server (plan's Server 2), not merely discouraged.
- Forge-native (single repo): DRAFT…EXECUTING are implicit in issue/PR state; `VERIFYING` = PR
  open with checks running; `INTEGRATED` = merge event; `RELEASED` = deployment + env approval.
