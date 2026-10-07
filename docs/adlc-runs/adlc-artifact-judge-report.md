# ADLC Artifact Quality Judge Report

**Date:** 2026-10-07  
**Judge model:** claude-opus-4-6  
**Projects evaluated:** Task Tracker CLI (CS-2e894c06), Unit Converter CLI (CS-81cc2531), FSM Engine CLI (direct build)  
**Companion report:** [adlc-judge-report.md](adlc-judge-report.md) (MCP tool/infrastructure findings)

---

## 1. Executive Summary

**Artifact Quality Score: 56 / 70** (7 dimensions × 2 projects × 5 max)

The ADLC pipeline produces **functional software** with **good structure** but has **measurable gaps** in output correctness, test coverage, and cross-artifact consistency. The pipeline successfully decomposes requirements into stories, generates working code, and produces meaningful reviews — but specific bugs survive the pipeline end-to-end, test implementation falls short of the test design, and some code deviates from the architecture.

### Top 3 Artifact Findings

1. **BUG survived full pipeline (AF-01):** `stats` output has duplicate "Done:" label — prints "Done: 1" (count) then "Done: 33%" (percentage). Neither the test suite, code review, nor security review caught this.

2. **29% test gap (AF-06):** qa-derive designed 35 test cases; developer implemented only 27 (missing 10). All 5 edge cases from the test design were skipped entirely. The pipeline has no gate checking test-design-to-test-code coverage.

3. **Error routing wrong (AF-02):** User-facing errors (e.g., "Task 999 not found") print to stdout instead of stderr, violating NFR-004. The `except` block in `cli.py` correctly routes `StorageError` to stderr, but `done_task` returns errors as regular strings printed to stdout.

---

## 2. Project A: Task Tracker CLI — Detailed Results

### 2.1 Requirement Fidelity (Score: 5/5)

| Check | Result |
|-------|--------|
| Every requirement appears in INTAKE | PASS — all 4 commands, storage path, data model present |
| No hallucinated requirements | PASS — nothing invented |
| No requirements subtly changed | PASS — faithful reproduction |
| Ambiguities raised as QUESTIONs | N/A — requirements were clear |
| NFRs traceable | PASS — NFR-001 through NFR-005 all in intake doc |

**Verdict:** INTAKE stage produced a faithful, complete requirement specification. No additions, no omissions, no distortions.

### 2.2 Architecture-Code Alignment (Score: 3/5)

| Check | Result | Finding |
|-------|--------|---------|
| Module structure matches ADR | PASS — cli.py, commands.py, storage.py, models.py all present | — |
| Technology choices match | PASS — argparse, unittest, stdlib-only, JSON storage | — |
| Data model matches ADR schema | PASS — Task fields match exactly | — |
| No architectural drift | **PARTIAL** | **AF-08:** `done_task()` and `stats()` operate on raw dicts, not Task model objects (ADR 5.1 says commands.py uses models.py) |
| Separation of concerns | **PARTIAL** | **AF-09:** `commands.py:14` prints are mixed with logic — `add_task` returns a formatted string, coupling business logic to presentation |

**Findings:**
- **AF-08 (MEDIUM):** `done_task` at `commands.py:37-45` iterates over raw `data["tasks"]` dicts and mutates them directly, never constructing Task objects. `stats` at `commands.py:49-55` does the same. The ADR says "commands.py contains the four command implementations" and "models.py defines the Task dataclass and its JSON serialization" — the implication is commands work with Task objects.
- **AF-09 (LOW):** ADR 5.1 says "Each [command] returns a result; printing is done by the caller." In practice, `add_task` returns `f"Added task {task.id}: {task.description}"` — the formatting IS the return value. This is a minor coupling but faithful to the spirit.

### 2.3 Plan Coverage (Score: 5/5)

| Check | Result |
|-------|--------|
| Every requirement → story | PASS — REQ-001 fully decomposed into ST-001–ST-008 |
| Every story has typed ACs | PASS — all ACs use specific, testable assertions |
| No orphan stories | PASS — all stories trace to user stories/NFRs |
| Dependencies correct | PASS — foundation stories block features, features block CLI, CLI blocks tests |
| Story sizing reasonable | PASS — XS to M, appropriate for scope |

**Verdict:** Plan is solid. Decomposition is clean, dependencies are logical, and ACs are specific enough to test against.

