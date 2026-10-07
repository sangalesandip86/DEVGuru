# ADLC Platform — Adversarial QA Judge Report

**Change Sets:** CS-7eba012b (Round 1), CS-81cc2531 (Round 2)  
**Date:** 2026-10-07  
**Judge model:** claude-opus-4-6  
**Scenarios run:** 7 (5 Round 1 + 2 Round 2)  
**Total findings:** 50 (30 Round 1 + 20 Round 2)

---

## 1. Executive Summary

**Overall Health Score: 21 / 40** (Below target — strong core enforcement on lifecycle states, significant gaps in fail-safety, role isolation, and documentation)

### Top 3 Critical Findings

1. **CRITICAL — Source type spoofing (F-13):** Agents can pass `source_type="SYSTEM"` or `"HUMAN"` in `record_evidence` and it is **accepted**. The server derives `trust_level` from identity ceiling, so the *stored trust_level* is correctly capped at `EXTERNAL_UNSTRUCTURED` for agents. However, the caller-supplied `source_type` field is stored as-is (`"SYSTEM"`, `"HUMAN"`), creating a misleading record. Any downstream consumer that reads `source_type` instead of `trust_level` will be deceived.

2. **CRITICAL — Stage transitions are fail-open (F-07/08):** `record_transition` logs a `VIOLATION` for invalid transitions (INTAKE→IMPLEMENT, REVIEW→INTAKE, fake stages) but **returns successfully** and **does not block the caller**. An agent can proceed to any stage after recording a violation. The only real gate is CI, not the MCP server.

3. **HIGH — Self-handoff accepted (F-09):** `record_handoff` allows `developer→developer` handoffs with empty payloads. No validation that from_role ≠ to_role, and no payload content check. A role can hand off to itself with `{}`, creating meaningless audit records.

---

## 2. Scenario Results

### Scenario 1: Happy Path (Task Tracker CLI — CS-2e894c06)

| Check | Result | Notes |
|-------|--------|-------|
| Pipeline completes end-to-end | PARTIAL | 6 stages ran, but product-owner agent hit 10-turn limit |
| MCP evidence recorded at each stage | PASS | 8 evidence entries created |
| Handoffs recorded | PASS | 5 handoffs |
| Stage transitions valid | FAIL | All transitions logged as VIOLATION (missing `requirement_id`, `design_decision` outputs) |
| Tests pass | PASS | 27/27 |
| Code review found real bugs | PASS | 3 blocking items found and fixed |
| Manual interventions needed | **4** | (1) agent turn limit, (2) review agents can't write files, (3) evidence requires model_id, (4) OBSERVATION not a valid classification |

### Scenario 2: Edge Cases — Empty/Minimal Input

| Test | Result | Finding ID |
|------|--------|-----------|
| `create_change_set` with `requirements: []` | ERROR: "title, requirements and repositories are required" | F-01 |
| `record_transition` with fake stage names | VIOLATION logged, call succeeds | F-02 |
| `record_evidence` classification=FACT | BLOCKED (PermissionDenied) | — (working correctly) |
| `record_evidence` classification=OBSERVATION | ERROR: not in valid list | F-04 |
| `record_evidence` classification=QUESTION without metadata.blocking | BLOCKED (ValidationError) | — (working correctly) |
| `record_evidence` classification=ASSUMPTION without metadata.impact | BLOCKED — but error only mentions `impact`, not `expires_at` | F-06 |
| `record_evidence` classification=DECISION | PASS | — |
| `record_evidence` classification=RISK | PASS | — |
| `record_evidence` classification=INFERENCE without input_references | BLOCKED (ValidationError) | — (working correctly) |
| `record_evidence` classification=PROPOSAL | PASS | — |
| `query_evidence` with non-existent CS | Returns empty `[]` | F-18 |
| `query_evidence` with fake classification | Returns empty `[]` | F-19 |
| `evaluate_readiness` with fake story | NotFound error | — (working correctly) |

### Scenario 3: Gate Bypass — Skip Stages

