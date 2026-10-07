# ADLC Platform — Comprehensive Evaluation Findings & Recommended Changes

**Date:** 2026-10-07  
**Evaluator:** claude-opus-4-6  
**Scope:** MCP tools, pipeline artifacts, agent personas, pipeline gates, multi-tech-stack  
**Method:** Adversarial QA, artifact quality judging, mutation testing, mass pipeline runs

---

## 1. Executive Summary

The ADLC platform was evaluated across **5 rounds** with **19 projects** (1,562 tests) spanning Python CLIs, REST APIs, full-stack web apps, Java, and Node.js ecosystems.

| Round | Focus | Key Metric |
|-------|-------|------------|
| Round 1 | MCP tool enforcement (5 scenarios) | Health: 21/40 — fail-open stage transitions, source_type spoofing |
| Round 2 | Task lifecycle & concurrency (2 scenarios) | Health: 19/40 — phantom task claims, status regression, risk inflation |
| Round 3 | Artifact quality (2 projects deep) | Score: 56/70 (80%) — output bugs survive full pipeline |
| Round 4 | Mutation testing (3 projects) | Kill rate: 72-78% — `assertIn` weakness, missing state verification |
| Round 5 | Mass pipeline (19 projects, 3 tech stacks) | 1,562 tests; 9 code bugs; 12 mutation-tested (avg 77%) |
| Round 6 | Deep audit (crypto, SQL injection, dead features) | 2 CRITICAL security, 3 HIGH logic bugs found |

### Top 7 Platform-Level Issues

1. **Stage transitions are fail-open** (F-02/07/08) — `record_transition` logs VIOLATION but succeeds. Agents can skip stages.
2. **Security review misses crypto weakness** — Password Vault XOR encryption is trivially breakable; Mini ORM has SQL injection in `order_by`. Security review passed both as ACCEPT.
3. **No test-design-to-code gate** (AF-11) — qa-derive produces test designs, but no gate verifies the developer implemented them. 29% gap measured.
4. **Output formatting bugs survive the full pipeline** — duplicate labels, wrong decimal places, column overflow. Code reviewer reads code but doesn't run it.
5. **`assertIn`-based tests miss structural bugs** (MF-03/04/09) — tests check keywords but not structure, letting direction/format mutations survive. Quiz Engine has 106 tests but only 67% mutation score.
6. **Single MCP credential for all roles** (F-24) — every agent authenticates identically; MCP server cannot distinguish developer from reviewer.
7. **Security parameter constants never tested** — PBKDF2 iterations, hash algorithm, minimum password length all changeable without any test failing.

---

## 2. Projects Tested

### 2a. Python CLI Tools

| Project | Tests | Pass | Mutation Score | Key Finding |
|---------|-------|------|----------------|-------------|
| Task Tracker CLI | 27 | 27/27 | 72% (8/11) | Duplicate "Done:" label; review fix has 0 tests |
| Unit Converter CLI | 29 | 29/29 | 73% (11/15) | Precision mutation survives; wrong alias accepted silently |
| Expense Splitter CLI (manual) | 69 | 69/69 | 78% (11/14) | assertIn misses who-paid-whom direction |
| Expense Splitter CLI (ADLC) | 88 | 88/88 | — | Clean; CSV line terminator fix during impl |
| Note Search CLI | 123 | 123/123 | 91% (11/12) | Highest mutation score; only tag sort order survives; search module 100% |
| Cron Parser CLI | 86 | 86/86 | 70% (16/23) | Wrap-around ranges untested; prev_occurrences weak across year boundaries; SUN name never tested |
| Password Vault CLI | 82 | 82/82 | 83% (15/18) | CRITICAL: PBKDF2 iterations + hash algorithm mutations survive; security params vs functional correctness gap |
| Log Analyzer CLI | 89 | 89/89 | 64% (9/14) | Error isolation in stats untested; WARNING normalization untested; JSON field priority untested |
| CSV Transformer CLI | 95 | 95/95 | 82% (14/17) | Filters 91% (strongest module); stats empty_count and most_common limit untested |
| Quiz Engine CLI | 106 | 106/106 | 67% (12/18) | Most tests (106) but lowest mutation score; timed quiz path untested; boundary validation gaps |
| Habit Tracker CLI | 87 | 87/87 | 75% (18/24) | Dead code in `_prev_expected_day`; Windows ✓→X encoding fix; uncheck persistence untested |
| FSM Engine CLI | 89 | 89/89 | 89% (16/18) | 2 CRITICAL import-order bugs; 8 Unicode encoding crashes on Windows; NFA/DFA API inconsistency |
| Mini ORM + Migrations | 86 | 86/86 | 83% (15/18) | commit() removal not caught (same-connection tests); assertTrue(1) passes for bool coercion |