### 2.4 Code Correctness (Score: 3/5)

| Check | Result | Finding |
|-------|--------|---------|
| `python -m task_tracker --help` | PASS | — |
| All commands produce correct output | **FAIL** | AF-01, AF-02 |
| Edge cases handled | **FAIL** | AF-03, AF-04 |
| Error messages clear, to stderr | **FAIL** | AF-02 |
| Exit codes correct | PARTIAL | AF-02 |
| No hardcoded paths | PASS | `TASK_TRACKER_FILE` env override exists |
| Follows own conventions | PARTIAL | AF-08 |

**Findings:**

- **AF-01 (HIGH) — Duplicate "Done:" label in stats:**
  ```
  Total: 3
  Done:  1     ← count of done tasks
  Todo:  2
  Done:  33%   ← completion percentage — DUPLICATE LABEL
  ```
  `commands.py:55` uses "Done:" for both the count and the percentage. Should be distinct labels (e.g., "Complete: 33%").

- **AF-02 (HIGH) — Error messages go to stdout, not stderr:**
  `done_task()` returns error strings like `"Error: Task 999 not found."` which `cli.py:41` prints via `print(msg)` to stdout. Only `StorageError`/`OSError` (caught at `cli.py:46-48`) goes to stderr. NFR-004 says "exit code 1 on user error" (correct) but the error MESSAGE goes to the wrong stream.

- **AF-03 (MEDIUM) — Empty description accepted:**
  `add_task("")` creates `"Added task 5: "` with an empty description. No validation in commands.py or cli.py. Not caught by any test or review.

- **AF-04 (MEDIUM) — Long descriptions break table formatting:**
  An 80-character description produces a 104-character line with no truncation:
  ```
  1     todo    AAAA...AAAA2026-10-07
  ```
  The Created column merges with the description. Code reviewer noted this as non-blocking (item in review doc) but it's a visual correctness issue per AC-ST004.4.

- **AF-05 (LOW) — Integer division truncates percentage:**
  `commands.py:54` uses `done_count * 100 // total` which truncates: 2/3 = 66%, not 67%. AC-ST006.2 says "integer percentage" — ambiguous whether this means truncation or rounding. Convention favors `round()`.

### 2.5 Test Quality (Score: 3/5)

| Check | Result | Finding |
|-------|--------|---------|
| Tests for every AC | **FAIL** | AF-06: 10 ACs missing tests |
| Error/edge case tests | **FAIL** | AF-07: All 5 edge cases (TC-E01–E05) unimplemented |
| Tests independent | PASS | Each test class has setUp/tearDown with temp dirs |
| Tests use temp dirs | PASS | AC-ST008.3 met |
| All tests pass | PASS | 27/27 pass |
| Names describe what they verify | PASS | Clear test names |
| AC traceability | **FAIL** | No AC references in test code |

**Findings:**

- **AF-06 (HIGH) — 10 designed test cases not implemented:**
  The qa-derive test design specifies 35 test cases. Only 27 were implemented. Missing:
  
  | Designed Case | What's Missing |
  |--------------|----------------|
  | TC-001.5 | Default storage path construction test |
  | TC-003.3 | Explicit persistence verification after add |
  | TC-004.4 | Table column format validation |
  | TC-005.2 | Persistence verification after done |
  | TC-007.4 | Traceback suppression test |
  | TC-E01 | Very long description (1000+ chars) |
  | TC-E02 | Special characters in description |
  | TC-E03 | Non-integer ID argument |
  | TC-E04 | Invalid --status value |
  | TC-E05 | Storage file deleted between operations |

- **AF-07 (MEDIUM) — No edge case tests at all:**
  All 5 edge cases (TC-E01–TC-E05) from the test design were skipped. These are the most likely to catch real bugs — and indeed, empty description (related to TC-E02) and long description (TC-E01) both have actual bugs in the code.

### 2.6 Review Effectiveness (Score: 4/5)

| Check | Result |
|-------|--------|
| Code review caught real issues | PASS — 3 blocking items, all genuine |
| Security review identified risks | PASS — 7 LOW/INFO findings, appropriate |
| Findings actionable | PASS — specific fixes described |
| Blocking items blocking-worthy | PASS — non-atomic save, invalid build-backend, missing validation |
| False negatives | **PARTIAL** — AF-01 (duplicate label) and AF-02 (stderr routing) not caught |

