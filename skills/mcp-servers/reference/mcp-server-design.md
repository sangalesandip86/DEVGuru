# MCP Server Design

Plan refs: §6 (MCP server design), §4.3 (ledger schema, identity-and-auth), §4.5 (Change Set),
§4.6 (contracts), §5.5 (authority), §5.8 (identity), §5.10 (forge as source of truth),
v3.1 §6 Module 4 (work planning). Decision record: [ADR 0001](../../../docs/adr/0001-mcp-modular-monolith.md).
Implementation: [`../adlc-mcp/`](../adlc-mcp/README.md).

## 1. Shape: one server, four modules

The plan's three servers (and v3.1's work-planning engine) ship as **one package, one process,
one MCP server named `adlc`** — a modular monolith. Each engine is a module that owns its own
data and exposes one public API, so it can be pulled out into its own server later without
touching its callers.

```
                 ┌──────────────────────── adlc (one process) ───────────────────────┐
 role session ──▶│ app.py: identity from ADLC_TOKEN → enabled modules → one MCP server │
 (ADLC_TOKEN)    │                                                                     │
                 │  evidence_ledger ◀─EvidencePort── change_management ◀─ChangeSetStatus─ work_planning
                 │       │                               │                     Port          │   ▲
                 │  evidence_ledger.db        change_management.db      work_planning.db     │   EvaluatorPort
                 │                                                                           │   (planning-gates)
                 │  contract_registry ── contract_registry.db                                │
                 │                                                                           │
                 │  kernel: identity · errors · util · config · db · module protocol · mcp_compat
                 └───────────────────────────────────────────────────────────────────────────┘
 hooks ── scripts/ledger_cli.py append-fact ──▶ evidence_ledger (in-process, SYSTEM hook:<name>)
```

| Module | Plan | Enabled from | Owns |
|---|---|---|---|
| `evidence_ledger` | Server 1 | Phase 0 | `evidence`, `evidence_content`, `incidents`, `lessons`, `ledger_settings` (+ read-only `incidents_v1`) |
| `change_management` | Server 2 | Phase 2 (multi-repo / parallel only) | `change_sets`, `status_history`, `tasks`, `snapshots`, `dependencies`, `risk_assessments`, `handoffs`, `forge_events` |
| `work_planning` | v3.1 Module 4 | Phase 2 | `plan_commits`, `items`, `edges`, `links`, `work_events`, `story_status`, `status_history` |
| `contract_registry` | Server 3 | Phase 3 | `contracts`, `contract_versions`, `deployments`, `check_results` |

`ADLC_MODULES` enables modules per phase; single-repo Phase 1 work needs only `evidence_ledger`
plus forge events (§5.10).

### Module rules (enforced by `tests/test_module_boundaries.py`)

1. **Own data.** Each module has its own SQLite file (`$ADLC_DATA_DIR/<module>.db`) and its own
   migrations. No shared tables, no cross-module joins, no `ATTACH`.
2. **One public surface.** `api.py` is the only file anything outside the module may import.
3. **No module imports another module.** Cross-module needs are declared as *ports* (Protocols)
   in the consuming module's `api.py` and satisfied by adapters in `app.py` — the only file that
   knows more than one module.
4. **The kernel never imports a module.** It stays small: identity, errors, canonical JSON/hashing,
   config, the SQLite factory and migrations runner, the `Module` protocol, and the MCP SDK shim.
5. **Authorization lives in the module**, not in `app.py`, so it survives extraction. Tool
   registration is role-scoped as well (a SYSTEM-only tool is never registered for an agent
   session), but registration is not the control — the API re-checks every call.

| Port | Declared in | Satisfied in-process by | On extraction |
|---|---|---|---|
| `EvidencePort` (blocking items, SYSTEM facts) | change_management | `LedgerEvidenceAdapter` → evidence_ledger API | remote client of `adlc-ledger` |
| `ChangeSetStatusPort` | work_planning | `ChangeSetStatusAdapter` → change_management API | remote client |
| `EvaluatorPort` (DoR/DoD) | work_planning | not yet wired → `NullEvaluator` (fails safe) | adapter around `skills/enforcement/ci-checks/planning-gates` |