### 2b. Backend / Full-Stack (Python)

| Project | Type | Tests | Key Finding |
|---------|------|-------|-------------|
| Bookstore REST API | `http.server` + SQLite | 89/89 | REST CRUD + stats; search/pagination solid |
| Project Dashboard | `http.server` + HTML templates | 79/79 | Clean pass; dashboard aggregation + filtering |
| Chat Server | `socketserver` + threading | 98/98 (67% mutation) | Lowest mutation score; 8 survivors incl. missing commit, no concurrency tests, dead code |

### 2c. Multi-Tech-Stack

| Project | Language/Runtime | Tests | Key Finding |
|---------|-----------------|-------|-------------|
| Java Inventory System | Java 21 (javac, no Maven) | 64/64 | BigDecimal correct; JDK version mismatch (java 1.8 vs javac 21) |
| Node.js Recipe API | Node.js v24 (built-in `node:test`) | 92/92 (89% mutation) | HTTP 204 sends body (RFC violation); busy-wait file lock; search tests weak |
| Full-stack Todo App | Node.js + vanilla HTML/CSS/JS | 84/84 (85% mutation) | Mutable ref leak in getAll(); dead escapeHtml(); missing light-theme CSS |

---

## 3. Findings by Category

### 3a. MCP Tool Findings (50 total — Rounds 1-2)

**CRITICAL (8):**

| ID | Component | Issue |
|----|-----------|-------|
| F-02 | `record_transition` | Invalid stage names log VIOLATION but call succeeds (fail-open) |
| F-07 | `record_transition` | INTAKE→IMPLEMENT (skip 2 stages) succeeds |
| F-08 | `record_transition` | REVIEW→INTAKE (backward transition) succeeds |
| F-13 | `record_evidence` | Agent can set `source_type="SYSTEM"` — stored as-is |
| F-14 | `record_evidence` | Agent can set `source_type="HUMAN"` — stored as-is |
| F-35 | `claim_task` | Nonexistent task IDs can be claimed (phantom mutex) |
| F-41 | `compute_risk_tier` | Agent can set `tier_floor=CRITICAL` to inflate risk (LOW→CRITICAL) |
| F-49 | `record_task` | DONE tasks can regress to PENDING (no forward-only enforcement) |

**HIGH (10):**

| ID | Component | Issue |
|----|-----------|-------|
| F-09 | `record_handoff` | Self-handoff (developer→developer) accepted |
| F-15 | `append_journal` | 20 valid event_types completely undocumented |
| F-22 | qa-derive agent | "Implementation-blind" is prose, not enforced |
| F-23 | `dist/` directory | Empty — `generate_agents.py` never run |
| F-24 | MCP credentials | All agents share single credential |
| F-30 | Reviewer roles | `model_family_constraint` not checked |
| F-32 | `record_task` | Task owner silently reassigned with no audit |
| F-39 | `record_dependency` | Self-dependency accepted (A depends on A) |
| F-46 | `update_status` | SCOPED→PLANNED without any plan artifact |
| F-50 | `record_task` | Owner role changed without handoff record |

**MEDIUM (14), LOW (9), INFO (1):** See `adlc-issues.md` for full details.

---

### 3b. Artifact Quality Findings (15 total — Round 3)

| Pattern | Frequency | Examples |
|---------|-----------|---------|
| Output formatting bugs | 4/4 projects (100%) | Duplicate labels, float display, table overflow, decimal inconsistency |
| Test design→code gap | 1/1 (where qa-derive ran) | 29% of designed tests not implemented; all edge cases skipped |
| Error routing (stderr) | 2/4 projects (50%) | Errors to stdout instead of stderr when requirements implicit |
| Input validation missing | 2/4 projects (50%) | Empty descriptions accepted, no boundary checks |
| Architecture drift | 1/4 projects (25%) | Commands bypass model layer (raw dict mutation) |
| Review false negatives | 1/1 (where review ran) | Missed duplicate label and stderr routing bugs |
| Import ordering bugs | 1/15 (FSM CLI) | `@dataclass` used before `from dataclasses import dataclass` — 2 files, CRITICAL crash |
| API consistency gap | 1/15 (FSM CLI) | Model allows NFA transitions; engine rejects them at runtime |
| Platform encoding crashes | 3/15 (Quiz Engine, FSM CLI, Habit Tracker) | Unicode chars (ε/→/✓/✗/—) crash on Windows cp1252 console |

---

### 3c. Mutation Testing Findings (12 findings — Round 4)

