# Change Set Schema

Machine-readable form: [changeset.schema.json](changeset.schema.json).

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string `CS-<n>` | Yes | Server-assigned |
| `system` | string | Yes | The system being changed — not the repo |
| `initiative` | string | No | Grouping above the Change Set; full portfolio hierarchy is deferred (§2) |
| `requirements[]` | list of `{id, text, acceptance_criteria[], source}` | Yes | `source` cites issue URL / user statement |
| `story_refs[]` | list of story IDs `ST-<n>` | Yes when stories exist | Many-to-many: one story may span several Change Sets and one Change Set may implement several stories (v3.1 §4.12). Phase 1 forge-native: derived from `Implements: ST-n` lines in the PR body |
| `repositories[]` | list of `{repo, base_branch, pinned_sha}` | Yes | `pinned_sha` set by snapshot |
| `contracts[]` | list of `{contract_id, version, role: provider\|consumer}` | No | Phase 3 registry ids |
| `environments[]` | list of `{name, state_ref}` | No | |
| `status` | lifecycle state | Yes | See changeset-lifecycle.md |
| `status_before_blocked` | lifecycle state | When `BLOCKED` | Return target |
| `risk_tier` | `LOW\|MEDIUM\|HIGH\|CRITICAL` | Yes | Defaults to `HIGH` until computed |
| `risk_tier_history[]` | list of `{tier, reason_code?, actor_id, timestamp}` | Yes | Escalations + human downgrades |
| `snapshot_id` | string | Yes after `SCOPED` | |
| `parent_id` | string | No | Parent Change Set |
| `depends_on[]` | list of Change Set ids | No | |
| `tasks[]` | see tasks-and-checkpoints.md; each task carries `ac_refs[]` (`ST-<n>/AC-<n>`) | Yes after `PLANNED` | |
| `questions[]` | list of `{entry_id, state: OPEN\|ANSWERED\|EXPIRED, blocking}` | No | Ledger references |
| `assumptions[]` | list of `{entry_id, impact: LOW\|MEDIUM\|HIGH, expires_at}` | No | Ledger references |
| `gates[]` | list of `{gate, required_by_tier, status: PENDING\|REVIEWED\|VERIFIED\|APPROVED\|REJECTED, evidence_entry_id}` | Yes | |
| `forge_refs[]` | list of `{repo, issue, pr}` | No | Forge-native linkage |

```yaml
id: CS-881
system: billing-platform
requirements:
  - id: REQ-1
    text: "Apply a 2% fee to cross-border refunds"
    acceptance_criteria: ["Fee appears on refund receipt", "Domestic refunds unchanged"]
    source: "https://github.com/acme/billing/issues/412"
story_refs: [ST-101, ST-102]
repositories:
  - {repo: acme/billing, base_branch: main, pinned_sha: a1b2c3d}
  - {repo: acme/receipts, base_branch: main, pinned_sha: 9f8e7d6}
status: PLANNED
risk_tier: HIGH
risk_tier_history:
  - {tier: HIGH, reason_code: SENSITIVE_PATH, actor_id: "system:path-tier-lookup", timestamp: "2026-10-03T10:00:00Z"}
snapshot_id: SNAP-220
depends_on: []
tasks: []   # see tasks-and-checkpoints.md
```
