# Ledger Entry Schema

Machine-readable form: [`../../schemas/ledger-entry.schema.json`](../../schemas/ledger-entry.schema.json).

| Field | Description | Required | Set by |
|---|---|---|---|
| `entry_id` | Unique identifier for this entry (`ENTRY-<id>`, server-assigned) | Yes | Server |
| `run_id` | Identifier for the agent execution run | Yes | Caller / hook |
| `change_set_id` | The Change Set this entry belongs to (null for platform-level operations). In forge-native mode: `<owner>/<repo>#<issue>` | No | Caller |
| `actor_type` | `HUMAN` / `AGENT` / `SYSTEM` | Yes | **Server-derived** |
| `actor_id` | The specific human, agent role, or system process (e.g. `hook:fact-writer`) | Yes | **Server-derived** |
| `agent_role` | Which role produced this entry, when `actor_type` is AGENT | Conditional | **Server-derived** |
| `model_id` | Which model was used | Yes for AGENT entries | Caller (recorded, not trusted for authority) |
| `tool` | `claude-code` \| `copilot` | Yes | Caller / hook |
| `classification` | FACT / INFERENCE / ASSUMPTION / PROPOSAL / QUESTION / DECISION / RISK | Yes | Caller (FACT only from SYSTEM actors) |
| `trust_level` | SYSTEM / ORGANIZATIONAL / REPOSITORY / EXTERNAL_STRUCTURED / EXTERNAL_UNSTRUCTURED — derived from a `source_type` map | Yes | **Server-derived** |
| `source_type` | Input to the trust map (`command_output`, `file_read`, `issue_text`, ...) | Yes | Caller / hook |
| `content` | The actual claim, decision, or observation | Yes | Caller |
| `source` | Where this came from (file:line, command output, doc URL, user statement) | Yes for FACT | Caller / hook |
| `input_references` | IDs of evidence entries this was derived from | Yes for INFERENCE | Caller |
| `output_references` | IDs of artifacts/files this produced | No | Caller |
| `decision_ids` | IDs of related DECISION entries | No | Caller |
| `lifecycle_state` | For DECISION/PROPOSAL: DRAFT / PROPOSED / REVIEWED / VERIFIED / APPROVED / REJECTED | No | Caller up to REVIEWED; VERIFIED / APPROVED server-only |
| `snapshot_id` | Which snapshot this entry was made against | No | Caller |
| `parent_entry_id` | For a correcting entry, the `entry_id` it corrects | No (required on corrections) | Caller via `record_correction` |
| `outcome_status` | `CHALLENGED` on correcting entries | No | Server (via `record_correction`) |
| `platform_release_sha` | One value covering the skill/role/policy version in effect | Yes | Server (from its deployed release) |
| `timestamp` | ISO 8601 timestamp | Yes | Server |
| `signal_source` | For self-improvement: AGENT / REVIEWER / HUMAN / PRODUCTION | No | Caller |
| `prev_hash` | Hash of the previous entry in the chain | Yes | Server |
| `entry_hash` | `sha256` over the canonical JSON of this entry (including `prev_hash`) | Yes | Server |

### Classification-specific fields
| Classification | Extra fields |
|---|---|
| ASSUMPTION | `impact` (LOW/MEDIUM/HIGH), `expires_at`, `invalidated_by` |
| QUESTION | `blocking` (bool), `question_state` (OPEN/ANSWERED/EXPIRED), `addressed_to`, `options[]` (≥2), `proposed_default` (draft answer or payload). One entry per story/Change Set batch |
| RISK | `severity` (LOW/MEDIUM/HIGH/CRITICAL), `reason_code` (optional, from the closed list) |
| DECISION / PROPOSAL | `lifecycle_state` |

`question_state` changes are recorded as new entries (`parent_entry_id` = the question);
the effective state is the latest entry in that chain.

## Invariants
- **Append-only.** No entry is ever deleted or modified. Corrections are new entries with
  `parent_entry_id` set, never an edit to the original.
- **Hash-chained.** `entry_hash = sha256(canonical_json(entry_without_entry_hash))`, where the
  entry includes `prev_hash` = the previous entry's `entry_hash` (genesis: 64 zeros).
  Canonical JSON = UTF-8, sorted keys, no insignificant whitespace.
- FACT entries have `actor_type: SYSTEM`.
- `lifecycle_state: VERIFIED` only with `actor_type: SYSTEM`; `APPROVED` only with
  `actor_type: HUMAN`.

## Related tables (same ledger)
| Table | Schema | Notes |
|---|---|---|
| Incidents | `self-improvement/failure-capture/reference/incident.schema.json` | Signal plus `evidence_refs` (entry ids) only. No task text, files, or use-case content (ADR 0006). `record_incident` rejects free-text fields; `query_incidents` returns pointers, not content |
| Lessons | `self-improvement/improvement-review/reference/lesson.schema.json` | Written with `record_lesson`; a sanitization PASS is required; `scope: ORG` only after a human APPROVED event |

**Retention:** ledger entries referenced by incidents stay in the project ledger under its own
access controls and retention period (default 90 days, configurable). Lessons outlive them by
design, because they contain nothing from the case.