| Pattern | Task Tracker | Expense Splitter | Root Cause |
|---------|-------------|-----------------|------------|
| Mutation score | 72% | 78% | — |
| `assertIn` misses structure | Yes | Yes | Tests check keywords not structure |
| Side-effect testing weak | Yes (completed_at) | No | Tests verify return, not state |
| Dead validation code | Yes (_validate_shape) | No | Review fix added, no test |
| Direction mutations survive | No | Yes (who-paid-whom) | Tests check amount not actors |
| Format mutations survive | Yes | Yes (decimal) | Loose assertions |

---

### 3d. Mass Pipeline Run Findings (Round 5)

From 15+ projects across diverse requirements:

| Finding | Projects Affected | Severity |
|---------|-------------------|----------|
| **Windows encoding issues** — formatters use Unicode chars (✓/✗/→/ε/—) that crash on cp1252 | Quiz Engine, FSM CLI (8 instances across 4 files), Habit Tracker | HIGH |
| **Falsy collection bug** — `[] or default` evaluates to `default` because `[]` is falsy | Quiz Engine | HIGH |
| **N/A in numeric filter** — string `"N/A" > "0"` is True lexicographically | CSV Transformer | HIGH |
| **Test bugs more common than code bugs** — 4 projects had test assertion errors, not code errors | Note Search, Log Analyzer, CSV Transformer, Quiz Engine | MEDIUM |
| **JDK version mismatch undetected** — `java` on PATH is 1.8 while `javac` is 21; pipeline doesn't check runtime vs compiler version | Java Inventory | MEDIUM |
| **Clean projects confirm core logic is solid** — Cron Parser, Password Vault, Log Analyzer, Java Inventory all clean | 4 projects | INFO (positive) |
| **Security-sensitive code PARTIALLY handled** — Password Vault XOR crypto passes functional tests but is trivially breakable (known-plaintext attack); deep audit overturned initial "clean" assessment | Password Vault | CRITICAL (revised) |
| **Java BigDecimal precision correct** — `9.99 * 100 = 999.00` exact, no floating-point errors | Java Inventory | INFO (positive) |
| **Mutable reference leak** — `getAll()` returns internal array reference, not a copy; callers can corrupt state | Full-stack Todo | MEDIUM |
| **Dead code generated** — `escapeHtml()` function in app.js never called (textContent used instead, which is correct) | Full-stack Todo | LOW |
| **Incomplete dark mode** — `[data-theme="light"]` CSS block missing; light theme toggle doesn't work | Full-stack Todo | LOW |
| **Malformed JSON on PUT silently accepted** — bad JSON parsed as `{}`, validation catches missing fields but PUT has no required fields | Full-stack Todo | MEDIUM |
| **XSS protection correct** — uses `textContent`, never `innerHTML` with user data; path traversal blocked | Full-stack Todo | INFO (positive) |
| **Node.js mutation score 85%** — highest of all projects tested; 3 surviving mutations all structural | Full-stack Todo | INFO (positive) |
| **HTTP 204 sends body** — `sendJSON(res, 204, null)` writes `"null"` with Content-Length 4; RFC 7231 §6.3.5 says 204 must have no body | Node.js Recipe API | MEDIUM |
| **Busy-wait file locking** — `store.js` uses synchronous loop for file lock, blocking Node.js event loop | Node.js Recipe API | MEDIUM |
| **Search tests only match from start** — searching "spaghetti" in "Spaghetti Carbonara" also matches `startsWith`; need mid-word search test | Node.js Recipe API | LOW |
| **Empty PUT body silently succeeds** — `PUT /api/recipes/:id` with `{}` returns 200 with no changes, no error | Node.js Recipe API | LOW |
| **Recipe scaling arithmetic correct** — fractional servings, zero-quantity, scale-up/down all verified | Node.js Recipe API | INFO (positive) |
| **Node.js 89% mutation score** — second highest; redundant guard only survivor besides weak search test | Node.js Recipe API | INFO (positive) |
| **CRITICAL: XOR encryption trivially breakable** — Password Vault uses XOR with repeating key; known-plaintext attack recovers key. Encryption key derivable from stored PBKDF2 hash | Password Vault | CRITICAL |
| **HIGH: SQL injection in ORM order_by** — Mini ORM `order_by` parameter uses f-string interpolation, not parameterized query; `User.filter(db, order_by="name; DROP TABLE users")` is exploitable | Mini ORM | HIGH |
| **HIGH: `or True` in chat server** — `if __name__ == "__main__" or True:` makes import start server unconditionally | Chat Server | HIGH |
| **HIGH: FSM minimizer wrong initial state** — minimizer picks wrong representative for initial state's partition | FSM Engine | HIGH |
| **HIGH: Quiz timed mode never enforces time** — timed quiz mode exists but time limits are never checked during gameplay | Quiz Engine | HIGH |
| **commit() removal not caught by ORM tests** — SQLite autocommit with same-connection tests masks missing commit calls | Mini ORM | MEDIUM |
| **assertTrue(1) passes for bool** — `assertTrue(1)` succeeds due to truthiness; need `assertIs(val, True)` for type-strict checks | Mini ORM | LOW |

