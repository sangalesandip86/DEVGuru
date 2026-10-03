# Conflict Resolution

Plan ref: §4.7. Replaces v2's flat authority ranking. Reviewers judge in **domains**
(code-quality, security, design, test-design, diagnosis) that are not comparable on one axis, so no
ranking lets one domain's ACCEPT cancel another's REJECT.

## Rules

1. **A REJECT from any reviewer blocks within its own domain.** Only an authenticated human lifts it.
   A security REJECT is not overridden by an architecture ACCEPT, and vice versa.
2. **Cross-domain disagreement goes to a human**, not to a ranking table. Architect ACCEPT +
   security-reviewer REJECT is a human decision, presented with both positions and their evidence via
   [`human-review-format`](../../grounding/human-review-format/SKILL.md).
3. **Upstream–downstream rejection:** rejection evidence goes to the upstream role and the Evidence
   Ledger. Upstream gets **one** revision attempt; still rejected after revision → escalate to a
   human with both positions and evidence.
4. **Infeasibility:** product-owner is notified with evidence; the Change Set moves to `BLOCKED`
   until the requirement is revised or confirmed.
5. **Max handoff cycles between any two roles: 3.** After 3 back-and-forth rejections, escalate to a
   human, regardless of rules 1–4.

## Related

- Two roles disagreeing on **risk tier** is not a conflict to resolve here: the higher assessment
  wins by fail-safe default ([`fail-safe-defaults`](../../grounding/ambiguity-escalation/reference/fail-safe-defaults.md)).
- A security REJECT is never retried into exhaustion
  ([`failure-catalog`](../../grounding/agent-failure-modes/reference/failure-catalog.md)).
- Lifting a REJECT is a human action recorded as an `APPROVED` ledger entry with `actor_type: HUMAN`,
  referencing the REJECT entry via `parent_entry_id`.
