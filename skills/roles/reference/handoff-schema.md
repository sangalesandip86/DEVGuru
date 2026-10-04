# Handoff Schema

Plan ref: §4.7. Machine-readable form: [`handoff.schema.json`](handoff.schema.json).

Every transfer of work between roles is a typed handoff, recorded in the Evidence Ledger
(`record_handoff` on Server 2 for multi-repo work; a `DECISION` entry referencing the PR for
single-repo forge-native work). Handoffs are what make a Change Set traceable and resumable.


```yaml
handoff:
  handoff_id: HO-1042
  change_set_id: CS-881            # or the forge issue/PR id for single-repo work
  task_id: TASK-14                 # optional
  snapshot_id: SNAP-220
  from_role: architect             # server-derived from the authenticated caller, never self-reported
  to_role: developer               # or human:<role> in Degraded Mode
  attempt: 1                       # cycles between this role pair; max 3 then escalate to a human
  risk_tier: HIGH
  inputs:
    - artifact_ref: "repo-a@a1b2c3d:docs/architecture-decision-AD-77.md"
      content_hash: "sha256:9f8e..."
      trust_level: REPOSITORY
  outputs:
    - kind: design_decision        # one of the role's declared handoff_outputs
      artifact_ref: "repo-a@b4c5d6e:docs/adr/AD-78.md"
      content_hash: "sha256:1a2b..."
  claims:                          # every claim traces to a source (evidence-gate)
    - classification: DECISION
      content: "Use outbox pattern for fee events"
      ledger_entry_id: ENTRY-9990
  open_questions:
    - ledger_entry_id: ENTRY-9991
      blocking: true
      state: OPEN                  # OPEN | ANSWERED | EXPIRED
  assumptions:
    - ledger_entry_id: ENTRY-9992
      impact: MEDIUM               # LOW | MEDIUM | HIGH
      expires_at: "2026-10-10T00:00:00Z"
  verdict:                         # reviewers only
    authority: REVIEWED            # agents may only ever emit REVIEWED here
    domain: security               # code-quality | security | design | test-design | diagnosis
    result: REJECT                 # ACCEPT | REJECT
    evidence: [ENTRY-9993]
  created_at: "2026-10-03T12:00:00Z"
```

## Rules

- `artifact_ref` **always** resolves to `repo@sha:path` plus `content_hash`. A bare filename is
  mutable and is rejected by schema validation. Git already versions artifacts; no separate registry.
- `from_role` and `trust_level` on the record are server-derived; values supplied by the caller are
  ignored.
- `verdict.authority` can only be `REVIEWED` from an agent. `VERIFIED` comes from machine evidence
  written by the server; `APPROVED` comes only from an authenticated human event.
- A handoff with an `OPEN` question marked `blocking: true` cannot satisfy completion criteria
  ([`completion-criteria`](../../change-management/change-set/reference/completion-criteria.md)).
- `attempt` > 3 for the same role pair → escalate to a human
  ([`conflict-resolution`](conflict-resolution.md)).