A missing port never degrades to "assume fine": `NullEvidencePort` reports that blocking items
cannot be confirmed (so integration blocks), `NullEvaluator` reports the gate cannot pass, and
`NullChangeSetStatus` reports statuses as unknown.

## 2. Identity (all modules)

- **One credential per role session.** The server process resolves `ADLC_TOKEN` once at
  start-up into an `Identity` (`actor_type`, `actor_id`, `agent_role`, `tool`, `model_id`,
  `human_roles`). Every tool handler closes over that identity; **no tool accepts
  `actor_type`, `actor_id`, `agent_role` or `trust_level` as an argument** (a test asserts that
  passing one raises).
- **Pilot credential store:** `ADLC_CREDENTIALS` (default `~/.adlc/credentials.json`) maps
  `sha256(token)` → identity. Only hashes are stored; `scripts/adlc_credentials.py issue` mints
  a token and prints it once. The credentials file sits outside the repository.
- **Beyond a single-user, single-workspace pilot** — a second person or any cloud agent
  session — replace `kernel.identity.resolve_identity` with the organisation's OAuth2 / mTLS /
  RBAC layer and run the server remotely (streamable HTTP). Modules only ever see an `Identity`,
  so nothing else changes.
- **Hooks** write through `scripts/ledger_cli.py append-fact`, in-process, as
  `SYSTEM` / `hook:<ADLC_HOOK_NAME>`. It is deliberately not an MCP tool. Because an agent with
  shell access could run the CLI, managed settings deny agent Bash access to it, and
  `ADLC_REQUIRE_HOOK_TOKEN=1` additionally requires a SYSTEM credential in `ADLC_HOOK_TOKEN`.
- **Known pilot limitation:** a stdio server inherits its token from the client's
  environment. If an agent session can read its own environment, it holds only *its own*
  role's token — still never a SYSTEM or HUMAN one, which is what the authority split needs.

## 3. Authority (§5.5) — who can set what

| Value | Set by | Where enforced |
|---|---|---|
| `REVIEWED` (entry lifecycle, handoff verdict) | AGENT or HUMAN | `evidence_ledger.domain.LIFECYCLE_AUTHORITY`; `record_handoff` |
| `VERIFIED` | SYSTEM only, with a machine source | `LIFECYCLE_AUTHORITY`; `check_compatibility` returns `VERIFIED` only from its own deterministic check |
| `APPROVED` | HUMAN only | `LIFECYCLE_AUTHORITY`; lesson ORG scope only after a HUMAN APPROVED entry, never by an agent |
| `FACT` entries | SYSTEM (hooks, CI) or a HUMAN's own statement — never AGENT | `evidence_ledger.domain.validate_entry` |
| `PLAN_APPROVED` `INTEGRATED` `RELEASED` `ROLLED_BACK` | only `ingest_forge_event` (SYSTEM) | `change_management.domain.FORGE_ONLY` — `update_status` rejects them for **every** caller |
| `CANCELLED` (Change Set) | HUMAN | `check_manual_transition` |
| Lifting an `ESCALATION` block | HUMAN | `check_manual_transition`; escalated tasks likewise |
| Risk-tier override | HUMAN; every downgrade logged | `override_risk_tier` |
| Story `READY` `DONE` `ACCEPTED` | nobody directly — derived from SYSTEM-ingested gate results and PO acceptance | no status-setting tool exists; `ingest_*` are SYSTEM-only; plan files carrying `status` are rejected |
| Deployments | SYSTEM (CI) | `record_deployment` |

## 4. Module: evidence_ledger (plan Server 1)

