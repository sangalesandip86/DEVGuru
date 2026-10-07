# Habit Tracker CLI — ADLC Run Summary

**Project**: Habit Tracker CLI  
**Location**: `tetaprojects/habit-tracker-cli/`  
**Generated**: 2026-10-07  
**Python**: 3.10+, stdlib only  

---

## Overview

A CLI habit tracker with daily/weekly/weekdays frequencies, streak calculation,
completion rate tracking, ASCII calendar view, and archive/unarchive support.

## Files Built

### Source (6 modules)
| File | Lines | Purpose |
|------|-------|---------|
| `habit_tracker/models.py` | ~40 | `Habit` dataclass with serialization |
| `habit_tracker/storage.py` | ~58 | JSON persistence, atomic writes via `tempfile.mkstemp` + `os.replace` |
| `habit_tracker/streaks.py` | ~148 | Streak, longest-streak, completion-rate logic |
| `habit_tracker/habits.py` | ~163 | Business logic (add, check-in, uncheck, list, archive, stats) |
| `habit_tracker/calendar_view.py` | ~40 | ASCII monthly calendar rendering |
| `habit_tracker/cli.py` | ~90 | argparse CLI with subcommands, errors to stderr |

### Tests (6 files, 87 tests — all passing)
| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_models.py` | 6 | Create, serialization, roundtrip |
| `tests/test_storage.py` | 6 | Create, load, corrupt, structure, roundtrip |
| `tests/test_streaks.py` | 22 | Daily/weekday/weekly streaks, longest, completion rate |
| `tests/test_habits.py` | 30 | All business operations, edge cases |
| `tests/test_calendar.py` | 6 | Rendering, checkmarks, headers |
| `tests/test_cli.py` | 19 | Integration via subprocess, all commands |

---

## Mutation Testing Results

### streaks.py — 75% (6/8 caught)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| M1 | `timedelta(days=1)` → `days=2` in `_prev_expected_day` daily | SURVIVED | **Dead code** — daily streak uses direct subtraction |
| M2 | `weekday() < 5` → `< 4` | CAUGHT | |
| M3 | `streak += 1` → `+= 2` | CAUGHT | |
| M4 | `timedelta(weeks=1)` → `weeks=2` in `_prev_expected_day` weekly | SURVIVED | **Dead code** — weekly streak uses ISO week math |
| M5 | Remove today check for daily | CAUGHT | |
| M6 | Wrong completion rate formula | CAUGHT | |
| M7 | Skip sorting dates | CAUGHT | |
| M8 | Wrong longest streak reset | CAUGHT | |

### habits.py — 80% (8/10 caught)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| M9 | Skip duplicate check | CAUGHT | |
| M10 | `next_id += 1` → `+= 2` | SURVIVED | No test verifies ID sequencing |
| M11 | Allow future dates | CAUGHT | |
| M12 | Skip persist on check-in | CAUGHT | |
| M13 | Skip persist on uncheck | SURVIVED | No test verifies disk state after uncheck |
| M14 | Archive sets `False` instead of `True` | CAUGHT | |
| M15 | Case-sensitive name comparison | CAUGHT | |
| M16 | Skip frequency validation | CAUGHT | |
| M17 | Allow zero target | CAUGHT | |
| M18 | Skip before-creation check | CAUGHT | |

### storage.py — 67% (4/6 caught)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| M19 | Skip `os.replace` (atomic write) | CAUGHT | |
| M20 | Remove JSON indent | SURVIVED | Cosmetic — no test checks formatting |
| M21 | Skip structure validation | CAUGHT | |
| M22 | Wrong default `next_id` (0 vs 1) | CAUGHT | |
| M23 | Skip `makedirs` in save | CAUGHT | |
| M24 | Remove UTF-8 encoding | SURVIVED | No non-ASCII test data |
| M25 | Return empty data on corrupt file | CAUGHT | |

### Aggregate Mutation Score: 18/24 = 75%

---

## Issues Found

### HT-01: Dead code in `_prev_expected_day` (Medium)
**File**: `streaks.py:12-22`  
The `daily` and `weekly` branches of `_prev_expected_day` are never called.
Daily streak logic at line 80 uses `day - timedelta(days=1)` directly.
Weekly streak logic at line 46 uses ISO week arithmetic.
Only the `weekdays` branch is exercised.

### HT-02: No test for ID sequencing (Low)
**File**: `habits.py:36`  
`next_id += 2` mutation survives. Tests verify habit creation succeeds
but never assert that IDs are sequential (1, 2, 3...).

### HT-03: Uncheck persistence not tested (Medium)
**File**: `habits.py:72`  
Removing `storage.save()` after uncheck survives. Tests call `uncheck()`
and check the return message but never reload from disk to verify the
check-in was actually removed from persistent storage.

### HT-04: No non-ASCII test data (Low)
**File**: `storage.py:30`  
Removing `encoding="utf-8"` survives. No test creates a habit with
non-ASCII characters (e.g., "Méditer" or "読書") to exercise the
encoding path.

### HT-05: JSON formatting not tested (Info)
**File**: `storage.py:43`  
Removing `indent=2` survives. Cosmetic — the file is still valid JSON,
just not human-readable. Low priority.

### HT-06: Windows Unicode encoding issue (Medium)
**File**: `calendar_view.py`  
Original implementation used Unicode characters (✓ and ·) which caused
`UnicodeEncodeError: 'charmap' codec can't encode character '✓'`
on Windows cp1252 consoles when run via subprocess in tests. Fixed by
switching to ASCII characters (X and .).
**Pattern**: ADLC-generated code should default to ASCII for CLI output
on cross-platform projects.

---

## Quality Assessment

| Dimension | Score | Notes |
|-----------|-------|-------|
| Requirement fidelity | 5/5 | All features implemented |
| Architecture alignment | 4/5 | Clean module separation; dead code in streaks.py |
| Code correctness | 4/5 | All functions work correctly; dead code present |
| Test coverage | 4/5 | 87 tests, good edge cases; persistence gaps |
| Test effectiveness (mutation) | 3/5 | 75% mutation score; 6 surviving mutations |
| Error handling | 5/5 | Proper stderr routing, StorageError, validation |
| Cross-platform | 3/5 | Unicode issue on Windows required fix |

**Total: 28/35 (80%)**
