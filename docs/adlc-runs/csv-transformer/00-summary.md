# ADLC Run Summary — CSV Transformer CLI

**Date:** 2026-10-07  
**Output:** `tetaprojects/csv-transformer-cli/`  
**Tests:** 95/95 pass (after 1 fix)

## What Was Built

```
tetaprojects/csv-transformer-cli/
  csvt/
    __init__.py, __main__.py, cli.py, reader.py,
    filters.py, sorter.py, stats.py, joiner.py, formatter.py
  tests/
    __init__.py, test_reader.py, test_filters.py,
    test_sorter.py, test_stats.py, test_joiner.py, test_cli.py
    fixtures/
      products.csv, orders.csv, numbers.csv, empty.csv,
      mixed_numeric.csv, quoted.csv
```

**Commands:** filter, sort, select, stats, join, head, convert  
**Tests:** 95 total (68 unit + 27 integration via subprocess)

## Bug Found During Development

**N/A in numeric filter (fixed):** `filter --where "price>0"` included rows with `price=N/A` because the string comparison `"N/A" > "0"` evaluates True lexicographically. Fixed by returning False when the filter value is numeric but the cell value isn't.

## Edge Cases Verified

- CSV with quoted commas and embedded newlines
- BOM-marked UTF-8 files
- Dollar-prefixed numeric values ($1,234.56)
- N/A and empty values in numeric contexts
- Numeric sorting (not lexicographic)
- Inner/left/outer joins with missing matches
- Duplicate column names in joins (auto-suffixed `_2`)
- One-to-many joins
- Pipe-compatible CSV output
- Errors to stderr, exit code 1