| Tool | Notes |
|---|---|
| `record_evidence` | Identity, `trust_level`, `tool`, `timestamp`, `platform_release_sha` are server-derived. `FACT` needs a source; `INFERENCE` needs existing `input_references`; `QUESTION` needs `metadata.blocking`; `ASSUMPTION` needs `metadata.impact` and `metadata.expires_at`. `answers_entry_id` answers a QUESTION/ASSUMPTION with a new entry (`outcome_status: ANSWERED`). |
| `query_evidence` | Filters: `change_set_id`, `actor_role`, `classification`, `trust_level`. Each row carries a `derived_status` (OPEN / ANSWERED / EXPIRED / CHALLENGED). |
| `record_incident` | ADR 0006 signal only: `skill`, `step`, `failure_class` (from `failure-class-map.json`; required for negative/production), `signal_type`, `signal_source`, `verification_strength`, `pattern_eligible`, `evidence_refs[]` (existing entry_ids) and an optional `note`. Any other field (`prompt`, `files`, `context`, `hypothesis`, …) is rejected. See *Incidents and lessons* below. |
| `query_incidents` | Pointers and classes only — never evidence content. Pattern-eligible only unless `pattern_eligible_only=false`. |
| `record_lesson` | A sanitized, shareable lesson for one `(skill, step, failure_class)` cluster, or its promotion to ORG. Requires `sanitization_result`. |
| `query_lessons` | Lessons by skill / failure_class / scope, each with `last_fired` for pruning. |
| `record_correction` | The only way to correct: a new entry with `parent_entry_id` and `outcome_status: CHALLENGED`. |

**Storage guarantees.** `evidence`, `incidents` and `lessons` are append-only at the storage layer
(`BEFORE UPDATE/DELETE … RAISE(ABORT)` triggers) and **hash-chained**:
`row_hash = sha256(prev_hash + canonical_json(row))`. `ledger_cli.py verify` detects an edited,
deleted or reordered row even if someone drops the triggers.

**Trust derivation.** The caller names a `source_type`; the server maps it to a trust level and
takes the **lowest** of that and every referenced entry's trust (taint propagation — an inference
drawn from a README is no more trusted than the README).

| source_type | trust | source_type | trust |
|---|---|---|---|
| `file_read` | REPOSITORY | `external_fetch` | EXTERNAL_UNSTRUCTURED |
| `command_output` | SYSTEM | `mcp_response` | EXTERNAL_STRUCTURED |
| `tool_output` | SYSTEM | `ci_result`, `scanner_result`, `forge_event`, `platform_policy` | SYSTEM |
| `hook_observation` | SYSTEM | `user_statement`, `org_policy`, `org_document` | ORGANIZATIONAL |
| `repo_file`, `git_metadata`, `agents_md`, `agent_analysis` | REPOSITORY | `issue_text`, `pr_comment`, `web_page`, `external_doc`, `generated_log` | EXTERNAL_UNSTRUCTURED |
| *anything else* | **EXTERNAL_UNSTRUCTURED** (fail-safe) | | |

**Incidents and lessons (ADR 0006).**
- *Incident = signal + pointers.* The case itself stays in this project's ledger under its
  retention; the incident stores only classes and `evidence_refs`. `verification_strength` is
  `{changed_code_coverage, acceptance_criteria_exercised}`; a `positive` signal needs both
  (otherwise record `unverified-positive`, which is never `pattern_eligible`).
- *Notes* (≤280 chars, one line) are for judgment-only failures: `signal_source` must be REVIEWER
  or HUMAN, and the author — server-derived — may not be the agent role or session (`actor_id`)
  that produced any referenced evidence.
- *Lessons* carry `skill, step, failure_class, occurrences{incidents,change_sets,projects},
  what_failed (≤280), advice (≤500), check?, remedy_kind GATE|LINT|SKILL_TEXT|EXAMPLE,
  reproduction_ref?, incident_refs[]` (all from the same cluster). Every lesson needs
  `sanitization_result {passed: true, checker_version, checked_at}` from `sanitize_check.py`;
  anything else is rejected (fail-closed). A cheap built-in guard also rejects local pointers
  (entry / change-set ids, `repo@sha:path`) in lesson text. The failing agent role never
  authors the lesson.
- *Scope* defaults to PROJECT. ORG is a new row with `parent_lesson_id` +
  `approval_entry_id`, where the approval is a HUMAN-authored `APPROVED` evidence entry whose
  `output_references` contain the lesson id. AGENT callers can never write ORG; the ORG row copies
  the approved content (it cannot be edited on the way out). `incident_clusters()` (API) feeds
  improvement-review with the cluster occurrences.
- *Migration 0002* renames the v1 `incidents` table (which held free-text fields) to
  `incidents_v1`: kept local, chain-verified, never queried.

