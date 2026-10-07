# ADLC Platform — Full Evaluation Report

**Date:** 2026-10-07  
**Evaluator:** Adversarial QA Judge (claude-opus-4-6)  
**Scope:** MCP infrastructure, artifact quality, code correctness, test effectiveness, mutation testing  
**Projects generated:** 12 (Python CLI tools + TCP backend server)  
**Total tests written:** 1,019  
**Total tests passing:** 1,019 (100%)  
**Mutation test kill rate:** 66.7–78% (avg 71.9%)

---

## 1. Executive Summary

The ADLC platform was evaluated across four axes:

| Axis | Scope | Score | Grade |
|------|-------|-------|-------|
| MCP Infrastructure (Rounds 1–2) | 50 findings across 7 adversarial scenarios | 19/40 | **D+** |
| Artifact Quality (Round 3) | 15 findings across 7 dimensions, 2 projects | 56/70 (80%) | **B** |
| Code Generation (Round 4) | 12 projects, 1,019 tests, all passing | 100% pass | **A** |
| Mutation Testing (Round 4) | 4 projects, 64 total mutations | 66.7–78% kill (avg 71.9%) | **C** |

**Bottom line:** The ADLC pipeline produces **functional, well-structured software** with **comprehensive test suites**. However, the MCP enforcement layer has **critical fail-open gaps** (invalid transitions succeed, agents can spoof metadata), and test suites have **systematic blind spots** that mutation testing exposes — particularly around output formatting, state-change verification, and boundary conditions.

### Top 5 Actionable Findings

1. **Stage transitions fail-open (F-02/07/08):** `record_transition` logs VIOLATION but returns success. Invalid/backward/skipped transitions proceed unchecked.
2. **No test-design-to-code gate (AF-11):** qa-derive produces test designs but nothing verifies the developer implements them. 29% of designed tests were skipped.
3. **Agents can inflate risk tier (F-41):** Any agent can set `tier_floor=CRITICAL`, triggering unnecessary reviews for trivial changes.
4. **Task status regression allowed (F-49):** DONE tasks can be flipped back to PENDING with no validation.
5. **Mutation survivors at 22–33%:** Tests verify return values but not state changes (`completed_at` not checked, `who-paid-whom` not validated, in-memory SQLite hides missing commits).

---

## 2. MCP Infrastructure Findings (50 Findings)

**Change Sets tested:** CS-7eba012b (Round 1), CS-81cc2531 (Round 2)  
**Health Score:** 19/40  
**Full report:** [adlc-judge-report.md](adlc-judge-report.md)

### 2.1 Severity Distribution

| Severity | Count | Key Pattern |
|----------|-------|-------------|
| CRITICAL | 8 | Fail-open enforcement: transitions, claims, risk tier, task regression |
| HIGH | 10 | Data integrity: silent overwrites, self-references, missing gates |
| MEDIUM | 14 | Consistency: fail-open queries, missing validations, format issues |
| LOW | 9 | Documentation: undocumented enums, unclear error messages |
| INFO | 1 | Source-only documentation |
| CLOSED | 1 | F-34 works correctly |

### 2.2 Critical Findings Summary

| ID | Component | Issue | Root Cause |
|----|-----------|-------|------------|
| F-02 | `record_transition` | Invalid stage names succeed (logged as VIOLATION) | Returns result dict instead of raising error |
| F-07 | `record_transition` | INTAKE→IMPLEMENT skip succeeds | Same: VIOLATION logged but call succeeds |
| F-08 | `record_transition` | REVIEW→INTAKE backward transition succeeds | Same: fail-open by design |
| F-13 | `record_evidence` | Agent can set `source_type="SYSTEM"` | No validation of source_type against actor_type |
| F-14 | `record_evidence` | Agent can set `source_type="HUMAN"` | Same |
| F-35 | `claim_task` | Nonexistent task IDs can be claimed | No existence check before mutex grant |
| F-41 | `compute_risk_tier` | Agent can inflate risk to CRITICAL via `tier_floor` | No actor_type check on tier_floor |
| F-49 | `record_task` | DONE→PENDING regression allowed | Upsert with no forward-only status check |

### 2.3 What Works Well

