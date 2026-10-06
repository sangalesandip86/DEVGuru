# Cross-Cutting Design Rules

## Host Parity Invariant

**Statement:** Every capability behaves identically regardless of host tool (Claude Code,
Copilot, future hosts). Host adapters translate protocol details only — they never add, remove,
or modify capabilities.

**Implications:**
- Roles are defined in tool-neutral YAML and generated per host.
- Hooks parse both host payload dialects (dual-platform hook parsing).
- The MCP server is host-agnostic.
- Managed settings are generated per host from one source.

**Verification:** a CI check for role parity across host outputs.

## Document Visibility Classification

Every agent-generated artifact carries an implicit visibility classification:

| Level | Rule | Examples |
|---|---|---|
| `INTERNAL` | Never in chat or deliverables. Stored in `.adlc/`. Viewable via Insight Hub on demand. | Role notes, evidence queries, intermediate analysis, handoff contracts, risk computations |
| `DELIVERABLE` | May appear in chat and PRs. Stored in normal project locations. | PR descriptions, review summaries, gate approval requests, escalation reports |

**Implementation:** Single `visibility` field on evidence ledger entries and journal events.
Default: `INTERNAL`. Context Assembly skips `INTERNAL` entries when building human-facing
responses.