**Retention (`ADLC_EVIDENCE_RETENTION_DAYS`, default 90, minimum 1).** Append-only and deletion
conflict, so payloads are separated from the chain by a **salted content commitment**:
- The chained `evidence` row stores `content_hash = sha256(salt + content)`; the payload and
  its salt live in `evidence_content`, which is not chained.
- After the retention period, `ledger_cli.py purge` (run daily) deletes the payload row. A
  storage trigger refuses to delete payloads younger than the retention period, and payloads are
  immutable.
- `verify` still passes after a purge because the chain never covered the payload; it also
  re-checks every remaining payload against its commitment. With the salt gone, purged content
  cannot be recovered or confirmed by guessing.
- Queries already hide payloads past retention before the purge runs (`content: null`,
  `content_status: EXPIRED`); present payloads report `PRESENT`.
- Entries written before migration 0002 keep inline content (`INLINE`) and are not purgeable.
  Crypto-shredding was rejected: the stdlib has no vetted cipher, and the commitment approach gives
  the same "chain valid, content gone" result with plain deletion.
- Chain hashing omits NULL columns, so `ALTER TABLE … ADD COLUMN` migrations keep existing chains
  valid (tested by upgrading a 0001-only database).

**Completion-criteria view.** `blocking_items(change_set_id)` returns open `blocking: true`
QUESTIONs and unexpired ASSUMPTIONs with impact above LOW — consumed by change_management
through `EvidencePort`.

## 5. Module: change_management (plan Server 2 — multi-repo / parallel only)

| Tool | Notes |
|---|---|
| `create_change_set` | Starts in `DRAFT`. Includes `story_refs[]` (v3.1). |
| `get_change_set` | With `tasks[]`, checkpoints, latest snapshot, dependencies, risk history, handoffs, forge events, status history, and `effective_risk_tier` (uncomputed → HIGH). |
| `update_status` | Lifecycle-checked. Rejects `PLAN_APPROVED` / `INTEGRATED` / `RELEASED` / `ROLLED_BACK` from every caller. `BLOCKED` needs `block_kind` (GATE_FAILED / DEPENDENCY_UNMET / ESCALATION) and returns to the prior state. |
| `ingest_forge_event` | SYSTEM-only; registered only for SYSTEM sessions. See below. |
| `create_snapshot` | Must pin every repository by commit SHA ("latest" rejected). |
| `validate_snapshot_currency` | Caller supplies current HEADs and changed paths (git is not run server-side). Overlap with task paths **or** any always-overlap path class (lockfile, dependency manifest, IaC, migration, schema, CI config, feature flags) → STALE. Missing information → STALE. |
| `record_dependency` | `evidence_level` DECLARED / STATIC / OBSERVED; UNRESOLVED unless explicitly resolved. |
| `compute_risk_tier` | Highest path tier (declared `path-tiers.json` + `control-file-paths.json` + built-in floor where control files are CRITICAL); no paths → HIGH; disagreeing assessments → higher; named reason codes → exactly +1 level; story-type `tier_floor` raises only; recomputation never lowers. `diff_lines` above `ADLC_MAX_DIFF_LINES` → `decompose_required`. |
| `override_risk_tier` | HUMAN-only; every override logged with direction; `override_stats()` gives the downgrade rate. |
| `record_handoff` | `from_role` from the credential. `inputs[].artifact_ref` must be `repo@sha:path` with a `sha256:` content hash; unsourced `claims[]` are rejected (evidence-gate). A security-reviewer REJECT, or a 3rd rejection between the same two roles, blocks the Change Set with ESCALATION. |
| `record_task` / `checkpoint_task` / `record_task_failure` | Tasks embedded in the Change Set. A running task needs its own worktree (no two IN_PROGRESS tasks share one) and DONE dependencies. Failure classes follow the §4.1 catalog: only RETRY classes draw on the 3-attempt cap; scope violation, permission denial and security rejection ESCALATE immediately; context exhaustion REPLANs; a crash RESUMEs from the checkpoint. |

**Forge events → transitions** (approval matrix §4.5):