| Test | Result | Finding ID |
|------|--------|-----------|
| INTAKE → IMPLEMENT (skip 2 stages) | VIOLATION logged, **not blocked** | F-07 |
| REVIEW → INTAKE (backward) | VIOLATION logged, **not blocked** | F-08 |
| Self-handoff (developer → developer) | **ACCEPTED** | F-09 |
| Handoff to fake role | BLOCKED (ValidationError) | — (working) |
| Handoff with empty payload `{}` | **ACCEPTED** | F-10 |
| Duplicate Change Set title | **ACCEPTED** (new CS-11584845 created) | F-12 |
| `update_status` to PLAN_APPROVED | BLOCKED (PermissionDenied) | — (working) |
| `update_status` to INTEGRATED | BLOCKED (PermissionDenied) | — (working) |
| `update_status` to RELEASED | BLOCKED (PermissionDenied) | — (working) |
| `update_status` BLOCKED without block_kind | BLOCKED (ValidationError) | — (working) |
| `update_status` DRAFT → IN_PROGRESS | ERROR: "invalid transition" | F-20 |
| `update_status` DRAFT → ACTIVE | ERROR: "invalid transition" | F-20 |
| `lifecycle_state=APPROVED` by agent | BLOCKED (PermissionDenied) | — (working) |
| `lifecycle_state=VERIFIED` by agent | BLOCKED (PermissionDenied) | — (working) |
| `lifecycle_state=REVIEWED` by agent | ACCEPTED | — (working, agents may set REVIEWED) |
| `validate_transition` (dry-run) | Returns correct disallowance info | — (working) |

### Scenario 4: Role Boundary — Permission Leaks

| Role | Intended Restriction | Actual Enforcement | Finding |
|------|---------------------|-------------------|---------|
| code-reviewer | Read-only (no Write/Edit) | **ENFORCED** — agent type definition restricts to Read, Grep, Glob + MCP tools | — (working) |
| security-reviewer | Read-only (no Write/Edit) | **ENFORCED** — agent type restricts to Read, Grep, Glob, Bash + MCP tools | — (working) |
| qa-derive | Implementation-blind (`denied_paths.read: [src/**]`) | **NOT ENFORCED** — has full Read access. `denied_paths` is prose only, Read tool has no path-deny. | F-22, F-23 |
| developer | Cannot set APPROVED via MCP | **ENFORCED** at MCP server level | — (working) |
| All roles | Per-role identity in MCP | **NOT ENFORCED** — all agents are `agent:developer` | F-24 |
| All roles | `can_modify` path restrictions | **NOT ENFORCED** — no mechanism restricts write paths beyond control-file deny | F-29 |
| Reviewers | Different model family from implementer | **NOT ENFORCED** — no check mechanism | F-30 |
| All roles | `dist/` agent files with `disallowedTools`/`maxTurns` | **ABSENT** — `dist/claude/` is empty, generator never run | F-23 |

### Scenario 5: Data Integrity — MCP Tool Abuse

| Test | Result | Finding ID |
|------|--------|-----------|
| JSON injection in content field | Stored as literal string, not parsed. Safe. | — (working) |
| `source_type="SYSTEM"` by agent | **ACCEPTED** — stored as `source_type: SYSTEM`, `trust_level: EXTERNAL_UNSTRUCTURED` | F-13 |
| `source_type="HUMAN"` by agent | **ACCEPTED** — stored as `source_type: HUMAN`, `trust_level: EXTERNAL_UNSTRUCTURED` | F-14 |
| Journal event_type `task.complete` | REJECTED | F-15 |
| Journal event_type `run.start` | REJECTED | F-15 |
| Journal event_type `run.end` | REJECTED | F-15 |
| Journal event_type `run.complete` | REJECTED | F-15 |
| Journal event_type `gate.pass` | REJECTED | F-15 |
| Journal event_type `gate.fail` | REJECTED | F-15 |
| Journal event_type `error` | REJECTED | F-15 |
| Journal event_type `handoff` | REJECTED | F-15 |
| Journal event_type `violation` | REJECTED | F-15 |
| Journal event_type `task.start` | ACCEPTED | — |
| Journal event_type `stage.enter` | ACCEPTED | — |
| Journal event_type `stage.exit` | ACCEPTED | — |
| Journal event_type `task.checkpoint` | ACCEPTED | — |
| `get_change_set` non-existent ID | NotFound (correct) | — |
| BLOCKED with proper block_kind from DRAFT | ACCEPTED — DRAFT→BLOCKED works | F-21 |