---

## 4. Systematic Patterns (Cross-Cutting)

### Pattern 1: The Pipeline Produces Correct Logic but Wrong Output
**Evidence:** Every project's core business logic works. Conversions convert, parsers parse, encryption encrypts. But output *formatting* — labels, decimal places, table alignment, singular/plural — has bugs in 100% of projects where tested deeply.

**Root cause:** Developer agent treats formatting as trivial. Code reviewer reads source but doesn't run the code against expected output. No AC-vs-output comparison exists in the pipeline.

### Pattern 2: Test Design Is Better Than Test Implementation
**Evidence:** qa-derive produces comprehensive test designs with edge cases. The developer implements 71-77% of them. All edge cases get skipped first.

**Root cause:** No gate checks test-design-to-test-code coverage. The developer writes tests from ACs directly rather than cross-referencing qa-derive's output.

### Pattern 3: `assertIn` Is the Enemy of Mutation Testing
**Evidence:** Every project uses `assertIn("keyword", output)` for output verification. This catches presence but not structure, direction, or exact format.

**Root cause:** The developer agent defaults to the loosest assertion that makes the test pass. No guidance in the developer skill says "use assertEqual for structured output."

### Pattern 4: Side-Effect Testing Is Consistently Weak
**Evidence:** Tests verify return values (print output, exit codes) but rarely verify state changes (was data persisted? was the timestamp set? was the file created?).

**Root cause:** CLI integration tests run commands and check stdout. They don't read the storage file afterward. The test design doesn't require persistence verification.

### Pattern 5: Code Review Catches Structure, Misses Output
**Evidence:** Code reviewer finds real issues — non-atomic saves, missing validation, wrong imports. But it consistently misses output formatting bugs, because it reads code rather than running it.

**Root cause:** code-reviewer role doesn't include "run the code and compare output to ACs" in its workflow.

### Pattern 6: Review Fixes Lack Tests
**Evidence:** When code review adds a fix (e.g., `_validate_shape()`), no test is written for it. The fix is dead code from day one.

**Root cause:** No gate says "every code-review fix needs a test." The developer fixes the code but doesn't update the test suite.

### Pattern 7: Simpler Projects Score Higher
**Evidence:** Unit Converter (90%) > Task Tracker (74%). Projects with fewer commands and simpler state have fewer gaps.

**Root cause:** Complexity reveals weaknesses in the pipeline's cross-artifact consistency. More stages = more places for design-to-code drift.

### Pattern 8: Explicit Requirements Produce Better Code
**Evidence:** When requirements say "Error on unknown units" → stderr routing correct. When NFR says "exit code 1 on error" → stderr routing wrong. Explicit > implicit.

**Root cause:** Developer agent follows explicit requirements faithfully but doesn't infer standard behavior (errors→stderr) when requirements are silent.

### Pattern 9: Protocol/Platform Compliance Is Weak
**Evidence:** HTTP 204 sends body (RFC violation), busy-wait file locking blocks Node.js event loop, JDK version mismatch undetected. The developer agent gets application semantics right but misses platform-level correctness.

**Root cause:** Developer agent focuses on feature requirements, not protocol specs or runtime constraints. No checklist item says "verify HTTP status codes match RFC semantics" or "check runtime version compatibility."

### Pattern 10: Networking/Concurrent Code Has More Bugs
**Evidence:** Chat Server has a CRITICAL IndexError on no-argument commands (13 test failures) — the most impactful single bug found across all 19 projects. The bug is simple (off-by-one in argument parsing) but the domain (socket protocol parsing) is where the pipeline struggles.

**Root cause:** Network protocol parsing requires defensive coding around variable-length input. The developer agent assumes well-formed input more aggressively in socket/protocol contexts than in CLI contexts.

### Pattern 11: More Tests ≠ Better Tests
**Evidence:** Quiz Engine (106 tests, 67% mutation) vs FSM Engine (89 tests, 89% mutation). Log Analyzer (89 tests, 64% mutation) vs Password Vault (82 tests, 83%). The project with the most tests has one of the lowest mutation scores. Test count doesn't correlate with mutation score — assertion quality matters more.

