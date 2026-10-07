# Mini ORM — Build & Evaluation Summary

## Project Overview
- **Type:** Python library (ORM + migration tool for SQLite)
- **Location:** `tetaprojects/mini-orm/`
- **Stack:** Python 3.10+, stdlib only (sqlite3)
- **Purpose:** Test ADLC pipeline's ability to generate framework/library code (not just CLI apps)

## Files Created

### Library (`mini_orm/`)
| File | Purpose | Lines |
|------|---------|-------|
| `__init__.py` | Package exports | 7 |
| `exceptions.py` | ValidationError, IntegrityError, MigrationError | 11 |
| `field.py` | Field descriptor with validation, type coercion, DB conversion | 107 |
| `model.py` | Base Model class with CRUD, metaclass, query API | 123 |
| `database.py` | Database wrapper with connection management | 53 |
| `query.py` | Filter/count query builder with parameterized SQL | 85 |
| `migration.py` | Migration apply, rollback, show, file discovery | 102 |
| `__main__.py` | CLI entry point (migrate/rollback/showmigrations) | 55 |

### Tests (`tests/`)
| File | Tests | Covers |
|------|-------|--------|
| `test_field.py` | 29 | Field validation, type coercion, boundaries, SQL types, DB conversion |
| `test_model.py` | 16 | CRUD, auto_now_add, defaults, unique, unicode, repr |
| `test_query.py` | 22 | All filter operators, ordering, pagination, SQL injection, count |
| `test_migration.py` | 12 | Apply, rollback, show, edge cases, missing up/down |
| `test_integration.py` | 7 | Full workflows: CRUD, multi-model, complex queries, migration lifecycle, SQL injection, unicode |
| **Total** | **86** | **All pass** |

## Test Results
```
Ran 86 tests in 2.270s
OK
```

## SQL Injection Safety ✓
All queries use parameterized `?` placeholders. Verified:
- `User.filter(db, name="'; DROP TABLE users; --")` — table survives ✓
- `User.filter(db, name__contains="'; DROP TABLE users; --")` — table survives ✓
- `Book(author_name="Robert'); DROP TABLE books;--")` saved and retrieved correctly ✓

## Mutation Testing Results

**Score: 15/18 caught = 83.3%**

| # | Mutation | File | Result |
|---|----------|------|--------|
| M1 | Negate delete guard (`is None` → `is not None`) | model.py | CAUGHT |
| M2 | Remove `self.id = None` after delete | model.py | CAUGHT |
| M3 | Skip `_validate()` in save | model.py | CAUGHT |
| M4 | Always INSERT, never UPDATE (`id is None or True`) | model.py | CAUGHT |
| M5 | Skip `db.commit()` after INSERT | model.py | **SURVIVED** |
| M6 | Remove `self.id = cursor.lastrowid` | model.py | CAUGHT |
| M7 | Change `gt` operator from `>` to `>=` | query.py | CAUGHT |
| M8 | Remove required field validation | field.py | CAUGHT |
| M9 | Change contains LIKE from `%val%` to `val%` | query.py | CAUGHT |
| M10 | Bool `to_db_value` always returns 1 | field.py | CAUGHT |
| M11 | Skip auto_now_add default setting | model.py | CAUGHT |
| M12 | `get()` always returns None | model.py | CAUGHT |
| M13 | `max_length` check `>` to `>=` | field.py | CAUGHT |
| M14 | Skip `db.commit()` after UPDATE | model.py | **SURVIVED** |
| M15 | Remove bool `from_db_value` conversion | field.py | **SURVIVED** |
| M16 | Don't reverse rollback order | migration.py | **SURVIVED** |
| M17 | Remove UNIQUE constraint in DDL | database.py | CAUGHT |
| M18 | `count()` returns n+1 | model.py | CAUGHT |

## Surviving Mutations — Root Cause Analysis

### M5 & M14: Commit removal not caught
- **Why:** SQLite autocommit within the same connection means data is visible even without explicit commit.
  Tests use the same `Database` instance for write and read, so uncommitted data is still accessible.
- **Fix needed:** Test that verifies data persistence by opening a *second* connection after save.

### M15: Bool from_db_value removal not caught
- **Why:** Tests use `assertTrue(found.active)` which passes for both `True` (bool) and `1` (int).
  SQLite stores bools as INTEGER, so without reconversion, raw `1` is returned.
- **Fix needed:** Use `assertIs(found.active, True)` or `assertIsInstance(found.active, bool)`.

### M16: Rollback order not caught
- **Why:** Test migrations are independent (no foreign keys between tables). Forward-order
  rollback works fine when there are no inter-table dependencies.
- **Fix needed:** Add test with dependent migrations (e.g., table B references table A via FK;
  rollback must drop B before A).

## Bugs / Issues Found

| ID | Severity | Description |
|----|----------|-------------|
| ORM-01 | Medium | `makemigrations` not implemented (prints stub message) |
| ORM-02 | Low | No `from_db_value` for `float` precision loss (SQLite REAL ↔ Python float) |
| ORM-03 | Low | `order_by` doesn't validate field name exists |
| ORM-04 | Low | No `__ne` (not equal) filter operator |

## Key Observations for ADLC Evaluation

1. **Library code quality is comparable to app code** — the ORM API is clean and functional
2. **Parameterized SQL throughout** — no SQL injection vulnerabilities
3. **Same mutation survival patterns** as other projects:
   - `db.commit()` removal survives because tests use same connection
   - Weak assertion types (`assertTrue` vs `assertIs`) let type-coercion mutations survive
   - Missing edge-case migrations (dependent tables) let order mutations survive
4. **Test coverage is good** (86 tests) but has the classic ADLC gap: tests verify behavior within a single session/connection, not across boundaries