| Area | Verified |
|------|----------|
| Lifecycle state enforcement (APPROVED/VERIFIED blocked for agents) | Yes |
| FACT classification blocked for agents | Yes |
| Hash-chained journal (tamper detection) | Yes |
| Trust level ceiling (IDENTITY_TRUST_CEILING) | Yes |
| Forge-only statuses (PLAN_APPROVED, INTEGRATED, etc.) | Yes |
| Role-specific tool restrictions (code-reviewer, security-reviewer) | Yes |
| Confidence bounds on dependencies | Yes |
| Retry policy per failure class | Yes |

---

## 3. Artifact Quality Findings (15 Findings)

**Projects:** Task Tracker CLI (CS-2e894c06), Unit Converter CLI (CS-81cc2531)  
**Score:** 56/70 (80%)  
**Full report:** [adlc-artifact-judge-report.md](adlc-artifact-judge-report.md)

### 3.1 Findings Table

| ID | Severity | Dimension | Description |
|----|----------|-----------|-------------|
| AF-01 | HIGH | Code Correctness | `stats` output has duplicate "Done:" label (count + percentage) |
| AF-02 | HIGH | Code Correctness | Error messages go to stdout, not stderr (violates NFR-004) |
| AF-06 | HIGH | Test Quality | 10 of 35 designed test cases not implemented (29% gap) |
| AF-11 | HIGH | Pipeline Gap | No gate checking test-design-to-test-code coverage |
| AF-03 | MEDIUM | Code Correctness | Empty description accepted by `add` command |
| AF-04 | MEDIUM | Code Correctness | Long descriptions break table formatting |
| AF-07 | MEDIUM | Test Quality | All 5 edge cases from test design skipped entirely |
| AF-08 | MEDIUM | Architecture | `done_task`/`stats` bypass Task model (raw dict mutation) |
| AF-10 | MEDIUM | Review Quality | Code review missed duplicate label and stderr routing bugs |
| AF-05 | LOW | Code Correctness | Stats percentage truncates instead of rounding |
| AF-09 | LOW | Architecture | Command functions return formatted strings (minor coupling) |
| AF-12 | LOW | Code Correctness | Unit Converter: input value displayed as float (`100.0`) |
| AF-13 | LOW | Code Correctness | Unit Converter: singular input displayed as plural |
| AF-14 | LOW | Code Correctness | argparse error exits code 2, not 1 |
| AF-15 | INFO | Code Correctness | Same-unit conversion shows inconsistent decimals |

### 3.2 Per-Dimension Scores

| Dimension | Task Tracker | Unit Converter | Average |
|-----------|-------------|----------------|---------|
| Requirement Fidelity | 5/5 | 4/5 | 4.5 |
| Architecture-Code Alignment | 3/5 | 5/5 | 4.0 |
| Plan Coverage | 5/5 | N/A | 5.0 |
| Code Correctness | 3/5 | 4/5 | 3.5 |
| Test Quality | 3/5 | 5/5 | 4.0 |
| Review Effectiveness | 4/5 | N/A | 4.0 |
| Cross-Artifact Consistency | 3/5 | N/A | 3.0 |

---

## 4. Per-Project Results

### 4.1 Test Results Summary

| # | Project | Type | Tests | Pass | Bugs Found | Mutation Score |
|---|---------|------|-------|------|------------|---------------|
| 1 | Note Search CLI | Python CLI | 123 | 123 | — | — |
| 2 | Cron Parser CLI | Python CLI | 86 | 86 | — | — |
| 3 | Unit Converter CLI | Python CLI | 29 | 29 | Float display, plural | 73.3% |
| 4 | Task Tracker CLI | Python CLI | 27 | 27 | Duplicate label, stderr | 72% |
| 5 | Expense Splitter CLI | Python CLI | 88 | 88 | — | 78% |
| 6 | Password Vault CLI | Python CLI | 82 | 82 | Dead code `_get_key()` | — |
| 7 | CSV Transformer CLI | Python CLI | 95 | 95 | N/A numeric filter bug | — |
| 8 | Log Analyzer CLI | Python CLI | 89 | 89 | — | — |
| 9 | Quiz Engine CLI | Python CLI | 106 | 106 | — | — |
| 10 | Habit Tracker CLI | Python CLI | 87 | 87 | — | — |
| 11 | FSM Engine CLI | Python CLI | 89 | 89 | — | — |
| 12 | Chat Server | TCP Backend | 98 | 98 | `__main__.py` always-run bug, dead code `sanitize_sql_param` | 66.7% |