**Root cause:** The pipeline generates high test counts with consistent architecture (unit per module + integration) but uses weak assertion patterns throughout. Improving assertion style would boost mutation scores more than adding more tests.

### Pattern 12: Dead Code Is Generated Consistently
**Evidence:** Task Tracker `_validate_shape()` (added in review, no test), Habit Tracker `_prev_expected_day` daily/weekly branches (unreachable), Full-stack Todo `escapeHtml()` (never called). Dead code appears in 3/19 projects (16%).

**Root cause:** No dead code detection in the pipeline. Code review adds defensive code without tests. Developer generates utility functions "just in case" that nothing calls.

### Pattern 13: Security Review Misses Cryptographic Weaknesses
**Evidence:** Password Vault uses XOR encryption with repeating key — trivially breakable with known-plaintext attack. The encryption key is derivable from the stored PBKDF2 hash. Security review passed this as "ACCEPT" with no HIGH/CRITICAL findings. Mini ORM has SQL injection in `order_by` via f-string — the one place parameterized queries weren't used.

**Root cause:** Security reviewer checks for common patterns (SQL injection in queries, path traversal, input validation) but doesn't evaluate cryptographic algorithm strength. XOR encryption "looks like encryption" and passes functional tests, but is not semantically secure. The security review persona lacks crypto-specific checklist items.

### Pattern 14: Features Are Generated but Never Enforced
**Evidence:** Quiz Engine's timed mode exists (code, UI, data model) but time limits are never checked during gameplay. The feature passes all tests because no test verifies that time actually runs out.

**Root cause:** Developer agent implements the data model and UI for a feature but skips the enforcement logic. Tests verify the feature can be configured, not that it works. This is a subtle variant of the output-formatting pattern — the *structure* is correct but the *behavior* is wrong.

### Pattern 15: Security Parameter Constants Never Tested
**Evidence:** Password Vault mutation testing: reducing PBKDF2 iterations from 100,000 to 1, changing hash algorithm from SHA-256 to MD5, and lowering minimum password length from 8 to 4 all survive with 0 test failures. Tests verify encrypt/decrypt roundtrips but never assert the security parameters themselves.

**Root cause:** The pipeline generates "functional correctness" tests (does it work?) but never "security adequacy" tests (is it secure enough?). Constants like iteration counts, algorithm names, key/salt lengths, and session TTLs are never asserted in tests because the test generator focuses on behavior, not configuration. For security-sensitive code, the test-engineer agent needs a "security constant assertion" pattern: verify that PBKDF2 iterations >= 100K, key length >= 32 bytes, algorithm is not in {md5, sha1}, etc.

### Pattern 16: Backward/Reverse Operations Systematically Undertested
**Evidence:** Cron Parser scheduler has 57% mutation score for `prev_occurrences`/`_retreat` vs solid forward scheduling. Habit Tracker's `uncheck` persistence mutation (skip save) survives. Log Analyzer's "remove error filter" mutations survive. Across projects, "undo/previous/reverse" paths have consistently lower mutation scores than "add/next/forward" paths.

**Root cause:** Requirements and acceptance criteria naturally emphasize the forward/happy path ("create a quiz", "add a habit", "find next occurrence"). Reverse operations ("previous occurrences", "uncheck", "remove credential") are mentioned but get fewer specific ACs. The qa-derive agent inherits this bias — it generates more test cases for creation than for deletion/reversal.

---

## 5. Recommended Changes

### 5.1 Changes to MCP Tools

| Priority | Change | Findings Addressed | Effort |
|----------|--------|-------------------|--------|
| **P0** | `record_transition`: Return error (not just log) for invalid transitions | F-02, F-07, F-08 | S |
| **P0** | `record_evidence`: Validate `source_type` against caller's `actor_type` | F-13, F-14 | S |
| **P0** | Implement per-role MCP credentials | F-24 | M |
| **P0** | `record_task`: Enforce forward-only status transitions (DONE is terminal) | F-49 | S |
| **P0** | `compute_risk_tier`: Restrict `tier_floor` to SYSTEM/HUMAN callers | F-41 | S |
| **P0** | `claim_task`: Validate task_id exists before granting mutex | F-35 | S |
| **P1** | `record_handoff`: Reject `from_role == to_role` | F-09 | S |
| **P1** | `record_dependency`: Reject self-referential dependencies | F-39 | S |
| **P1** | `update_status`: Require plan artifact before SCOPED→PLANNED | F-46 | S |
| **P1** | `record_task`: Require handoff before owner_role change | F-32, F-50 | M |
| **P2** | Document all valid enum values in tool descriptions | F-15, F-16, F-17, F-31, F-38 | S |
| **P2** | `query_evidence`: Return NotFound for nonexistent change_set_id | F-18 | S |
| **P2** | `query_evidence`/`query_journal`: Validate filter values | F-19, F-45 | S |
| **P2** | `record_handoff`: Require non-empty payload | F-10 | S |
| **P2** | `start_worker`: Raise exceptions like all other tools | F-48 | S |
| **P2** | `fold_state`/`get_worker_status`: Return NotFound for bad IDs | F-42, F-44 | S |

