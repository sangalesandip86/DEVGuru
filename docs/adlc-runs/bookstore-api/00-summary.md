# Bookstore REST API — Build Summary

**Date:** 2026-10-07  
**Location:** `tetaprojects/bookstore-api/`  
**Tests:** 89/89 passing (4.0s)  
**Type:** REST API (http.server + sqlite3, stdlib only)

## What Was Built

A full-featured bookstore REST API with CRUD operations for books and reviews, search, pagination, filtering, and statistics.

```
tetaprojects/bookstore-api/
  bookstore/
    __init__.py, db.py, validators.py, models.py,
    router.py, handlers.py, server.py
  tests/
    __init__.py, test_validators.py (22), test_models.py (34),
    test_api.py (33 integration)
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/books | List books (pagination, filter by author/genre) |
| GET | /api/books/search?q= | Search by title or author |
| GET | /api/books/{id} | Get book with avg rating |
| POST | /api/books | Create book (validates title, author, ISBN, price) |
| PUT | /api/books/{id} | Partial update |
| DELETE | /api/books/{id} | Delete (cascades reviews) |
| GET | /api/books/{id}/reviews | List reviews for a book |
| POST | /api/books/{id}/reviews | Add review (rating 1-5) |
| GET | /api/stats | Aggregate stats (total, avg rating, per-genre) |

## Test Coverage

- **test_validators.py** (22 tests): Book/review input validation — required fields, ISBN format (10/13 digits, dashes), price >= 0, rating 1-5, partial update mode
- **test_models.py** (34 tests): SQLite CRUD — create, get, list (pagination/filter), update, delete, search (case-insensitive, partial), stats, reviews, cascade delete, duplicate ISBN, SQL injection safety, unicode, long titles
- **test_api.py** (33 tests): Full HTTP integration — real HTTPServer on random port, all endpoints, validation (400/404/409/422 status codes), search, reviews, stats, SQL injection safety, full lifecycle test, trailing slash normalization

## Security Checks

| Check | Result |
|-------|--------|
| SQL injection (parameterized queries) | PASS — `'; DROP TABLE books; --` returns empty results, table intact |
| ISBN uniqueness enforced | PASS — 409 Conflict on duplicate |
| Foreign key cascade | PASS — deleting book removes reviews |
| Input validation on all write endpoints | PASS — 400/422 for invalid input |
| WAL mode + foreign keys enabled | PASS |

## Architecture Highlights

- **Router**: Regex-based URL pattern matching with path parameter extraction
- **Handlers**: RequestContext pattern separating HTTP from business logic
- **Models**: Parameterized SQL queries throughout (no string interpolation)
- **Validators**: Separate validation layer (book + review), partial update support
- **DB**: SQLite with WAL journal mode, foreign keys ON, Row factory for dict access