---

## 3. Findings Table

| ID | Severity | Category | Scenario | Description | Expected | Actual |
|----|----------|----------|----------|-------------|----------|--------|
| F-01 | LOW | error-handling | S2 | `create_change_set` with `requirements: []` says "required" | "requirements must not be empty" | "title, requirements and repositories are required" |
| F-02 | CRITICAL | enforcement-gap | S2/S3 | `record_transition` with invalid stages logs VIOLATION but succeeds | Return error, prevent further progress | Returns `{allowed: false}` but call succeeds, no blocking |
| F-04 | MEDIUM | documentation | S2 | OBSERVATION not a valid classification despite being commonly referenced in ADLC docs | Either add OBSERVATION or update all docs/prompts | Error: "must be one of (FACT, INFERENCE, ASSUMPTION, PROPOSAL, QUESTION, DECISION, RISK)" |
| F-06 | LOW | error-handling | S2 | ASSUMPTION error mentions `impact` but not `expires_at` | List all missing required metadata fields | Only says "require metadata.impact" |
| F-07 | CRITICAL | enforcement-gap | S3 | INTAKE→IMPLEMENT skip succeeds (logged as VIOLATION) | Block the transition; return error | VIOLATION logged, call returns successfully |
| F-08 | CRITICAL | enforcement-gap | S3 | REVIEW→INTAKE backward transition succeeds | Block backward transitions | VIOLATION logged, call returns successfully |
| F-09 | HIGH | data-integrity | S3 | Self-handoff developer→developer accepted | Reject from_role == to_role | Accepted with `HO-8e718dab29` |
| F-10 | MEDIUM | data-integrity | S3 | Handoff with empty payload `{}` accepted | Require at least summary or artifact reference | Accepted with empty payload |
| F-12 | MEDIUM | data-integrity | S3 | Duplicate Change Set titles allowed | Warn or reject duplicate titles | Created CS-11584845 with same title as CS-7eba012b |
| F-13 | CRITICAL | enforcement-gap | S5 | Agent can claim `source_type="SYSTEM"` | Reject or override source_type for AGENT callers | Accepted; stored as `source_type: SYSTEM` (trust_level correctly capped) |
| F-14 | CRITICAL | enforcement-gap | S5 | Agent can claim `source_type="HUMAN"` | Reject or override source_type for AGENT callers | Accepted; stored as `source_type: HUMAN` (trust_level correctly capped) |
| F-15 | HIGH | documentation | S5 | Valid journal event_types are undocumented | Document all valid types in tool description | Only discoverable by reading source code |
| F-16 | MEDIUM | documentation | S2 | Valid evidence classifications not in tool description | List valid values in tool schema | Only in error message after failed call |
| F-17 | MEDIUM | documentation | S3 | Valid Change Set status transitions undocumented | Document DRAFT→SCOPED→PLANNED→... flow | Only discoverable from source code |
| F-18 | LOW | error-handling | S2 | `query_evidence` with non-existent CS returns empty `[]` | Return NotFound or include warning | Silent empty result |
| F-19 | LOW | error-handling | S2 | `query_evidence` with fake classification returns `[]` | Validate classification parameter | Silent empty result |
| F-20 | MEDIUM | documentation | S3 | DRAFT→IN_PROGRESS and DRAFT→ACTIVE fail; only DRAFT→SCOPED is valid | Document valid transitions or include them in error | Error only says "invalid transition DRAFT -> X" |
| F-21 | LOW | consistency | S5 | DRAFT can transition directly to BLOCKED | BLOCKED should only be reachable from active states | DRAFT→BLOCKED accepted (FORWARD map has no explicit active-only check for BLOCKED from DRAFT) |
| F-22 | HIGH | role-boundary | S4 | code-reviewer and security-reviewer tool restrictions work (no Write/Edit). But qa-derive `denied_paths.read: [src/**]` is **not enforced** — role spec says "implementation paths denied at the tool-permission level" but Read tool has no path-deny capability | `denied_paths` rendered as tool-level blocks | Prose only; qa-derive can read any file |
| F-23 | HIGH | role-boundary | S4 | `dist/claude/` and `dist/copilot/` are **empty** — `generate_agents.py` never run on current specs. Agent types come from session-level config, not generated files. `disallowedTools`, `maxTurns` absent. | Generated agent files with enforced constraints | Empty directories |
| F-24 | HIGH | enforcement-gap | S4 | MCP server sees all agents as `actor_type=AGENT, actor_id=agent:developer` regardless of role. Cannot distinguish code-reviewer from developer. | Per-role credentials | Single credential for all roles |
| F-29 | MEDIUM | enforcement-gap | S4 | `can_modify` constraints (e.g., code-reviewer → `docs/reviews/**` only) are advisory prose. Nothing restricts WHERE an agent writes besides managed-settings deny list for control files. | Path-scoped write restrictions | No mechanism exists |
| F-30 | MEDIUM | enforcement-gap | S4 | `model_family_constraint: "different-from-implementer"` on reviewers is not enforced. No mechanism to check reviewer model ≠ implementer model. | Automated model-family check | Guideline only |
| F-25 | MEDIUM | missing-feature | S1 | Product-owner agent hit 10-turn limit on INTAKE | Complex stages need higher turn budgets | Agent exhausted before completing work |
| F-26 | MEDIUM | consistency | S1 | All stage transitions log as VIOLATION (missing required_outputs) | Conductor should produce required outputs per stage | `requirement_id`, `design_decision`, `plan_id` etc. never generated |
| F-27 | LOW | consistency | S5 | `record_evidence` error message for FACT says "Record an INFERENCE" | Helpful, but implies INFERENCE is always the alternative | Suggest all valid alternatives |
| F-28 | INFO | documentation | S5 | Valid journal event_types (from source): `session.join`, `session.leave`, `session.heartbeat`, `task.start`, `task.claim`, `task.deliver`, `task.abandon`, `task.checkpoint`, `stage.enter`, `stage.exit`, `stage.gate_pass`, `stage.gate_fail`, `evidence.fact`, `evidence.inference`, `evidence.decision`, `coord.intent_claim`, `coord.intent_release`, `coord.conflict`, `coord.message` | Documented in tool description | Only in source code at `event_journal/domain.py:7-12` |

