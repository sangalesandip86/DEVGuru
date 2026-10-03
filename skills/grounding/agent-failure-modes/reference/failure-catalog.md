# Failure Catalog

Each failure mode has a handling rule **and** a retry-policy class.

| Failure Mode | Handling | Retry Policy |
|---|---|---|
| Agent loops (generate → review → regenerate endlessly) | Iteration cap per task (default: 3 attempts), then BLOCKED + evidence of what was tried | RETRY (counts toward the 3-attempt cap) |
| Agent produces structurally invalid output | Output validation gate — does the output match the expected shape for its handoff? | RETRY |
| Agent misunderstands the task / scope violation | Does the output stay within Change Set scope? If it touches files/APIs outside scope, flag before accepting | ESCALATE immediately — does **not** draw from the 3-attempt budget |
| Agent hits tool failure (command error, MCP timeout) | Retry with backoff for transient errors; BLOCKED for persistent errors; never silently skip the tool call | RETRY (transient) / STOP (persistent) |
| Agent exceeds context window mid-task | Detect context pressure, checkpoint progress to Evidence Ledger, decompose remaining work into sub-tasks | REPLAN |
| Agent session crashes | Evidence Ledger entries from partial run persist; agent reads prior entries before regenerating | RESUME |
| Permission denial (agent attempted an action outside its scope) | Logged, blocked at the tool-permission layer | ESCALATE immediately — never retried |
| Security-gate rejection (security-reviewer rejects) | Treated as a correct, working control, not a failure to route around | ESCALATE to human — never silently retried into exhaustion |

A scope violation, a permission denial, and a security rejection are not retry-worthy transient
failures. Burning down the same 3-attempt counter used for a flaky tool timeout would either
exhaust the budget on a legitimate block, or worse, create pressure to keep trying until
something slips through.

## Retry policy definitions
| Policy | Meaning | Consumes attempt budget? |
|---|---|---|
| `RETRY` | Try again, changing something material between attempts (record what changed) | Yes |
| `STOP` | Stop the task; mark BLOCKED with the error as evidence | No |
| `ESCALATE` | Hand to a human (or the upstream role, per conflict-resolution) immediately | No |
| `REPLAN` | Checkpoint, then decompose the remaining work into sub-tasks | No (sub-tasks get their own budget) |
| `RESUME` | Read prior ledger entries and continue from the last checkpoint | No |

## Transient vs. persistent tool failure
| Transient (RETRY with backoff 1s / 4s / 16s) | Persistent (STOP) |
|---|---|
| Network timeout, HTTP 429/502/503, MCP timeout, lock contention | Auth failure (401/403), command not found, schema/validation error, same error 3 times in a row |

## Interaction with handoff cycles
Rejections between two roles are capped separately at **3 handoff cycles**
(`roles/reference/conflict-resolution.md`). A loop between developer and code-reviewer hits
whichever cap comes first.

## What "evidence of what was tried" contains
For each attempt: the attempt number, the change made relative to the previous attempt, the
failure observed (ledger FACT reference), and the hypothesized cause (INFERENCE). Present it
using `grounding/human-review-format`.