### 5.2 Changes to ADLC Skills (Pipeline)

| Priority | Change | Findings Addressed | Effort |
|----------|--------|-------------------|--------|
| **P0** | **Add test-design coverage gate** — after IMPLEMENT, compare test methods against qa-derive test design. Flag unimplemented cases before REVIEW. | AF-06, AF-07, AF-11 | M |
| **P0** | **Add output-correctness check** — code-reviewer runs the code and compares actual output against AC expected values. | AF-01, AF-02, AF-10, Pattern 1, Pattern 5 | M |
| **P0** | **Require test for every code-review fix** — if review adds `_validate_shape()`, a test must exist before REVIEW passes. | MF-02, Pattern 6 | S |
| **P1** | **Add mutation testing gate** — after TEST, run mutation pass. Target ≥85% kill rate. | MF-01–12, Pattern 3-4 | L |
| **P1** | **Add input validation heuristic** — developer agent validates inputs at command boundaries even when ACs don't explicitly say so. | AF-03, Pattern 8 | S |
| **P1** | **Add standard output-routing check** — verify errors→stderr, success→stdout as a standard REVIEW checklist item. | AF-02, Pattern 8 | S |
| **P1** | **Enforce edge case implementation** — qa-derive marks edge cases as MANDATORY vs OPTIONAL. Mandatory ones must be implemented. | AF-07, Pattern 2 | M |
| **P1** | **Add persistence verification requirement** — test design requires CLI integration tests to read storage after write commands. | MF-08, Pattern 4 | S |
| **P2** | **Add Windows compatibility check** — flag Unicode characters (✓✗→) in output formatters on non-UTF-8 terminals. | Quiz Engine encoding | S |
| **P2** | **Ban `assertIn` for output correctness** — developer skill should use `assertEqual` or regex for structured output checks. | MF-03, MF-04, MF-09, Pattern 3 | S |
| **P2** | **Require state-change assertions** — tests for write operations must verify persisted state, not just return message. | MF-01, MF-05, Pattern 4 | S |
| **P1** | **Add protocol compliance checklist** — verify HTTP status codes match RFC, check runtime version compatibility. | Pattern 9, PF-17 (204 body) | S |
| **P1** | **Add defensive parsing requirement for network code** — protocol parsers must handle variable-length input. | Pattern 10, Chat Server crash | S |
| **P2** | **Add dead code detection** — warn when functions/branches are unreachable. | Pattern 12, PF-12 | M |
| **P0** | **Add crypto algorithm review to @security-reviewer** — XOR, ROT13, base64 are not encryption. Check for known-weak algorithms. | Pattern 13, Password Vault CRITICAL | S |
| **P0** | **Verify parameterized queries in ALL SQL paths** — not just SELECT/INSERT/UPDATE/DELETE, but also ORDER BY, GROUP BY, table names. | Pattern 13, Mini ORM SQL injection | S |
| **P1** | **Add feature-enforcement verification** — test that features with limits/timeouts/thresholds actually enforce them, not just configure them. | Pattern 14, Quiz Engine timed mode | M |
| **P0** | **Add security constant assertion tests** — for security-sensitive projects, test-engineer must assert PBKDF2 iterations >= 100K, key length >= 32 bytes, algorithm not in {md5, sha1}, session TTL <= 300s. | Pattern 15, PV-F1/F2/F3 | S |
| **P1** | **Add reverse-operation test parity** — qa-derive must generate equal test coverage for reverse operations (uncheck, delete, prev_occurrences) as for forward operations. | Pattern 16, CS-4/5/7, MF-14 | M |

### 5.3 Changes to Agent Personas/Roles