| Event | In state | Result |
|---|---|---|
| `plan_check_passed`, `codeowners_review` | PLANNED | `PLAN_APPROVED` when the tier's row is satisfied: LOW = VERIFIED plan check; MEDIUM = + code-reviewer REVIEWED ACCEPT; HIGH = + `human:tech-lead`; CRITICAL = + `human:security-lead` and `human:product-owner` |
| `pr_merged` | VERIFYING | `INTEGRATED` once every repository has merged **and** completion criteria hold (no UNRESOLVED dependency, every task DONE, no blocking items from the ledger); otherwise BLOCKED/ESCALATION with the list |
| `pr_merged` | any other | BLOCKED/ESCALATION — a merge bypassed verification |
| `deployment`, `environment_approval` | INTEGRATED | `RELEASED` when deployment succeeded in the release environment and the tier's release approver signed (MEDIUM tech-lead, HIGH security-lead, CRITICAL release-manager) |
| `rollback` | RELEASED | `ROLLED_BACK` (only from RELEASED) |

Every event is recorded (hash-chained) even when it causes no transition. Every transition is
appended to `status_history` and mirrored to the ledger as a SYSTEM FACT via `EvidencePort`.

## 6. Module: work_planning (v3.1 Module 4)

| Tool | Notes |
|---|---|
| `get_work_item` | REQ / EPIC / FEAT / ST / MS as of the last ingested plan commit, with derived status and flags. |
| `query_work_graph` | BFS over `scope`, `time`, `depends_on` edges and Story ↔ Change Set `implements` links. |
| `evaluate_readiness` / `evaluate_done` | Read-only dry run: built-in structural pre-checks plus the `EvaluatorPort`. Never changes status. Without an evaluator the gate cannot pass. |
| `link_change_set` | Agent-callable; the PR body's `Implements: ST-n` line must list the story. |
| `ingest_plan_commit` | SYSTEM-only. Rejects plan files carrying `status`/`ready`/`done`/`accepted`. Recomputes AC hashes, edges and statuses. |
| `ingest_work_event` | SYSTEM-only. `readiness_gate` / `completion_gate` (with the `ac_hash` evaluated), `pr_opened`, `po_acceptance` (`human:product-owner`), `cancelled` (human), `split`. |

Derived status: `DRAFT` (no AC) → `REFINING` → `READY` (passing readiness gate on the *current*
AC hash) → `IN_PROGRESS` (PR opened or Change Set linked) → `IN_VERIFICATION` (all linked
Change Sets VERIFYING or later) → `DONE` (passing completion gate) → `ACCEPTED` (PO acceptance).
`BLOCKED` while a linked Change Set is blocked; `SPLIT`, `CANCELLED` terminal. An AC change after
READY drops the story to `REFINING` with an `AC_FREEZE_VIOLATION` flag.

## 7. Module: contract_registry (plan Server 3)

| Tool | Notes |
|---|---|
| `register_contract` | Types http / grpc / event / schema; policy BACKWARD / FORWARD / FULL / NONE. The provider and each consumer register their own view; versions are immutable. |
| `check_compatibility` | Against **recorded deployments** only. Provider candidate vs every deployed consumer; consumer candidate vs the deployed provider — and, for event contracts, vs every provider version ever deployed in that environment (retained events). Any unknown → INCOMPATIBLE. Compatible → `verification: VERIFIED`, set by the server. |
| `detect_drift` | Declared (explicit version, else deployed, else latest) vs observed spec: missing, undeclared, type-mismatched fields. |
| `record_deployment` | SYSTEM (CI) only; append-only, hash-chained. |

## 8. Persistence

SQLite, one file per module, WAL-free default settings, `BEGIN IMMEDIATE` around chained
appends. Fine for a single-user, single-workspace pilot. For a team or cloud sessions, run the
server remotely behind real authentication; a module whose load or ownership warrants it moves
to its own server (ADR 0001 §Extraction) and can swap SQLite for a server database without any
caller noticing, because nothing outside the module touches its storage.

## 9. Verification

`python -m unittest discover -s tests -t .` from `adlc-mcp/` — stdlib only. Covers append-only
triggers, hash-chain tamper detection (edit and delete), identity non-spoofability, every
privileged-state denial, lifecycle and approval-matrix transitions, fail-safe defaults, the
module-boundary rules, and that each module runs standalone with only its own database.