**Finding:**
- **AF-10 (MEDIUM) — Code review missed 2 output bugs:** The duplicate "Done:" label (AF-01) and stderr routing issue (AF-02) were not flagged. The reviewer noted "Stats output wording differs slightly from AC-ST006.3" as non-blocking — but didn't identify the duplicate label. The stderr issue was not mentioned at all despite NFR-004 specifying error behavior.

### 2.7 Cross-Artifact Consistency (Score: 3/5)

| Check | Result | Finding |
|-------|--------|---------|
| Requirements → Plan | PASS — all requirements covered by stories | — |
| Plan → Code | PASS — all stories implemented | — |
| Code → Tests | **FAIL** | AF-06: 10 designed tests not implemented |
| ADR → Code | **PARTIAL** | AF-08: commands bypass Task model |
| Test design → Test code | **FAIL** | 29% gap (10/35 missing) |
| Review → Fixes | PASS — all 3 blocking items fixed | — |

**Finding:**
- **AF-11 (HIGH) — No pipeline gate between test design and test implementation:**
  The qa-derive agent produced 35 test cases. The developer implemented 27. There is no automated check that verifies test-design-to-test-code coverage. This is the biggest cross-artifact gap — the ADLC pipeline produces a test design but has no enforcement that the test implementation matches it.

---

## 3c. Combined Scoring Matrix

| Dimension | Project A | Project B | Average | Key Issue |
|-----------|-----------|-----------|---------|-----------|
| Requirement Fidelity | 5/5 | 4/5 | 4.5 | A: perfect; B: singular/plural display |
| Architecture-Code Alignment | 3/5 | 5/5 | 4.0 | A: commands bypass model; B: clean |
| Plan Coverage | 5/5 | N/A | 5.0 | Solid decomposition |
| Code Correctness | 3/5 | 4/5 | 3.5 | Output formatting bugs in both |
| Test Quality | 3/5 | 5/5 | 4.0 | A: 29% gap; B: comprehensive |
| Review Effectiveness | 4/5 | N/A | 4.0 | Catches structural, misses output |
| Cross-Artifact Consistency | 3/5 | N/A | 3.0 | Test design→code gap |
| **Total** | **26/35** | **18/20** | **80%** | |

---

## 4. Findings Table

| ID | Severity | Dimension | Description | Expected | Actual |
|----|----------|-----------|-------------|----------|--------|
| AF-01 | HIGH | Code Correctness | `stats` output has duplicate "Done:" label | Unique labels for count and percentage | "Done: 1" and "Done: 33%" — same label for different data |
| AF-02 | HIGH | Code Correctness | Error messages for `done` go to stdout, not stderr | Errors to stderr per NFR-004 | `print(msg)` to stdout; only StorageError goes to stderr |
| AF-06 | HIGH | Test Quality | 10 of 35 designed test cases not implemented (29% gap) | All designed tests implemented | 27/35 implemented; all 5 edge cases skipped |
| AF-11 | HIGH | Cross-Artifact | No gate checking test-design-to-test-code coverage | Automated coverage check | Pipeline proceeds with incomplete test implementation |
| AF-03 | MEDIUM | Code Correctness | Empty description accepted by `add` command | Reject empty/whitespace descriptions | `"Added task 5: "` with empty description |
| AF-04 | MEDIUM | Code Correctness | Long descriptions break table formatting in `list` | Truncate or wrap long descriptions | 80-char description merges with Created column |
| AF-07 | MEDIUM | Test Quality | All 5 edge cases from test design skipped | Edge cases implemented (they catch real bugs) | TC-E01 through TC-E05 all missing |
| AF-08 | MEDIUM | Architecture | `done_task` and `stats` bypass Task model (raw dicts) | Use Task.from_dict() per ADR 5.1 | Direct dict mutation in commands.py |
| AF-10 | MEDIUM | Review | Code review missed duplicate label and stderr routing | Review catches output correctness bugs | Noted "wording differs slightly" but missed specific bugs |
| AF-05 | LOW | Code Correctness | Stats percentage truncates instead of rounding (66% vs 67%) | `round()` for conventional rounding | Integer division `//` truncates |
| AF-09 | LOW | Architecture | Command functions return formatted strings (coupling) | Return data; let caller format | Minor — spirit of ADR is followed |
| AF-12 | LOW | Code Correctness | Unit Converter: input value displayed as float (100.0 vs 100) | Clean integer display for whole numbers | argparse `type=float` causes `100.0` display |
| AF-13 | LOW | Code Correctness | Unit Converter: singular input displayed as plural ("1.0 liters") | Handle singular/plural in display | Alias normalizes to canonical plural |
| AF-14 | LOW | Code Correctness | Unit Converter: argparse error exits code 2, not 1 | Consistent exit code 1 for all errors | argparse's own error handler uses code 2 |
| AF-15 | INFO | Code Correctness | Unit Converter: same-unit conversion shows inconsistent decimals | Consistent formatting on both sides | `42.0 km = 42.00 km` — different decimal places |