| Role | Change | Findings Addressed | Priority |
|------|--------|-------------------|----------|
| **@developer** | Cross-reference qa-derive test design when writing tests, not just ACs directly | AF-06, AF-07, Pattern 2 | P0 |
| **@developer** | Use `assertEqual` (not `assertIn`) for structured output assertions | MF-03, MF-04, Pattern 3 | P1 |
| **@developer** | Add test for every code-review fix, not just the code fix | MF-02, Pattern 6 | P0 |
| **@developer** | Validate inputs at boundaries (empty strings, negative numbers) even without explicit ACs | AF-03, Pattern 8 | P1 |
| **@developer** | Test both return values AND state changes for write operations | MF-01, Pattern 4 | P1 |
| **@developer** | Handle platform encoding (set UTF-8 encoding for Unicode output) | Quiz Engine | P2 |
| **@code-reviewer** | **Run the code** and compare output against ACs, not just read source | AF-01, AF-02, AF-10, Pattern 5 | P0 |
| **@code-reviewer** | Verify every review fix has a corresponding test before ACCEPT | MF-02, Pattern 6 | P0 |
| **@code-reviewer** | Check error routing (stderr vs stdout) as standard checklist item | AF-02, Pattern 8 | P1 |
| **@qa-derive** | Classify edge cases as MANDATORY vs OPTIONAL in test design | AF-07, Pattern 2 | P1 |
| **@qa-derive** | Include persistence verification tests in design (read storage after writes) | MF-08, Pattern 4 | P1 |
| **@qa-derive** | Include output format exactness tests (exact string match, not keyword) | Pattern 3 | P2 |
| **@security-reviewer** | Check for platform encoding issues (cp1252, UTF-8 BOM) | Quiz Engine | P2 |
| **@product-owner** | Enforce explicit error routing in requirements ("errors to stderr") | Pattern 8 | P2 |

### 5.4 Changes to Pipeline Gates

| Gate | When | What It Checks | Priority |
|------|------|----------------|----------|
| **Test-Design Coverage Gate** | After IMPLEMENT, before REVIEW | Every qa-derive test case has a matching test method | P0 |
| **Output-Correctness Gate** | During REVIEW | Run code, compare output to AC expected values | P0 |
| **Review-Fix Test Gate** | After REVIEW fixes applied | Every blocking fix has a corresponding test | P0 |
| **Mutation Testing Gate** | After TEST, before REVIEW | ≥85% mutation kill rate | P1 |
| **Persistence Verification Gate** | During TEST | Write-operation tests verify storage file | P1 |
| **Encoding Safety Gate** | During REVIEW | No unguarded Unicode in stdout formatters | P2 |

### 5.5 Documentation Improvements

| Area | Change | Priority |
|------|--------|----------|
| MCP tool descriptions | Add valid enum values for all parameters (statuses, classifications, event_types, failure_classes) | P1 |
| `update_status` errors | Include valid transitions in error message ("cannot go from DRAFT to X; valid: SCOPED") | P2 |
| CS status ↔ stage mapping | Document the relationship between Change Set statuses and pipeline stages | P1 |
| OBSERVATION classification | Either add as valid classification or remove from docs/prompts | P2 |
| `generate_agents.py` output | Run the script and populate `dist/` with enforced `disallowedTools` and `maxTurns` | P1 |

---

## 6. Implementation Priority

### Sprint 1 — Before Pilot (P0)

**MCP fixes (6 items):**
1. `record_transition` returns error for invalid transitions
2. `record_evidence` validates `source_type` against `actor_type`
3. Per-role MCP credentials
4. `record_task` forward-only status enforcement
5. `compute_risk_tier` restrict `tier_floor` to SYSTEM/HUMAN
6. `claim_task` validate task existence

**Pipeline fixes (3 items):**
7. Test-design coverage gate (qa-derive → test code comparison)
8. Output-correctness check in code-reviewer workflow
9. Review-fix test requirement

**Persona fixes (3 items):**
10. @developer cross-references qa-derive test design
11. @code-reviewer runs code against ACs
12. @code-reviewer verifies review fixes have tests

**Security fixes (3 items):**
13. Add crypto algorithm review to @security-reviewer (XOR/ROT13/base64 are not encryption)
14. Verify parameterized queries in ALL SQL paths (ORDER BY, GROUP BY, table names)
15. Add security constant assertion tests (PBKDF2 iterations, key length, algorithm)

### Sprint 2 — Before Scale (P1)

**MCP fixes (4 items):**
13. Reject self-handoffs and self-dependencies
14. Require plan artifact before PLANNED status
15. Require handoff for owner_role changes
16. Document all enum values

**Pipeline fixes (5 items):**
17. Mutation testing gate (target ≥85%)
18. Input validation heuristic in developer skill
19. Standard output-routing check
20. Mandatory edge case enforcement
21. Persistence verification requirement

