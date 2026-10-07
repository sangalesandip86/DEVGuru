# Note Search CLI — Mutation Testing Results

**Project**: `note-search-cli/`  
**Date**: 2026-10-07  
**Tests**: 123 (all passing)  

---

## Aggregate Score: 11/12 = 91% (highest Python CLI score)

### search.py — 100% (5/5)

| ID | Mutation | Result |
|----|----------|--------|
| NS-1 | Force case-sensitive search | CAUGHT |
| NS-2 | Line number off by one (i vs i+1) | CAUGHT |
| NS-3 | Skip context before | CAUGHT |
| NS-4 | Skip context after | CAUGHT |
| NS-5 | Don't escape regex metacharacters | CAUGHT |

### notes.py — 86% (6/7)

| ID | Mutation | Result | Notes |
|----|----------|--------|-------|
| NS-7 | Skip empty title validation | CAUGHT | |
| NS-9 | Date filter inverted (>= to <=) | CAUGHT | |
| NS-11 | Skip save on delete | CAUGHT | |
| NS-12 | Word count uses len(content) not len(split()) | CAUGHT | |
| NS-13 | Tag sort order reversed | SURVIVED | Stats tag display order untested |
| NS-14 | next_id += 2 | CAUGHT | |
| NS-15 | Skip save on create | CAUGHT | |

---

## Quality: 91% — best mutation score of all Python CLI projects

Note Search is the strongest project tested. All search module mutations are
caught (100%), and the notes module has only one survivor (tag display order).
The high test count (123) correlates with high mutation score here, unlike
Quiz Engine (106 tests, 67%).

Key difference: Note Search tests use exact assertions and verify persistence.
Quiz Engine tests use assertIn and skip timing/boundary paths.