---

## 3b. Project B: Unit Converter CLI — Results

**Pipeline:** Compact run (no INTAKE/ARCHITECTURE docs — direct to IMPLEMENT+TEST)  
**Change Set:** CS-81cc2531  
**Tests:** 29/29 pass

### Scores

| Dimension | Score | Notes |
|-----------|-------|-------|
| Requirement Fidelity | 4/5 | All conversions present; singular "liter"→"liters" display mismatch |
| Architecture-Code Alignment | 5/5 | Clean separation: converter.py (logic), cli.py (parsing), no coupling |
| Plan Coverage | N/A | Compact run — no formal plan produced |
| Code Correctness | 4/5 | All conversions correct; float display bug (100.0 vs 100) |
| Test Quality | 5/5 | 29 tests, edge cases included (crossover, negatives, aliases, same-unit) |
| Review Effectiveness | N/A | Compact run — no formal review |
| Cross-Artifact Consistency | N/A | Compact run — fewer artifacts to compare |

**Scored dimensions: 18/20** (4 applicable dimensions)

### Findings

| ID | Severity | Description | Expected | Actual |
|----|----------|-------------|----------|--------|
| AF-12 | LOW | Input value displayed as float: `100.0 km = 62.14 miles` | `100 km = 62.14 miles` | argparse parses as `float`, displayed with `.0` |
| AF-13 | LOW | Singular input displayed as plural: `1.0 liters = 0.26 gallons` | `1 liter = 0.26 gallons` or handle singular display | Alias normalizes to canonical plural form |
| AF-14 | LOW | argparse error exits with code 2, not 1 | Exit code 1 on all errors | `convert abc km miles` returns rc=2 from argparse |
| AF-15 | INFO | Same-unit conversion works but shows inconsistent decimals: `42.0 km = 42.00 km` | Either both sides have 2 decimals or neither | Left side has 1, right has 2 |

### What's Better vs Project A

| Aspect | Project A (Task Tracker) | Project B (Unit Converter) |
|--------|-------------------------|---------------------------|
| Error routing | Errors to stdout | Errors to stderr — correct |
| Test coverage | 27/35 (77%) | Comprehensive — edge cases included |
| Edge case handling | Skipped all 5 edge cases | Crossover (-40°C), negatives, aliases tested |
| Architecture | Commands bypass model layer | Clean separation throughout |
| Output bugs | Duplicate "Done:" label | Minor float display only |

---

## 4. Project C: FSM Engine CLI — Results

**Pipeline:** Direct build (IMPLEMENT + TEST)  
**Location:** `tetaprojects/fsm-cli/`  
**Tests:** 89/89 pass (after 2 critical fixes)  
**Mutation Score:** 89% (16/18)

### Scores

| Dimension | Score | Notes |
|-----------|-------|-------|
| Requirement Fidelity | 5/5 | All 8 subcommands implemented: create, add-transition, run, validate, visualize, list, test, minimize |
| Architecture-Code Alignment | 5/5 | Clean 7-module design: models, engine, validator, visualizer, minimizer, storage, cli |
| Plan Coverage | N/A | Direct build — no formal plan |
| Code Correctness | 3/5 | 2 CRITICAL import-order bugs (NameError); 8 Unicode encoding crashes |
| Test Quality | 4/5 | 89 tests across 6 files; 89% mutation score; 2 untested paths |
| Review Effectiveness | N/A | Direct build — no formal review |
| Cross-Artifact Consistency | N/A | Direct build |

**Scored dimensions: 17/20** (4 applicable dimensions, but adjusted to 22/35 when considering the severity of bugs)

### Bugs Found

