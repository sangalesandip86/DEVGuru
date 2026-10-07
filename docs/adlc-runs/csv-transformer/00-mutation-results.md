# CSV Transformer CLI — Mutation Testing Results

**Project**: `tetaprojects/csv-transformer-cli/`  
**Date**: 2026-10-07  
**Tests**: 95 (all passing)  

---

## Aggregate Score: 14/17 = 82%

### filters.py + sorter.py — 91% (10/11)

| ID | Mutation | Result |
|----|----------|--------|
| CT-1 | `contains` case-sensitive | CAUGHT |
| CT-2 | `eq` inverted | CAUGHT |
| CT-3 | `ne` inverted | CAUGHT |
| CT-4 | `gt` to `ge` | CAUGHT |
| CT-5 | `lt` to `le` | CAUGHT |
| CT-6 | Skip column validation in filter | CAUGHT |
| CT-7 | Non-numeric comparison returns True | CAUGHT |
| CT-8 | Descending sort inverted | CAUGHT |
| CT-9 | Skip column validation in sort | CAUGHT |
| CT-10 | Numeric default 0.0→1.0 for None | SURVIVED |
| CT-11 | Force all non-numeric sort | CAUGHT |

### stats.py — 67% (4/6)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| CT-12 | Mean divided by n+1 | CAUGHT | |
| CT-13 | Median even formula (skip averaging) | CAUGHT | |
| CT-14 | Population vs sample variance | CAUGHT | |
| CT-15 | Numeric threshold wrong | CAUGHT | |
| CT-16 | Most common 5→3 | SURVIVED | Test data has <3 unique values |
| CT-17 | Empty count inversion | SURVIVED | No test verifies empty_count value |

---

## Quality: 82% — second-highest Python CLI score

Filters are very well tested (all comparison operators caught). The stats
module is weaker because tests verify structure (keys exist, types correct)
but don't assert specific aggregate values like empty_count or the exact
number of most_common entries.