**Total: 1,019 tests, 1,019 passing (100%)**

### 4.2 Project Architecture Diversity

| Category | Projects |
|----------|----------|
| Pure CLI (file I/O) | Note Search, Cron Parser, Task Tracker, Log Analyzer, CSV Transformer |
| CLI with encryption | Password Vault |
| CLI with financial logic | Expense Splitter |
| CLI with game/quiz logic | Quiz Engine |
| CLI with time-series data | Habit Tracker |
| State machine engine | FSM CLI |
| TCP server (threading + SQLite) | Chat Server |
| Unit conversion (math) | Unit Converter |

### 4.3 Notable Project-Specific Findings

**Password Vault CLI:**
- Dead code: `_get_key()` method exists but is never called (82 tests, none exercise it)
- Encryption implementation uses correct patterns (Fernet, PBKDF2)

**CSV Transformer CLI:**
- **Bug found:** N/A values in numeric filter — string fallback comparison `"N/A" > "0"` is True
- Fixed: return False when filter value is numeric but cell isn't parseable

**Chat Server (Backend):**
- TCP socketserver + threading + SQLite (WAL mode) architecture
- 8 commands: JOIN, MSG, LEAVE, ROOMS, WHO, DM, HISTORY, KICK
- Thread-safe room state with `threading.Lock`
- Thread-local SQLite connections for WAL mode
- Token-bucket rate limiter per user
- **Bug:** `__main__.py:4` has `if __name__ == "__main__" or True:` — always runs server on import
- Integration tests use real TCP connections on random ports

**Quiz Engine CLI:**
- Most tests of any project (106)
- Scoring engine, quiz validation, multiple question types
- Good separation of concerns

**FSM Engine CLI:**
- State machine definition and execution
- Transition validation, guard conditions
- 89 tests with comprehensive edge cases

---

## 5. Mutation Testing Results

### 5.1 Summary Across Projects

| Project | Mutations | Killed | Survived | Kill Rate |
|---------|-----------|--------|----------|-----------|
| Task Tracker CLI | 11 | 8 | 3 | 72% |
| Expense Splitter CLI | 14 | 11 | 3 | 78% |
| Unit Converter CLI | 15 | 11 | 4 | 73.3% |
| Chat Server | 24 | 16 | 8 | 66.7% |
| **Total** | **64** | **46** | **18** | **71.9%** |

### 5.2 Surviving Mutations (Test Gaps)

| ID | Project | Mutation | Why It Survived |
|----|---------|----------|-----------------|
| MF-01 | Task Tracker | Don't set `completed_at` on done | No test checks `completed_at` is set |
| MF-02 | Task Tracker | Skip `_validate_shape()` | Validation added in review, never tested |
| MF-05 | Task Tracker | Skip mkdir on first load | No test creates file in nested nonexistent dir |
| MF-03 | Expense Splitter | Balance threshold 0.005→0.5 | No test with balances between $0.01-$0.49 |
| MF-04 | Expense Splitter | Wrong settle message direction | Tests check amounts but not who-paid-whom |
| MF-06 | Expense Splitter | 1 decimal instead of 2 in balances | `$10.00` matches both `:.1f` and `:.2f` |
| — | Unit Converter | Precision change (round to 1 decimal) | Round inputs give same result with fewer decimals |
| — | Unit Converter | Wrong alias mapping | No alias-specific validation test |
| — | Unit Converter | `type=int` instead of `type=float` | No decimal-input CLI test |
| — | Unit Converter | Remove category validation | No test for cross-category conversion error |
| — | Chat Server | Remove thread lock from rate_limiter.allow() | All rate limiter tests single-threaded |
| — | Chat Server | Remove conn.commit() from save_message() | In-memory SQLite single-connection hides missing commits |
| — | Chat Server | Remove conn.commit() from create_room() | Same in-memory SQLite reason |
| — | Chat Server | Remove rate limiter check from _do_msg() | No integration test triggers rate limiting |
| — | Chat Server | Remove join broadcast notification | No test verifies join notification sent to room |
| — | Chat Server | Remove empty room cleanup on leave | No test checks rooms dict after last user leaves |
| — | Chat Server | HISTORY --n boundary off-by-one | No test sends HISTORY --n without a value |
| — | Chat Server | sanitize_sql_param is dead code | Never called; parameterized queries used |

### 5.3 Common Patterns in Surviving Mutations

