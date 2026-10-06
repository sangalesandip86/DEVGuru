# Discovery Bounds

Discovery (asking questions and reading files to understand a task) is bounded so it cannot
loop indefinitely.

| Bound | Default | Configurable range |
|---|---|---|
| Questions per round | 5 | 3–10 |
| Discovery rounds | 5 | 3–8 |
| File reads per question | 3 | 1–5 |
| Round timeout | 5 min | — |

## Exhaustion behavior
- When any bound is reached without enough grounding: **ESCALATE** to a human with a summary
  (questions asked, files read, what remains unknown). It does not draw from the 3-attempt budget.
- Do not continue discovery by guessing; unresolved items become QUESTION entries or tagged,
  expiring ASSUMPTIONs (`grounding/ambiguity-escalation`).

## Self-improvement signal
Log every exhaustion as a `discovery-budget-exhaustion` signal via
`self-improvement/failure-capture` (negative signal), with the bound that was hit and the task
type, so repeated exhaustion can drive better refinement or adjusted bounds.
