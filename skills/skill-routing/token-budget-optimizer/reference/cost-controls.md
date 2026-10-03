# Cost Controls

Default policy values — overridable, tuned from ledger data.

| Control | Default | On breach |
|---|---|---|
| Per-task soft cap | 1× tier budget | Warn; record `RISK` |
| Per-task hard cap | 2× tier budget | Stop, checkpoint, escalate (budget-escalation.md) |
| Per-Change-Set cap | sum of task caps × 1.25 | Escalate to `human:tech-lead` |
| Retry spend | counts toward the task cap | Same as above |

Tier budgets (relative units, calibrate per org): LOW 1, MEDIUM 3, HIGH 8, CRITICAL 15.

Never: skip grounding, skip a gate, or downgrade model tier on HIGH/CRITICAL to stay under a cap.
Track cost per merged change — it is one of the five pilot baseline metrics (§7).
