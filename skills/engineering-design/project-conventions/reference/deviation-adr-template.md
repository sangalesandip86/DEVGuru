# Deviation ADR template (MADR, short form)

Use for every deviation from existing conventions. Store it in the project's existing ADR
directory (from `declared_standards.adr_dirs`); if none exists, propose `docs/adr/`.
Record a DECISION ledger entry referencing the ADR as `repo@sha:path` + content hash.

```markdown
# ADR-NNNN: <deviation in one line, e.g. "Use pino instead of winston in payments-service">

- Status: Proposed
- Date: YYYY-MM-DD
- Change Set / Story: CS-nnn / ST-nnn
- Deviation type: new-dependency | new-pattern | new-layer | new-module | data-store | messaging | error-handling | logging | config
- Approvals required: architect REVIEWED; human:tech-lead APPROVAL (required for new dependency or boundary change, any tier)

## Existing approach
What the project does today, with evidence: `conventions.json` concern entry, golden file
`path:line`, governing ADR/config `path#sha`.

## Why it doesn't fit this change
Concrete, sourced reason (numbers where relevant: latency, volume, a missing capability).
"Preference" or "more modern" is not a reason.

## Alternatives considered
1. Use the existing approach as-is — why rejected.
2. Extend/wrap the existing approach — why rejected.
3. The proposed deviation.

## Decision
What will be used, and exactly where (scope: this module only / repo-wide).

## Consequences & migration impact
- Two approaches now coexist? For how long? Who owns convergence?
- Follow-up REFACTOR/TECHNICAL_STORY id if convergence is planned.
- New conformance rule needed? (e.g. restrict the new library to one module)
```

Reject the ADR yourself (don't file it) if "Why it doesn't fit" has no sourced reason — follow
the existing convention instead.