| ID | Severity | Category | Description |
|----|----------|----------|-------------|
| AF-FSM-01 | CRITICAL | Import Order | `@dataclass` used before `from dataclasses import dataclass` in `engine.py` — NameError on any import |
| AF-FSM-02 | CRITICAL | Import Order | Same import-ordering bug in `validator.py` |
| AF-FSM-03 | HIGH | Platform | `→` (U+2192) in minimize output crashes on Windows cp1252 |
| AF-FSM-04 | HIGH | Platform | `ε` (U+03B5) in engine trace crashes on Windows |
| AF-FSM-05 | HIGH | Platform | `ε` in CLI transition label display crashes on Windows |
| AF-FSM-06 | HIGH | Platform | `—` (U+2014) em dash in test runner output crashes on Windows |
| AF-FSM-07 | HIGH | Platform | `—` in validator warning message crashes on Windows |
| AF-FSM-08 | HIGH | Platform | `ε` in visualizer (both ASCII and DOT) crashes on Windows |
| AF-FSM-09 | MEDIUM | API Design | `add_transition` allows NFA (non-deterministic) transitions, but `run_fsm` rejects them at runtime |
| AF-FSM-10 | LOW | Incomplete | Epsilon transition handling only 1 level deep — no epsilon closure |

### Mutation Test Details

| ID | Mutation | Result |
|----|----------|--------|
| M1 | Invert acceptance check | KILLED |
| M2 | Never raise on missing transition | KILLED |
| M3 | Disable non-determinism check (>1 → >100) | **SURVIVED** — no test exercises this engine path |
| M4-M5 | Break get_transitions filters | KILLED |
| M6 | validate always returns valid | KILLED |
| M7 | _can_reach_accepting always fails | KILLED |
| M8 | Minimizer never splits groups | **SURVIVED** — test FSM's initial partition matches final |
| M9-M18 | 10 more mutations (storage, CLI, models) | ALL KILLED |

### Key Finding: Import-Order Bugs Are a New Category

This is the first project where the ADLC pipeline generated code with **import statements in the wrong order**. The `@dataclass` decorator was used before `from dataclasses import dataclass` appeared in both `engine.py` and `validator.py`. This caused 18/89 tests to fail on initial run — a CRITICAL correctness issue that would have been caught by simply running the code once.

**Root cause:** The code generation agent wrote class definitions before their imports. Neither a linter pass nor a simple "run the code" gate exists in the pipeline.

---

## 5. Cross-Project Patterns

Confirmed patterns from Projects A and B:

1. **Core logic is correct across both projects** — conversions, task operations, and data persistence all work correctly. The pipeline produces functionally sound software.

2. **Output formatting is the weak spot** — Project A has a duplicate label bug and table overflow; Project B has a float display issue. The developer agent gets logic right but makes presentation errors consistently.

3. **Test quality varies significantly** — Project A skipped all edge cases (27/35 = 77% coverage of test design). Project B included crossover, negative, alias, and same-unit tests (much more thorough). This suggests test quality depends on whether a qa-derive test design exists as a reference.

4. **Error handling improves when requirements are explicit** — Project B's requirements specified "Error on unknown units" and the implementation correctly routes to stderr. Project A's NFR-004 said "exit code 1 on error" but didn't explicitly say "stderr", and the implementation got it wrong for command-level errors.

5. **No test-design-to-code gate** — still the biggest systemic gap. When qa-derive produces a design, it's advisory only. No gate verifies the developer implemented all designed cases.

6. **Simpler projects produce higher-quality artifacts** — Unit Converter (4 dimensions scored: 18/20 = 90%) vs Task Tracker (7 dimensions: 26/35 = 74%) vs FSM CLI (4 dimensions: 17/20 = 85% before bug severity, 22/35 = 63% adjusted). More complexity exposes more gaps in the pipeline.

7. **Import-order bugs are a new failure mode** — FSM CLI is the first project where code generation placed `@dataclass` usage before its import statement. This is a CRITICAL bug that would be caught by running the code even once. The pipeline needs a "does it import cleanly?" gate.

8. **Platform encoding is a systemic issue** — 3 of 15 projects (20%) use Unicode characters that crash on Windows. The developer agent consistently uses aesthetic Unicode (ε, →, ✓, ✗, —) without encoding guards. This is a platform-awareness gap in the developer skill.

---

## 6. Recommendations

### For ADLC Skills (improve pipeline output quality)

