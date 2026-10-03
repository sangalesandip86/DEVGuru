# Budget Escalation

<!-- reconstructed: v2 source not provided; review -->

When a hard cap is reached:
1. Stop new work; checkpoint (context-compaction.md).
2. Record a `RISK` entry: spend, cap, remaining work estimate, cause hypothesis (INFERENCE).
3. Escalate with `grounding/human-review-format`:
   - LOW/MEDIUM → `human:tech-lead`
   - HIGH/CRITICAL → `human:tech-lead`, cc `human:security-lead` if security gates are pending
4. Human options: raise the cap, decompose, or cancel. The agent never chooses "drop verification".
5. Repeated escalations for one repo or role feed `self-improvement` as efficiency signals.
