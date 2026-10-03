<!-- reconstructed: v2 source not provided; review -->

# Evidence Taxonomy (§5.1)

## Classifications

| Class | Definition | Who writes it | Required support | Example |
|---|---|---|---|---|
| `FACT` | Directly observed by a system: command output, file content at a pinned SHA, CI result, forge event | **Hooks / server only** (SYSTEM) | `source` | "`pytest` exited 1 with 2 failures" (hook) |
| `INFERENCE` | A conclusion derived from cited evidence | Agents | `input_references` (≥1) | "The failure is caused by the timezone change in ENTRY-41" |
| `ASSUMPTION` | Believed but unsourced; proceeding on it deliberately | Agents | `impact`, `expires_at`, `reason` | "Assume amounts are in minor units (impact MEDIUM)" |
| `PROPOSAL` | A suggested change or course of action awaiting decision | Agents | rationale + references | "Add an index on `orders.customer_id`" |
| `QUESTION` | Something that needs an answer from a human or another role | Agents | `addressed_to`, `blocking`, `question_state` | "Should refunds be prorated?" (blocking) |
| `DECISION` | A choice made, with rationale | Agents (within authority) / humans | rationale + references; `lifecycle_state` | "Use optimistic locking for order updates" |
| `RISK` | A potential negative outcome worth tracking | Agents / hooks | `severity`, evidence | "Migration locks `payments` table for ~4 min at current size" |

## Decision order (pick the first that applies)
1. Was it observed by a system and recorded by a hook/server? → **FACT** (cite it; never write it)
2. Is it a choice being made? → **DECISION** (or **PROPOSAL** if not yours to make)
3. Is it a potential harm? → **RISK**
4. Is it derived from cited evidence? → **INFERENCE**
5. Is the answer needed and not discoverable? → **QUESTION**
6. Otherwise → **ASSUMPTION** (with impact and expiry)

## Lifecycle state (DECISION / PROPOSAL only)

```
DRAFT → PROPOSED → REVIEWED → VERIFIED → APPROVED
                 ↘ REJECTED (from any non-terminal state)
```

| State | Set by | Meaning |
|---|---|---|
| `DRAFT` | Agent | Work in progress |
| `PROPOSED` | Agent | Ready for review |
| `REVIEWED` | Agent role (reviewer) | Judgment with evidence attached — ACCEPT/REJECT. Never equivalent to VERIFIED |
| `VERIFIED` | Server, from machine evidence only | A deterministic check ran and passed |
| `APPROVED` | Authenticated human | Explicit sign-off |
| `REJECTED` | Reviewer agent, server, or human | Not accepted; reason referenced |

Not every item passes through VERIFIED — a pure design judgment may go REVIEWED → APPROVED. But
for HIGH and CRITICAL tiers, `APPROVED` requires a `VERIFIED` prerequisite on the machine-
checkable parts (§5.5).

## Common misclassifications
| Wrong | Right | Why |
|---|---|---|
| FACT: "tests pass" (agent says so) | Cite hook FACT `ENTRY-…` or CI VERIFIED | Self-report is not observation |
| INFERENCE with no inputs | ASSUMPTION | No evidence to derive from |
| ASSUMPTION on a payment rule | QUESTION (blocking) | High cost, hard to reverse |
| DECISION: "approved the plan" by an agent | PROPOSAL / REVIEWED | Only humans approve |
