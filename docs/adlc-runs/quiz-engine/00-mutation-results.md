# Quiz Engine CLI — Mutation Testing Results

**Project**: `tetaprojects/quiz-engine-cli/`  
**Date**: 2026-10-07  
**Tests**: 106 (all passing)  

---

## Aggregate Score: 12/18 = 67%

### scoring.py + validators.py — 67% (8/12)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| QE-1 | Wrong score formula (*10 not *100) | CAUGHT | |
| QE-2 | Remove rounding | CAUGHT | |
| QE-3 | Invert correct/incorrect comparison | CAUGHT | |
| QE-4 | Force shuffle seed to 42 | CAUGHT | |
| QE-5 | Wrong unshuffle default (-1→0) | CAUGHT | |
| QE-6 | Invert time check (elapsed < limit) | SURVIVED | No test exercises timed quiz timeout |
| QE-7 | Answer display range 0-3→0-2 | SURVIVED | No test data uses option index 3 |
| QE-8 | Allow 3 options instead of 4 | CAUGHT | |
| QE-9 | Allow correct_answer=4 | SURVIVED | No test validates answer index at boundary |
| QE-10 | Skip empty array check | CAUGHT | |
| QE-11 | Allow wrong answer count | CAUGHT | |
| QE-12 | Allow answer value=4 | SURVIVED | No test submits out-of-range answer 4 |

### commands.py — 67% (4/6)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| QE-13 | Skip question file validation | CAUGHT | |
| QE-14 | Quiz ID counter += 2 | CAUGHT | |
| QE-15 | Attempt ID counter += 2 | SURVIVED | No test verifies attempt ID sequencing |
| QE-16 | Skip save after quiz creation | CAUGHT | |
| QE-17 | Force score to 100.0 | CAUGHT | |
| QE-18 | Skip unshuffle after shuffle | SURVIVED | Shuffle→unshuffle roundtrip not tested |

---

## Issues Found

### QE-F1: Timed quiz timeout never tested (HIGH)
**File**: `scoring.py:42`  
The `run_timed_answers` function and the timed path in `take_quiz` (commands.py:95-98)
are never exercised by tests. Inverting the time check survives completely.

### QE-F2: Option index 3 never in test data (MEDIUM)
**File**: `scoring.py:56`  
The `(no answer)` display fallback uses range `0 <= ans <= 3`, but narrowing
to `<= 2` survives because test questions never use the 4th option (index 3) as
an answer.

### QE-F3: Boundary validation gaps at index 4 (MEDIUM)
**Files**: `validators.py:39,60`  
Both `correct_answer` validation (0-3) and answer validation (0-3) can be widened
to 0-4 without test failure. No test submits `correct_answer: 4` or answer `4`.

### QE-F4: Attempt ID sequencing untested (LOW)
**File**: `commands.py:113`  
Same pattern as Task Tracker and Habit Tracker — `+= 2` survives.

### QE-F5: Shuffle roundtrip untested (MEDIUM)
**File**: `commands.py:90`  
Skipping `unshuffle_answers` survives. Tests with `shuffle=True` don't verify
that the unshuffled answers map back to the original question order correctly.

---

## Quality: 67% — weakest mutation score of tested projects

The Quiz Engine has the most tests (106) but the lowest mutation score (67%).
This demonstrates that **test count does not correlate with mutation score**.
The tests extensively cover happy paths and basic validation, but miss:
- Timeout/timing paths entirely
- Boundary values at validation edges
- Shuffle/unshuffle integration correctness
