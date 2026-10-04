---
name: evidence-ledger
description: Record and query the append-only, hash-chained evidence ledger. Use when recording, querying, correcting evidence, or resuming a run.
metadata:
  group: core
  phase: 0
  binding: true
  plan-ref: "§4.3, §5.8, §6"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Evidence Ledger

## Purpose
The ledger is the platform's provenance backbone: what every run read, decided, and assumed.
It feeds audit, resumability, handoffs, and `/self-improvement`. It is served by the
`evidence_ledger` module of the `adlc` MCP server (plan's Server 1).

## When this applies
- Recording any non-FACT entry: INFERENCE, ASSUMPTION, DECISION, QUESTION, PROPOSAL, RISK
- Reading prior entries at the start of a run (resume) or to cite as sources
- Correcting a past entry (production feedback, a wrong assumption, an answered question)

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md) (cross-cutting).

- **Inputs:** an authenticated connection to the `evidence_ledger` module of the `adlc` MCP server; identity comes from the credential, never from arguments.
- **BLOCK:** if the ledger is unreachable, stop writing structured artifacts and report it; never fall back to unrecorded work.
- **Repo roles:** none; the ledger lives in `$ADLC_DATA_DIR`, not in a repo.

## Procedure
1. **Never write FACT entries yourself.** Command output and file reads are recorded by hooks
   directly (`enforcement/hooks/fact-writer-hooks`). Cite those entries by `entry_id`.
2. Record your own claims with `mcp:adlc.record_evidence`, supplying only:
   `change_set_id`, `classification`, `content`, `source` / `input_references`, and the optional
   fields relevant to the classification (`lifecycle_state`, `impact`, `expires_at`,
   `blocking`, `snapshot_id`). **Do not** pass `actor_type`, `actor_id`, `agent_role`, or
   `trust_level` — the server derives them from your authenticated connection and rejects
   requests that try to set them.
3. An INFERENCE must list `input_references`. A FACT requires `source`. The server rejects
   entries that violate [reference/ledger-entry-schema.md](reference/ledger-entry-schema.md).
4. **Entries are append-only.** To correct one, call `mcp:adlc.record_correction` — it writes a
   new entry with `parent_entry_id` set and `outcome_status: CHALLENGED`. There is no update or
   delete tool.
5. At the start of a run, `mcp:adlc.query_evidence` for the Change Set / task and read the last
   checkpoint before doing new work (`grounding/agent-failure-modes`, RESUME).
6. You can reach `lifecycle_state` `PROPOSED` or `REVIEWED` only. `VERIFIED` is written by the
   server from ingested machine evidence; `APPROVED` only from an authenticated human event.

## Outputs
Ledger entries per the schema; `entry_id`s to cite in handoffs and summaries.

## Enforcement
**Enforced** — see rules below.

| Rule | Enforced by |
|---|---|
| Agent identity is authentic | Server-side derivation from the authenticated connection (§5.6) |
| FACT entries are grounded | Hooks write FACT entries; agent credentials cannot write FACT |
| Append-only, tamper-evident | No update/delete tool; hash chain verified by the server on read and by an offline chain check |
| No agent sets APPROVED / VERIFIED | Tool surface: no such parameter value accepted from agent callers |
| Schema validity | Server validates against `core/schemas/ledger-entry.schema.json` |

## References
- [reference/ledger-entry-schema.md](reference/ledger-entry-schema.md)
- [reference/identity-and-auth.md](reference/identity-and-auth.md)
- [../schemas/ledger-entry.schema.json](../schemas/ledger-entry.schema.json)
- [../fact-classification/SKILL.md](../fact-classification/SKILL.md)
- [../../mcp-servers/reference/mcp-server-design.md](../../mcp-servers/reference/mcp-server-design.md)