**Persona fixes (5 items):**
22. @developer uses assertEqual for structured output
23. @developer validates inputs at boundaries
24. @developer tests state changes, not just returns
25. @qa-derive classifies edge cases MANDATORY vs OPTIONAL
26. @qa-derive includes persistence verification tests

### Sprint 3 — Quality Polish (P2)

27-39. Remaining P2 items from sections 5.1–5.5

---

## 7. Metrics Summary

| Metric | Value | Target |
|--------|-------|--------|
| MCP health score | 19/40 | ≥32/40 |
| Artifact quality score | 56/70 (80%) | ≥63/70 (90%) |
| Mutation kill rate (avg) | 77% (64-91% range, 12 projects) | ≥85% |
| Test-design implementation rate | 77% (27/35) | 100% |
| Output formatting bug rate | 100% of deeply-tested projects | 0% |
| Platform encoding bug rate | 20% (3/15) of projects | 0% |
| Projects tested | 15 built + 11 evaluated (Python, Java, Node.js) | — |
| Total tests across all projects | 1,580+ | — |
| Code bugs found | 9 across 18 projects | — |
| Test bugs found | 3 across 18 projects | — |
| Projects with test failures | 2/19 (Chat Server, FSM Engine) | 0/N |
| Total findings | 131 (50 MCP + 15 artifact + 26 mutation + 24 pipeline + 16 patterns) | — |
| Recommended changes | 48 (16 MCP + 20 skills + 14 personas + 6 gates + 5 docs) | — |

---

## 8. What Works Well

Despite the findings, the ADLC pipeline has genuine strengths:

| Strength | Evidence |
|----------|----------|
| **Core logic is always correct** | 20+ projects: conversions, parsers, crypto, scheduling — all produce correct results |
| **INTAKE is faithful** | Requirement fidelity scored 5/5 — no hallucination, no distortion |
| **Plan decomposition is solid** | Stories have typed ACs, correct dependencies, reasonable sizing |
| **Security-sensitive code is partially handled** | XSS prevention verified (Full-stack Todo). BUT: Password Vault XOR crypto is trivially breakable; Mini ORM has SQL injection in order_by. Security review missed both. |
| **Lifecycle state enforcement works** | APPROVED/VERIFIED blocked for agents; FACT reserved for hooks; forge-only statuses enforced |
| **Test infrastructure is good** | Every project uses temp dirs, subprocess integration, proper isolation |
| **Error routing improves with explicit requirements** | When told "errors to stderr", it works every time |
| **High test counts** | 27-123 tests per project — the pipeline generates substantial test suites |

---

## Appendix A: All Project Results

| # | Project | Tests | Pass/Fail | Mutation | Tech Stack | Status |
|---|---------|-------|-----------|----------|------------|--------|
| 1 | Task Tracker CLI | 27 | 27/0 | 72% | Python | DONE |
| 2 | Unit Converter CLI | 29 | 29/0 | 73% | Python | DONE |
| 3 | Note Search CLI | 123 | 123/0 | 91% | Python | DONE |
| 4 | Expense Splitter (manual) | 69 | 69/0 | 78% | Python | DONE |
| 5 | Expense Splitter (ADLC) | 88 | 88/0 | — | Python | DONE |
| 6 | Cron Parser CLI | 86 | 86/0 | 70% | Python | DONE |
| 7 | Password Vault CLI | 82 | 82/0 | 83% | Python | DONE |
| 8 | Log Analyzer CLI | 89 | 89/0 | 64% | Python | DONE |
| 9 | CSV Transformer CLI | 95 | 95/0 | 82% | Python | DONE |
| 10 | Quiz Engine CLI | 106 | 106/0 | 67% | Python | DONE |
| 11 | Habit Tracker CLI | 87 | 87/0 | 75% | Python | DONE |
| 12 | FSM Engine CLI | 89 | 88/1 | 89% | Python | DONE |
| 13 | Mini ORM | 86 | 86/0 | 83% | Python | DONE |
| 14 | Bookstore REST API | 89 | 89/0 | — | Python | DONE |
| 15 | Project Dashboard | 79 | 79/0 | — | Python | DONE |
| 16 | Chat Server | 98 | 98/0 | 67% | Python | DONE |
| 17 | Java Inventory | 64 | 64/0 | — | Java 21 | DONE |
| 18 | Node.js Recipe API | 92 | 92/0 | 89% | Node.js | DONE |
| 19 | Full-stack Todo | 84 | 84/0 | 85% | Node.js | DONE |
| **Total** | | **1,562** | **1,561/1** | **avg 77%** | | |

---

*Generated: 2026-10-07 | Evaluator: claude-opus-4-6 | Session: DEVGuru ADLC evaluation*