1. **`assertIn` is the enemy of mutation testing** (all projects)
   - Tests use `assertIn("$5.00", output)` which passes for both `"Alice paid Bob $5.00"` and `"Bob paid Alice $5.00"`
   - Fix: Use `assertEqual` or regex with capture groups

2. **Side-effect testing is systematically weak** (all projects)
   - Tests verify return values/messages but not persisted state changes
   - `completed_at` set? JSON file updated? Room state cleaned up?
   - Fix: Assert on persisted state after write operations

3. **Boundary values are undertested** (Expense Splitter, Unit Converter)
   - Threshold mutations survive because no test exercises the exact boundary
   - Fix: Add boundary-value tests for every numeric constant

4. **Dead validation code** (Task Tracker)
   - Code review added `_validate_shape()` but no corresponding test
   - Fix: Require test for every code-review fix

---

## 6. Cross-Cutting Patterns

### 6.1 Where the ADLC Pipeline Excels

| Strength | Evidence |
|----------|----------|
| **Requirement decomposition** | All projects have correct, traceable requirement-to-story-to-code flow |
| **Code structure** | Clean separation of concerns across all 12 projects (CLI, logic, storage, models) |
| **Test generation** | 1,019 tests, 100% pass rate, good naming conventions |
| **Working software** | Every project produces correct output for its happy-path requirements |
| **Diverse architecture support** | Successfully built CLI tools, TCP servers, encryption apps, state machines |

### 6.2 Systemic Weaknesses

| Weakness | Severity | Evidence | Impact |
|----------|----------|----------|--------|
| **Output formatting bugs survive** | HIGH | AF-01, AF-12, AF-13, AF-15 | Display bugs in 3/12 projects |
| **No test-design-to-code gate** | HIGH | AF-06, AF-11 | 29% of designed tests skipped |
| **Error routing inconsistent** | HIGH | AF-02 | stdout vs stderr wrong in 1/12 projects |
| **Edge cases systematically skipped** | MEDIUM | AF-07, mutation survivors | All 5 edge cases skipped in Task Tracker |
| **Review misses output bugs** | MEDIUM | AF-10 | Code reviewer reads source, doesn't run code |
| **Input validation gaps** | MEDIUM | AF-03 | Empty inputs accepted without checking |
| **Mutation kill rate below 80%** | MEDIUM | 66.7–78% across 4 projects | 22–33% of introduced bugs survive all tests |

### 6.3 Infrastructure vs. Artifact Quality

| Axis | Score | Interpretation |
|------|-------|----------------|
| MCP Infrastructure | 19/40 (47%) | Enforcement layer is incomplete — fail-open transitions, metadata spoofing, missing gates |
| Generated Artifacts | 56/70 (80%) | Pipeline produces good-quality software despite weak enforcement |
| Test Suites | 71.9% mutation kill | Tests catch most bugs but systematically miss state changes, commits, and formatting |

**Key insight:** The ADLC pipeline's artifact quality (80%) is significantly better than its infrastructure quality (47%). The pipeline produces good software *despite* weak enforcement — but this means quality depends on the LLM agent's judgment rather than verified gates, which won't scale reliably.

---

## 7. Prioritized Fix List

### CRITICAL — Fix before pilot (Sprint 1)

| # | Fix | Findings | Effort |
|---|-----|----------|--------|
| 1 | Make `record_transition` return error for invalid transitions | F-02, F-07, F-08 | M |
| 2 | Validate `source_type` against `actor_type` in `record_evidence` | F-13, F-14 | S |
| 3 | Restrict `tier_floor` to SYSTEM/HUMAN callers | F-41 | S |
| 4 | Block task status regression (DONE→PENDING) | F-49 | S |
| 5 | Validate `task_id` exists before granting mutex in `claim_task` | F-35 | S |
| 6 | Implement per-role MCP credentials | F-24 | L |

### HIGH — Fix before scaling (Sprint 2)

| # | Fix | Findings | Effort |
|---|-----|----------|--------|
| 7 | Add test-design-to-code coverage gate | AF-06, AF-11 | L |
| 8 | Reject self-handoffs and self-dependencies | F-09, F-39 | S |
| 9 | Document all valid enum values in tool descriptions | F-15, F-16, F-17, F-31, F-38 | M |
| 10 | Require ownership transfer via handoff before `record_task` role change | F-32, F-50 | M |
| 11 | Validate preconditions on CS status transitions | F-46 | M |
| 12 | Add output-correctness check to code-reviewer | AF-10 | M |
| 13 | Run `generate_agents.py` and deploy `dist/` | F-23 | M |
| 14 | Enforce qa-derive implementation-blindness | F-22 | L |

