# Run checkpoint

Every ranged run ends with a checkpoint at `.adlc/runs/<run_id>/checkpoint.json`. The file
follows [`checkpoint.schema.json`](../../schemas/checkpoint.schema.json). It is local state
(`.adlc/` is gitignored), so the durable copy is the handoff recorded in the Evidence Ledger.

```json
{
  "run_id": "RUN-2026-10-03-7f2a",
  "requested": {"start": "INTAKE", "end": "PLAN", "text": "ingest docs/req and go through architecture and planning"},
  "completed_stages": ["INTAKE", "ARCHITECTURE"],
  "stopped_at": "PLAN",
  "stop_reason": "ASK_PENDING",
  "ledger_cursor": "ENTRY-10442",
  "workspace": {"planning": "acme-plans@4be1c09", "app": "payments-svc@a1b2c3d"},
  "artifacts": [
    {"kind": "requirement", "ref": "acme-plans@4be1c09:plans/requirements/REQ-7.yaml", "content_hash": "sha256:…"},
    {"kind": "architecture-package", "ref": "acme-plans@4be1c09:architecture/README.md", "content_hash": "sha256:…"}
  ],
  "handoff": {"to": "human:tech-lead", "ref": "ENTRY-10440"},
  "next_preflight": {"start": "PLAN", "overall": "BLOCK", "inputs": ["architecture-package: needs APPROVAL from human:tech-lead"]},
  "open_questions": ["ENTRY-10431"],
  "created_at": "2026-10-03T14:20:00Z"
}
```

## Stop reasons
| `stop_reason` | Meaning | Resume when |
|---|---|---|
| `END_REACHED` | The requested end stage's gate passed | You want the next stages |
| `GATE_FAILED` | A stage's exit gate failed | The failing items are fixed |
| `ASK_PENDING` | Waiting for a human answer or APPROVAL | The ledger shows the answer or approval |
| `BLOCKED` | Preflight BLOCK on existing evidence | The missing items exist |
| `OBSERVED_STAGE` | Reached INTEGRATE/RELEASE | The forge or CI event is observed |
| `USER_STOP` | The user stopped the run | Any time |

## Resume rules
- Re-resolve the workspace first, because pinned SHAs may have moved. A moved SHA is a snapshot
  staleness check (§4.5).
- Re-run the preflight of `stopped_at`. Never trust the stored `next_preflight` as current.
- If an AC hash changed since the checkpoint, the readiness and test-design checks report it
  (AC freeze, §4.12).