---

## 4. Scoring Matrix

| Dimension | Score | Justification |
|-----------|-------|---------------|
| **Completeness** | 3/5 | All 10 stages defined, transition graph works, MCP tools functional. But DESIGN stage exists in graph but never used by conductor skill. OBSERVATION classification missing despite being referenced. |
| **Enforcement** | 2/5 | Lifecycle states (APPROVED/VERIFIED) properly blocked. FACT writing blocked for agents. But stage transitions are fail-open (VIOLATION logged, not blocked). Source type spoofing accepted. |
| **Error Quality** | 3/5 | Most errors are clear and actionable (FACT, QUESTION, lifecycle_state). Some are misleading (empty requirements says "required" not "empty"). ASSUMPTION error incomplete. |
| **Consistency** | 2/5 | Change Set statuses (DRAFT→SCOPED→PLANNED) don't map to stage names (INTAKE→ARCHITECTURE→PLAN). Two separate state machines with no documented relationship. OBSERVATION used in prompts but not valid. |
| **Fail-Safety** | 2/5 | Key areas fail safe: lifecycle states, FACT classification, forge-only statuses. But stage transitions fail open. Query with bad filters returns empty (silent failure). Source type accepted without validation against identity. |
| **Idempotency** | 4/5 | Evidence entries get unique IDs. Change Sets get unique IDs. Journal entries are hash-chained. Duplicate titles allowed (no uniqueness constraint, but doesn't corrupt data). |
| **Documentation** | 2/5 | Tool descriptions lack valid values for: event_types, classifications, status transitions, source_types. All discoverable only from source code or error messages. The tool description for `record_evidence` hints at rules but doesn't enumerate valid values. |
| **Role Isolation** | 3/5 | MCP-level enforcement works (APPROVED blocked for agents). But tool-level isolation relies on agent specs (prose), not managed-settings enforcement. All agents share one credential (`agent:developer`). qa-derive can read implementation code. |

**Total: 21 / 40**

---

## 5. Recommendations (prioritized)

### P0 — Critical (fix before pilot)

1. **Make `record_transition` blocking for invalid transitions.** Return an error (not just `allowed: false`) so callers cannot proceed. Or: require a valid prior transition before allowing stage work. Currently the gate is purely CI-side, making the MCP server's transition tracking advisory-only.

2. **Reject or override `source_type` for AGENT callers.** The server correctly caps `trust_level` via identity ceiling, but storing a caller-supplied `source_type="SYSTEM"` creates misleading records. Either validate `source_type` against `IDENTITY_TRUST_CEILING` or override it to "AGENT" for agent callers.

3. **Implement per-role credentials for MCP.** All agents currently authenticate as `agent:developer`. The server cannot distinguish a code-reviewer from a developer. This makes role-based enforcement impossible at the MCP level.

### P1 — High (fix before scale)

4. **Validate self-handoffs.** Reject `to_role == from_role` or require explicit justification.

5. **Document all valid enum values in tool descriptions.** Add valid values for: event_types (20 types), classifications (7), status transitions (DRAFT→SCOPED→...), source_types (18+). Agents currently discover these only by trial-and-error.

6. **Enforce qa-derive implementation-blindness.** Either restrict Read tool to `plans/`, `docs/`, and test paths, or use managed-settings `disallowedTools` to block Read on `src/` paths.

7. **Add OBSERVATION classification** or systematically replace all references to it in documentation and prompts with the correct classification (INFERENCE or RISK).

### P2 — Medium (improve quality)

8. Require non-empty `payload` for handoffs (at minimum, a `summary` field).
9. Add a uniqueness warning for duplicate Change Set titles.
10. Improve error messages: ASSUMPTION should list all missing metadata fields; empty requirements should say "must not be empty".
11. Document the relationship between Change Set statuses (DRAFT→SCOPED→...) and stage names (INTAKE→ARCHITECTURE→...).
12. Consider raising agent turn limits for complex stages like INTAKE.

### P3 — Low (polish)

13. `query_evidence` should validate the `classification` parameter against known values.
14. Fix DRAFT→BLOCKED transition — BLOCKED should only be reachable from active statuses.
15. Add valid-values hints to error messages for status transitions.

---

# Round 2 — Scenarios 6–7 (2026-10-07)

**Change Set:** CS-81cc2531  
**Evidence:** ENTRY-fffd269945e2  
**New findings:** 20

## Scenario 6: Concurrency & Task Lifecycle Abuse

**Goal:** Test `record_task`, `claim_task`, `checkpoint_task`, `record_task_failure`, `start_worker`, and `get_worker_status` with adversarial inputs.

### Tests & Results

| # | Test | Tool | Result | Finding |
|---|------|------|--------|---------|
| 1 | Create task with status `RUNNING` | `record_task` | REJECTED: "status must be one of (PENDING, IN_PROGRESS, DONE, BLOCKED)" | F-31: Valid statuses undocumented; `RUNNING` ≠ `IN_PROGRESS` |
| 2 | Same task ID, different owner_role | `record_task` (×2) | ACCEPTED: architect overwrote developer | **F-32: Silent owner reassignment** |
| 3 | Empty string as task_id | `record_task` | ACCEPTED: task with `id: ""` created | **F-33: Empty task_id accepted** |
| 4 | Fake owner_role "ceo" | `record_task` | REJECTED with valid role list | Good validation |
| 5 | Claim nonexistent task | `claim_task` | ACCEPTED: `{claimed: true}` | **F-35: Phantom task claiming** |
| 6 | Claim empty task_id | `claim_task` | REJECTED: "task_id is required" | Good (but contrast with record_task accepting "") |
| 7 | Fake failure_class | `record_task_failure` | REJECTED with valid list (9 classes) | F-38: Valid classes undocumented |
| 8 | Valid failure (TOOL_TRANSIENT) | `record_task_failure` | ACCEPTED: returns `{policy: RETRY, action: RETRY}` | Good — retry policy works |
| 9 | Checkpoint with fake snapshot | `checkpoint_task` | REJECTED: "snapshot SNAP-nonexistent not found" | Good validation |
| 10 | Checkpoint nonexistent task | `checkpoint_task` | REJECTED: "task CS-81cc2531/TASK-NEVER-RECORDED not found" | Good validation |
| 11 | Nonexistent work item | `start_worker` | Returns `{error: "..."}` in body | **F-48: Inconsistent error pattern** |
| 12 | Nonexistent plan_id | `get_worker_status` | Returns empty `{workers:[], running:0}` | **F-44: Fail-open on bad plan** |
| 13 | Mark task DONE then regress to PENDING | `record_task` (×2) | ACCEPTED both times | **F-49: Task status regression** |
| 14 | Reassign owner without handoff | `record_task` | ACCEPTED silently | **F-50: No handoff required** |

### Scenario 6 Verdict

Task lifecycle management has **solid input validation** (role names, failure classes, checkpoint references) but **weak state integrity** (status regression, silent owner reassignment, phantom claiming). The `record_task` upsert pattern is the root cause — it treats every call as a full overwrite rather than a state transition.

## Scenario 7: Dependency, Risk Tier & State Reconstruction Abuse

**Goal:** Test `record_dependency`, `compute_risk_tier`, `fold_state`, `validate_snapshot_currency`, `record_correction`, `link_change_set`, and `update_status` preconditions.

### Tests & Results

| # | Test | Tool | Result | Finding |
|---|------|------|--------|---------|
| 1 | Self-dependency (source == target) | `record_dependency` | ACCEPTED as DEP-cbebe80c | **F-39: Self-referential dependency** |
| 2 | Confidence > 1.0 | `record_dependency` | REJECTED: "confidence must be within [0, 1]" | Good validation |
| 3 | Confidence < 0 | `record_dependency` | REJECTED: same | Good validation |
| 4 | Fake evidence_level | `record_dependency` | REJECTED: "must be DECLARED, STATIC or OBSERVED" | Good validation |
| 5 | Empty paths | `compute_risk_tier` | Returns HIGH (uncomputable) | Correct per docs |
| 6 | Fake reason_codes | `compute_risk_tier` | REJECTED with valid closed list | Good validation |
| 7 | Agent sets tier_floor=CRITICAL | `compute_risk_tier` | ACCEPTED: LOW→CRITICAL | **F-41: Risk tier inflation** |
| 8 | Nonexistent run_id | `fold_state` | Returns empty state `{}` | **F-42: Fail-open** |
| 9 | SCOPED→PLANNED (no plan exists) | `update_status` | ACCEPTED | **F-46: No precondition checks** |
| 10 | PLANNED→EXECUTING (skip approval) | `update_status` | REJECTED: "invalid transition PLANNED -> EXECUTING" | Good — must go through PLAN_APPROVED |
| 11 | Correction on nonexistent entry | `record_correction` | REJECTED: "entry not found" | Good validation |
| 12 | Link nonexistent story | `link_change_set` | REJECTED: "story not found" | Good validation |
| 13 | Nonexistent snapshot | `validate_snapshot_currency` | REJECTED: "snapshot not found" | Good validation |
| 14 | Fake SHA in snapshot | `create_snapshot` | REJECTED: "commit SHAs required" | Good validation |
| 15 | Single-char evidence content | `record_evidence` | ACCEPTED: "A" stored | **F-47: No min content length** |
| 16 | Fake event_type in query | `query_journal` | Returns empty `[]` | **F-45: No event_type validation** |

### Scenario 7 Verdict

Dependency and snapshot tools have **excellent input validation** (bounds, enum, existence checks). The gaps are in **semantic validation**: self-dependencies, agent-controlled risk inflation, and missing precondition checks on status transitions. The `fold_state` fail-open pattern is concerning for resume workflows — a typo in `run_id` silently returns empty state instead of alerting the caller.

## Round 2 Summary

| Severity | Count | Key Pattern |
|----------|-------|-------------|
| CRITICAL | 3 | Phantom claiming, risk inflation, task regression |
| HIGH | 4 | Silent owner reassignment, self-dependency, missing preconditions |
| MEDIUM | 6 | Empty IDs, fail-open queries, inconsistent errors |
| LOW | 3 | Undocumented enums |
| GOOD | 14 | Strong input validation on bounds, enums, existence |

**Updated Health Score: 19/40** (down from 21/40 — task lifecycle and risk tier gaps are significant)

See `adlc-issues.md` for the full consolidated tracker with fix priorities.
