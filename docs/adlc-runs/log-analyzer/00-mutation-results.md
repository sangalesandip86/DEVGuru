# Log Analyzer CLI — Mutation Testing Results

**Project**: `tetaprojects/log-analyzer-cli/`  
**Date**: 2026-10-07  
**Tests**: 89 (all passing)  

---

## Aggregate Score: 9/14 = 64%

### parser.py — 62% (5/8)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| LA-1 | 500→400 error level boundary | CAUGHT | |
| LA-2 | 400→500 warn level boundary | CAUGHT | |
| LA-4 | WARNING→WARN normalization skip | SURVIVED | No test uses "WARNING" as log level |
| LA-5 | Wrong endpoint extraction (method vs path) | CAUGHT | |
| LA-6 | Skip continuation lines | CAUGHT | |
| LA-7 | JSON level field priority (level/severity swap) | SURVIVED | No test has both "level" and "severity" fields |
| LA-8 | JSON format detection wrong char | CAUGHT | |
| LA-10 | Default month fallback 1→0 | SURVIVED | No test with invalid month name |

### stats.py — 67% (4/6)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| LA-11 | Error count wrong key (ERROR→CRITICAL) | CAUGHT | |
| LA-12 | Warn count wrong key (WARN→WARNING) | CAUGHT | |
| LA-13 | Top errors 10→5 | CAUGHT | |
| LA-14 | Status group // 100 → // 10 | CAUGHT | |
| LA-15 | errors_per_hour counts ALL entries, not ERROR-only | SURVIVED | No test verifies per-hour error isolation |
| LA-16 | top_errors counts ALL messages, not ERROR-only | SURVIVED | No test verifies error-only filtering |

---

## Issues Found

### LA-F1: Error isolation in stats not tested (HIGH)
**Files**: `stats.py:10,16`  
Both `errors_per_hour` and `top_errors` filter by `level == "ERROR"`,
but removing these filters survives. Tests have mixed log levels but
never verify that non-ERROR entries are excluded from error-specific stats.

### LA-F2: WARNING normalization untested (MEDIUM)
**File**: `parser.py:107`  
The level extractor normalizes "WARNING" to "WARN" but no test uses
the "WARNING" keyword. This normalization survives mutation.

### LA-F3: JSON field priority order untested (MEDIUM)
**File**: `parser.py:152`  
JSON logs can have both "level" and "severity" fields. The parser
checks "level" first, but swapping priority to "severity" first
survives. No test has a JSON entry with both fields.

### LA-F4: Invalid month fallback untested (LOW)
**File**: `parser.py:51`  
`CLF_MONTHS.get(mon, 1)` defaults invalid months to January.
Changing default to 0 (invalid) survives — no test has an invalid month.

---

## Quality: 64% — second-weakest mutation score

The core parsing logic (CLF, syslog, JSON format detection) is solid,
but the stats module has a systematic weakness: tests verify aggregated
counts but never verify that the ERROR-only filters actually exclude
non-error entries. This means the stats could silently count all entries
as errors without any test catching it.