1. **Add a test-design coverage gate** — after IMPLEMENT, compare test methods against the qa-derive test design and flag unimplemented cases before proceeding to REVIEW.

2. **Add an output-correctness check to code review** — code-reviewer should run the code and compare actual output against AC expected values, not just read the source.

3. **Enforce edge case implementation** — the qa-derive test design edge cases (TC-E01–E05) represent the highest-value tests. Make their implementation mandatory before REVIEW gate passes.

4. **Add input validation heuristic** — the developer agent consistently skips input validation (empty descriptions, etc.) unless the AC explicitly mentions it. Consider adding a skill hint: "validate inputs at command boundaries even if not explicitly specified."

5. **Verify error output routing** — add a standard check that errors go to stderr and success output goes to stdout. This is a common miss.

### For Agent Roles

6. **developer agent** should cross-reference the qa-derive test design when writing tests, not just write tests based on ACs directly.

7. **code-reviewer agent** should be required to run the code and check output against ACs, not just read source.

8. **qa-derive agent** should flag "must-implement" edge cases separately from "nice-to-have" ones.

---

## 7. Mutation Testing Results (Round 4)

Manual mutation testing introduces deliberate bugs in source code and checks if tests catch them.

### Results by Project

| Project | Mutations | Killed | Survived | Score |
|---------|-----------|--------|----------|-------|
| Task Tracker CLI | 11 | 8 | 3 | 72% |
| Expense Splitter CLI | 14 | 11 | 3 | 78% |
| FSM Engine CLI | 18 | 16 | 2 | 89% |
| Habit Tracker CLI | 24 | 18 | 6 | 75% |
| Full-stack Todo App | 20 | 17 | 3 | 85% |

### Surviving Mutations (test gaps that let bugs through)

#### Task Tracker CLI

| Mutation | What it does | Why tests miss it |
|----------|-------------|-------------------|
| Don't set `completed_at` | `done` command doesn't timestamp completion | No test checks `completed_at` field after done (AC-003.2 untested) |
| Skip `mkdir` on first load | Fails on fresh install in nested path | Tests use pre-existing temp dirs, not nested paths via `load()` |
| Skip `_validate_shape()` | Corrupted JSON with wrong keys not caught | Code-review fix added validation but no test exercises it |

#### Expense Splitter CLI

| Mutation | What it does | Why tests miss it |
|----------|-------------|-------------------|
| Balance threshold 0.005→0.5 | Balances under $0.50 silently disappear | No test with small balances near the threshold |
| Swap names in settle message | "Bob paid Alice" → "Alice paid Bob" | Tests use `assertIn("$5.00")` — checks amount but not direction |
| 2→1 decimal format | `$10.00` → `$10.0` | `$10.00` matches `:.1f` output `10.0` via `assertIn("10.0")` |

### Systematic Weaknesses

1. **`assertIn` is the enemy of mutation testing** — catches keywords but not structure. Tests that check `assertIn("$5.00", output)` can't distinguish `"Alice paid Bob $5.00"` from `"Bob paid Alice $5.00"`.

2. **Side-effect testing is consistently weak** — tests verify return values (messages, exit codes) but rarely verify state changes (was `completed_at` set? was JSON file updated?).

3. **Dead validation code exists** — Task Tracker's `_validate_shape()` was added during code review but no test calls it. M10 (skip it entirely) survives all 27 tests.

4. **Integration tests don't read persisted state** — CLI tests run commands and check stdout, but never read the JSON storage file to verify data was actually saved.

### Recommended Test Quality Gates

| Gate | What it checks | When to run |
|------|---------------|-------------|
| Mutation score ≥ 85% | Tests catch at least 85% of injected bugs | After TEST, before REVIEW |
| State-change assertions | Tests for write ops verify persisted data | REVIEW checklist item |
| Output exactness | Tests use `assertEqual` not `assertIn` for structured output | REVIEW checklist item |
| Review-fix tests | Every code-review fix has a corresponding test | After REVIEW fixes applied |
| Persistence verification | CLI integration tests read storage file after writes | TEST design requirement |

---

*Last updated: 2026-10-07 — Rounds 1-5 (15 projects, 5 mutation-tested)*  
*Companion reports: [adlc-issues.md](adlc-issues.md) (consolidated tracker), [adlc-judge-report.md](adlc-judge-report.md) (MCP tools)*
