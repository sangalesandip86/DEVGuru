# Structured Reasoning Trail

## Purpose

Extends the evidence ledger and event journal with four structured reasoning channels,
providing role-specific working memory, auditable decisions, typed handoffs, and
human-readable summaries.

## Four Channels

| Channel | Event Types Used | Content | Audience |
|---------|-----------------|---------|----------|
| Role notes | `evidence.fact` | Role-specific working notes, observations | The role itself on resume |
| Decisions | `evidence.decision` | Explicit decisions with rationale + evidence refs | All roles, audit trail |
| Handoffs | `coord.message` | Typed handoff contracts (schema-validated) | Receiving role |
| Narrative | `evidence.inference` | Human-readable narrative summary | Operators, stakeholders |

## Payload Conventions

### Role Notes
```json
{
  "channel": "notes",
  "role": "developer",
  "content": "Discovered that the auth module uses JWT with RS256...",
  "evidence_refs": ["ev-001", "ev-002"]
}
```

### Decisions
```json
{
  "channel": "decision",
  "summary": "Use SQLite for journal storage",
  "rationale": "Stdlib-only constraint; no external DB dependency",
  "alternatives_considered": ["JSONL file", "PostgreSQL"],
  "evidence_refs": ["ev-003"]
}
```

### Handoffs
```json
{
  "channel": "handoff",
  "from_role": "developer",
  "to_role": "code-reviewer",
  "contract": { ... },
  "summary": "Implementation complete, ready for review"
}
```
Self-handoffs (from_role == to_role) are rejected.

### Narrative
```json
{
  "channel": "narrative",
  "summary": "Sprint progress: 3/5 stories complete, risk engine calibrated",
  "visibility": "DELIVERABLE"
}
```

## Timeline

Each reasoning entry automatically writes a timeline event to the event journal.
Timeline entries are compact: `{at, actor_id, role, channel, to?, summary}`.
The summary field is capped to the first line of the note content.

## Constraints

- Decisions must reference at least one evidence entry
- Handoffs validate against the existing handoff schema
- All reasoning entries are `INTERNAL` visibility by default
- Narrative channel entries may be `DELIVERABLE` for operator consumption

## Integration

- **Evidence Ledger:** reasoning entries link to evidence entry IDs
- **Event Journal:** all reasoning writes a journal event for timeline tracking
- **Conflict Resolution:** decisions channel is the audit trail
- **Self-Improvement:** reasoning patterns feed failure-capture and lesson extraction
