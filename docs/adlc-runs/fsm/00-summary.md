# FSM CLI — ADLC Artifact Quality Evaluation

**Project:** Finite State Machine CLI (`tetaprojects/fsm-cli/`)  
**Requirement:** DFA simulation, validation (reachability, dead states, non-determinism), ASCII/DOT visualization, partition-refinement minimization, JSON persistence, batch test runner  
**Date:** 2026-10-07

---

## Test Suite Overview

| Metric | Value |
|--------|-------|
| Total tests | 89 |
| Passing | 89 (after fixes) |
| Initial failures | 18 (2 root causes) |
| Modules covered | 7/7 (models, engine, validator, visualizer, minimizer, storage, cli) |

---

## Bugs Found

### Critical — Import Order (NameError crashes)

| ID | File | Issue | Severity |
|----|------|-------|----------|
| FSM-01 | `engine.py` | `from dataclasses import dataclass` placed AFTER `@dataclass` usage — NameError on import | CRITICAL |
| FSM-02 | `validator.py` | Same import ordering bug — `@dataclass` used before import | CRITICAL |

**Root cause:** Code generation placed the import after the class definition that uses it. Caused 18 of 89 tests to fail (all engine and validator tests).

### High — Unicode Encoding Crashes (Windows)

| ID | File:Line | Character | Context |
|----|-----------|-----------|---------|
| FSM-03 | `cli.py:213` | `→` (U+2192) | `"Minimized: 4 → 2 states"` |
| FSM-04 | `engine.py:50` | `ε` (U+03B5) | `trace.append("--ε-->")` |
| FSM-05 | `cli.py:116` | `ε` (U+03B5) | Transition label display |
| FSM-06 | `cli.py:191,195,198` | `—` (U+2014) | Em dash in test case output |
| FSM-07 | `validator.py:25` | `—` (U+2014) | Warning message text |
| FSM-08 | `visualizer.py:14,50` | `ε` (U+03B5) | ASCII and DOT output |

**Impact:** Any CLI command that triggers these code paths crashes with `UnicodeEncodeError: 'charmap' codec can't encode character` on Windows systems using cp1252 console encoding. 6 of 8 subcommands affected.

**Root cause:** ADLC code generation uses Unicode characters for aesthetics without considering the target platform's console encoding. No `PYTHONIOENCODING` or `sys.stdout.reconfigure()` guard.

### Medium — Design Issues

| ID | Issue | Impact |
|----|-------|--------|
| FSM-09 | `add_transition` allows NFA transitions (same from+input, different to) but `run_fsm` rejects them at runtime with FSMError | Confusing: can build an NFA that can't be run |
| FSM-10 | Epsilon transition handling only 1 level deep (no epsilon closure) | Incomplete NFA support |
| FSM-11 | No validation that transition states exist in FSM state list (model level) | Can create transitions referencing non-existent states via API |
| FSM-12 | Storage has load-modify-save race condition | Data corruption under concurrent CLI invocations |

---

## Mutation Test Results

### Batch 1 (10 mutations)

| ID | Mutation | Result |
|----|----------|--------|
| M1 | Invert acceptance check (`in` → `not in`) | KILLED |
| M2 | Never raise on missing transition | KILLED |
| M3 | Disable non-determinism check in engine (threshold 1→100) | **SURVIVED** |
| M4 | `get_transitions` ignores from_state filter | KILLED |
| M5 | `get_transitions` ignores symbol filter | KILLED |
| M6 | `validate` always returns valid=True | KILLED |
| M7 | `_can_reach_accepting` never finds accepting state | KILLED |
| M8 | Minimizer never splits groups (partition refinement disabled) | **SURVIVED** |
| M9 | `load_fsm` never raises NotFound | KILLED |
| M10 | Allow duplicate transitions silently | KILLED |

**Score: 8/10 (80%)**

### Batch 2 (10 mutations, 2 skipped)

| ID | Mutation | Result |
|----|----------|--------|
| M11 | `save_fsm` doesn't store FSM data | KILLED |
| M12 | `delete_fsm` doesn't remove FSM | KILLED |
| M13 | validate never exits nonzero | KILLED |
| M14 | Don't append final state to trace | KILLED |
| M15 | Never record actions | KILLED |
| M16 | `from_dict` drops all transitions | KILLED |
| M17 | Never report unreachable states | KILLED |
| M18 | Never report non-deterministic transitions | KILLED |
| M19 | Accept any initial state (skipped - pattern match issue) | SKIPPED |
| M20 | Wrong initial state after minimization (skipped) | SKIPPED |

**Score: 8/8 (100%)**

### Combined: 16/18 killed = **89% mutation score**

### Surviving Mutations (Test Gaps)

1. **M3 — Non-determinism error in engine not tested:** No test creates a non-deterministic FSM and runs input through `run_fsm`. The validator tests check non-determinism detection, but the engine's runtime guard is never exercised.

2. **M8 — Minimizer partition refinement not verified:** Test `test_four_to_two_states` should catch this but the minimizer still returns 2 states because the initial accepting/non-accepting partition happens to be the correct final partition for that specific test case. Need a test where partition refinement actually splits within an initial group.

---

## ADLC Pipeline Findings (from FSM CLI generation)

| Finding ID | Category | Severity | Description |
|------------|----------|----------|-------------|
| AF-FSM-01 | Code Correctness | CRITICAL | Import ordering bug — `@dataclass` used before `from dataclasses import dataclass` in 2 files |
| AF-FSM-02 | Platform Compat | HIGH | 8 Unicode encoding failures across 4 source files — crashes on Windows console |
| AF-FSM-03 | Test Coverage | MEDIUM | No test for engine's non-determinism runtime error path (M3 survivor) |
| AF-FSM-04 | Test Coverage | MEDIUM | Minimizer partition-refinement not distinguished from initial partition (M8 survivor) |
| AF-FSM-05 | API Design | MEDIUM | NFA transitions accepted at model level but rejected at engine level |
| AF-FSM-06 | Robustness | LOW | No epsilon closure — epsilon transitions handled as one-off fallback |
| AF-FSM-07 | Robustness | LOW | No model-level validation of transition states against FSM state list |

---

## Scores

| Dimension | Score | Max | Notes |
|-----------|-------|-----|-------|
| Code Correctness | 4 | 7 | 2 CRITICAL import bugs, 8 Unicode crashes |
| Test Quality | 5 | 7 | 89% mutation score, 2 gaps |
| Architecture | 6 | 7 | Clean separation, good dataclass design |
| API Consistency | 5 | 7 | NFA/DFA confusion in add_transition vs run |
| Platform Compatibility | 2 | 7 | Widespread Windows encoding failures |
| **Total** | **22** | **35** | |
