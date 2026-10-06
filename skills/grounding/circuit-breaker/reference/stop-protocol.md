# Stop Protocol

## Stop file
- Location: `.adlc/STOP` under the workspace root (override with `ADLC_WORKSPACE_ROOT`).
- Presence is the signal; content is optional free text (reason, who, when) and is data only.
- Scope: **all** sessions and background workers sharing that workspace.

## Polling
- Interactive tool calls: check before every tool invocation.
- Background workers: poll every **200 ms**.
- A worker that sees STOP finishes no new tool call; an in-flight call is allowed to return but its
  result is not acted on beyond checkpointing.

## Halt sequence
1. Write a `HALTED` event to `.adlc/journal/` (trigger, timestamp, session id).
2. Write a checkpoint (format below) and record it in the evidence ledger.
3. Preserve the workspace: no cleanup, no branch/worktree deletion, locks released only via the
   normal path.
4. Report: trigger, checkpoint entry id, completed vs. pending tasks.

## Checkpoint format
| Field | Content |
|---|---|
| `change_set_id` | Active Change Set |
| `task_id` | Task in progress (or last completed) |
| `completed` | Task ids finished this session |
| `pending` | Task ids not started |
| `in_flight` | Tool call interrupted, if any, and its intended effect |
| `workspace` | Branch/worktree paths preserved |
| `trigger` | `STOP_FILE`, `MAX_WALL_CLOCK`, `MAX_TASKS`, or `MAX_TOKENS` |

## Resume
1. A human removes `.adlc/STOP` (agents never do).
2. Start a session; `query_evidence` for the last checkpoint of the Change Set.
3. Verify the preserved workspace matches the checkpoint (branch, HEAD sha); on mismatch, ESCALATE.
4. Re-run any `in_flight` call only after confirming it had no partial effect.

## Configurable limits
| Limit | Default | Trigger on reach |
|---|---|---|
| Max wall-clock per session | 30 min | Halt sequence, trigger `MAX_WALL_CLOCK` |
| Max tasks per session | 20 | Halt sequence, trigger `MAX_TASKS` |
| Max tokens per session | 500K | Halt sequence, trigger `MAX_TOKENS` |
| STOP poll interval (background) | 200 ms | — |
