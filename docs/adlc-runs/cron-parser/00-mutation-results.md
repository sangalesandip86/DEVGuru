# Cron Parser CLI — Mutation Testing Results

**Project**: `tetaprojects/cron-parser-cli/`  
**Date**: 2026-10-07  
**Tests**: 86 (all passing)  

---

## Aggregate Score: 16/23 = 70%

### parser.py — 70% (7/10)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| CP-1 | Off-by-one in range end (`end + 1` → `end`) | CAUGHT | |
| CP-2 | Off-by-one in wildcard hi (`hi + 1` → `hi`) | CAUGHT | |
| CP-3 | Allow step=0 | CAUGHT | |
| CP-4 | Reverse wrap range order (`23-2` → wrong set) | SURVIVED | No test for wrap-around ranges like `23-2` or `FRI-MON` |
| CP-5 | `start <= end` → `start < end` (single-value range) | SURVIVED | No test for `5-5` (range where start == end) |
| CP-6 | Skip field count validation | CAUGHT | |
| CP-7 | SUN=0 → SUN=7 | SURVIVED | No test uses SUN by name — only numeric `0` |
| CP-8 | DEC=12 → DEC=11 | CAUGHT | |
| CP-9 | Invert dom_specified logic | CAUGHT | |
| CP-10 | Invert dow_specified logic | CAUGHT | |

### scheduler.py — 57% (4/7)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| CS-1 | Wrong DOW mapping SUN | CAUGHT | |
| CS-2 | DOM+DOW uses AND not OR | CAUGHT | |
| CS-3 | Year increment +1 → +2 | CAUGHT | |
| CS-4 | Year decrement -1 → -2 | SURVIVED | `prev_occurrences` not tested across year boundary |
| CS-5 | Advance skips 2 days instead of 1 | SURVIVED | Tests don't catch day gaps in next occurrence |
| CS-6 | `next_in_set` boundary `>=` → `>` | CAUGHT | |
| CS-7 | `prev_in_set` boundary `<=` → `<` | SURVIVED | Retreat logic boundary condition untested |

### explainer.py — 83% (5/6)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| CE-1 | AM/PM boundary `< 12` → `<= 12` | CAUGHT | |
| CE-2 | 12h display `% 12 or 12` → `% 12` | CAUGHT | |
| CE-3 | Minute not zero-padded | CAUGHT | |
| CE-4 | Reverse month name order | SURVIVED | No test verifies order of multi-month explanation |
| CE-5 | DOW name off by one | CAUGHT | |
| CE-6 | Skip dom explanation | CAUGHT | |

---

## Issues Found

### CP-F1: No wrap-around range tests (HIGH)
**File**: `parser.py:96-99`  
Ranges like `23-2` (hours 23,0,1,2) or `FRI-MON` (dow 5,6,0,1) are supported by the parser's wrap logic, but no test exercises this path. Mutation CP-4 (reverse the two list segments) survives entirely.

### CP-F2: No single-value range test (MEDIUM)
**File**: `parser.py:96`  
The range `5-5` should produce `{5}`, but changing `<=` to `<` survives, meaning this edge case is untested.

### CP-F3: SUN name unused in tests (MEDIUM)
**File**: `parser.py:9`  
DOW_NAMES maps SUN→0, but tests only use numeric `0` for Sunday. Changing the mapping to SUN=7 survives.

### CP-F4: prev_occurrences not tested across year boundaries (HIGH)
**File**: `scheduler.py:150`  
Year decrement from -1 to -2 survives. Tests call `prev_occurrences` but never with a from_time in January where the previous occurrence would be in the prior year.

### CP-F5: Day advance skip undetected (MEDIUM)
**File**: `scheduler.py:124`  
Skipping 2 days instead of 1 in `_advance()` survives — next_occurrences returns correct results by eventually finding the right minute, but with gaps the tests don't detect.

### CP-F6: prev_in_set boundary untested (MEDIUM)
**File**: `scheduler.py:196`  
`<=` vs `<` in `_prev_in_set` — the retreat logic boundary condition has no test that distinguishes between inclusive and exclusive matching.

---

## Quality Assessment: 28/35 (80%)

The cron parser is well-tested for core parsing and scheduling (86 tests), but the scheduler's backward traversal (`prev_occurrences`, `_retreat`) is significantly weaker than forward traversal. Wrap-around ranges — a key cron feature — have zero test coverage.
