# Escalation Reason Codes

Agent-expressed uncertainty escalates the tier by **exactly one level** (never more), and only for
this closed list. General unease is not a reason code.

| Code | Use when | Evidence required |
|---|---|---|
| `UNRESOLVED_DEPENDENCY` | Dependency discovery left an `UNRESOLVED` edge that could plausibly be affected | The scan output entry (`dependency-discovery` script result) |
| `UNKNOWN_BLAST_RADIUS` | Callers/consumers of changed code cannot be enumerated (dynamic dispatch, reflection, external consumers) | File:line of the changed symbol + the failed search |
| `SENSITIVE_PATH` | Change touches a sensitive domain the path lookup missed (Phase 2 domain judgment) | File:line showing the domain (e.g. fee computation) |
| `COMPATIBILITY_UNKNOWN` | Contract compatibility cannot be determined against deployed versions | `check-can-i-deploy.py` output with `UNKNOWN`/`INCOMPATIBLE` default |

## Rules
1. One escalation event raises the tier by one level. Multiple distinct reason codes in one
   assessment still raise by one level total; a later, separate assessment may raise again.
2. Record each escalation: `RISK` ledger entry + `risk_tier_history[]` row with `reason_code`.
3. CRITICAL is the ceiling.
4. **Downgrades are human-only.** Each downgrade writes a `risk_tier_history[]` row with
   `reason_code: HUMAN_DOWNGRADE`, the authenticated `actor_id`, and a justification.
5. **Downgrade rate is a health metric.** A rising rate means the escalation logic is miscalibrated
   and developers will start routing around the platform. Report it with the pilot metrics (§7) and
   feed it to `self-improvement/improvement-review`.
6. `SENSITIVE_PATH` raised by the Phase 0 lookup is a rule match, not an uncertainty escalation — it
   sets the tier directly and does not count toward the one-level rule.