### MEDIUM — Quality improvements (Sprint 3)

| # | Fix | Findings | Effort |
|---|-----|----------|--------|
| 15 | Add mutation testing gate (target >=85% kill rate) | MF-01 through MF-06 | L |
| 16 | Require state-change assertions in tests | MF-01, MF-08 | M |
| 17 | Add input validation heuristic to developer agent | AF-03 | S |
| 18 | Improve error messages (ASSUMPTION, status transitions) | F-06, F-20, F-27 | S |
| 19 | Return NotFound for nonexistent run/plan/event_type | F-42, F-44, F-45 | M |
| 20 | Reject empty task_id, empty handoff payloads | F-33, F-10 | S |

---

## 8. Recommendations

### Short-term (Sprint 1–2): Make enforcement real

The biggest ROI fix is making `record_transition` fail-closed for invalid transitions. This single change addresses 3 CRITICAL findings and establishes the principle that enforcement is actual, not advisory.

**Actions:**
1. Change `record_transition` to raise on invalid transitions (not just log VIOLATION)
2. Add input validation for `source_type`, `tier_floor`, task status direction
3. Document all enum values in MCP tool descriptions
4. Add a test-design-to-code coverage gate between IMPLEMENT and REVIEW

### Medium-term (Sprint 3–4): Improve test quality

Mutation testing reveals that tests catch 72–78% of introduced bugs. The 22–28% that survive represent real risk.

**Actions:**
1. Add mutation testing as a pipeline gate (target >=85%)
2. Ban `assertIn` for output correctness — use `assertEqual` or structured parsing
3. Require state-change assertions for write operations
4. Require test for every code-review fix (no dead validation code)
5. Add boundary-value tests for every numeric constant

### Long-term: Architectural improvements

1. **Per-role MCP credentials** — Currently all agents share `actor_type=AGENT, actor_id=agent:developer`. Role-specific credentials enable server-side enforcement of role boundaries.
2. **Enforcement map completion** — `docs/enforcement-map.md` should have a row for every rule, with explicit enforcement mechanism (CI, MCP, skill, hooks).
3. **Output-correctness gate** — Code reviewer should run generated code and compare actual output against acceptance criteria, not just read source.
4. **Edge case mandate** — qa-derive edge cases should be marked mandatory vs. nice-to-have, with enforcement that mandatory cases are implemented.

---

## Appendix A: Full Finding Index

### MCP Infrastructure (F-01 through F-50)

| ID | Severity | Category | Component | Status |
|----|----------|----------|-----------|--------|
| F-01 | LOW | error-handling | create_change_set | OPEN |
| F-02 | CRITICAL | enforcement-gap | record_transition | OPEN |
| F-04 | MEDIUM | documentation | record_evidence | OPEN |
| F-06 | LOW | error-handling | record_evidence | OPEN |
| F-07 | CRITICAL | enforcement-gap | record_transition | OPEN |
| F-08 | CRITICAL | enforcement-gap | record_transition | OPEN |
| F-09 | HIGH | data-integrity | record_handoff | OPEN |
| F-10 | MEDIUM | data-integrity | record_handoff | OPEN |
| F-12 | MEDIUM | data-integrity | create_change_set | OPEN |
| F-13 | CRITICAL | enforcement-gap | record_evidence | OPEN |
| F-14 | CRITICAL | enforcement-gap | record_evidence | OPEN |
| F-15 | HIGH | documentation | append_journal | OPEN |
| F-16 | MEDIUM | documentation | record_evidence | OPEN |
| F-17 | MEDIUM | documentation | update_status | OPEN |
| F-18 | LOW | error-handling | query_evidence | OPEN |
| F-19 | LOW | error-handling | query_evidence | OPEN |
| F-20 | MEDIUM | documentation | update_status | OPEN |
| F-21 | LOW | consistency | update_status | OPEN |
| F-22 | HIGH | role-boundary | qa-derive agent | OPEN |
| F-23 | HIGH | role-boundary | dist/ directory | OPEN |
| F-24 | HIGH | enforcement-gap | MCP credentials | OPEN |
| F-25 | MEDIUM | consistency | Conductor skill | OPEN |
| F-26 | MEDIUM | consistency | Conductor skill | OPEN |
| F-27 | LOW | consistency | record_evidence | OPEN |
| F-28 | INFO | documentation | append_journal | OPEN |
| F-29 | MEDIUM | enforcement-gap | Role system | OPEN |
| F-30 | HIGH | enforcement-gap | Reviewer roles | OPEN |
| F-31 | LOW | documentation | record_task | OPEN |
| F-32 | HIGH | data-integrity | record_task | OPEN |
| F-33 | MEDIUM | data-integrity | record_task | OPEN |
| F-34 | LOW | n/a | record_task | CLOSED |
| F-35 | CRITICAL | enforcement-gap | claim_task | OPEN |
| F-38 | LOW | documentation | record_task_failure | OPEN |
| F-39 | HIGH | data-integrity | record_dependency | OPEN |
| F-41 | CRITICAL | enforcement-gap | compute_risk_tier | OPEN |
| F-42 | MEDIUM | consistency | fold_state | OPEN |
| F-44 | MEDIUM | consistency | get_worker_status | OPEN |
| F-45 | MEDIUM | consistency | query_journal | OPEN |
| F-46 | HIGH | enforcement-gap | update_status | OPEN |
| F-47 | MEDIUM | data-integrity | record_evidence | OPEN |
| F-48 | MEDIUM | consistency | start_worker | OPEN |
| F-49 | CRITICAL | enforcement-gap | record_task | OPEN |
| F-50 | HIGH | data-integrity | record_task | OPEN |

### Artifact Quality (AF-01 through AF-15)

| ID | Severity | Dimension | Project | Status |
|----|----------|-----------|---------|--------|
| AF-01 | HIGH | Code Correctness | Task Tracker | OPEN |
| AF-02 | HIGH | Code Correctness | Task Tracker | OPEN |
| AF-03 | MEDIUM | Code Correctness | Task Tracker | OPEN |
| AF-04 | MEDIUM | Code Correctness | Task Tracker | OPEN |
| AF-05 | LOW | Code Correctness | Task Tracker | OPEN |
| AF-06 | HIGH | Test Quality | Task Tracker | OPEN |
| AF-07 | MEDIUM | Test Quality | Task Tracker | OPEN |
| AF-08 | MEDIUM | Architecture | Task Tracker | OPEN |
| AF-09 | LOW | Architecture | Task Tracker | OPEN |
| AF-10 | MEDIUM | Review Quality | Task Tracker | OPEN |
| AF-11 | HIGH | Pipeline Gap | All | OPEN |
| AF-12 | LOW | Code Correctness | Unit Converter | OPEN |
| AF-13 | LOW | Code Correctness | Unit Converter | OPEN |
| AF-14 | LOW | Code Correctness | Unit Converter | OPEN |
| AF-15 | INFO | Code Correctness | Unit Converter | OPEN |

### Mutation Testing (MF-01 through MF-12)

| ID | Severity | Project | Gap | Status |
|----|----------|---------|-----|--------|
| MF-01 | HIGH | Task Tracker | No test verifies `completed_at` set after done | OPEN |
| MF-02 | HIGH | Task Tracker | `_validate_shape()` never tested (dead code) | OPEN |
| MF-03 | HIGH | Expense Splitter | Tests don't verify WHO paid WHOM | OPEN |
| MF-04 | HIGH | Expense Splitter | Tests don't verify 2-decimal format specifically | OPEN |
| MF-05 | MEDIUM | Task Tracker | No test for mkdir auto-creation via load | OPEN |
| MF-06 | MEDIUM | Expense Splitter | Threshold not tested at boundary | OPEN |
| MF-07 | MEDIUM | All | `assertIn` checks pass for reversed direction | OPEN |
| MF-08 | MEDIUM | All | Integration tests don't verify persistence | OPEN |
| MF-09 | LOW | All | `assertIn` over `assertEqual` for output | OPEN |
| MF-10 | LOW | All | No exact error message format test | OPEN |
| MF-11 | LOW | All | No idempotency tests | OPEN |
| MF-12 | LOW | All | No concurrent access tests | OPEN |

---

*Generated: 2026-10-07 | 12 projects | 1,019 tests | 64 mutations tested | 50 infrastructure + 15 artifact + 12 mutation = 77 total findings*
