# Full-Stack Todo App — Build & Test Summary

**Tech Stack:** Node.js v24 (zero dependencies) + Vanilla HTML/CSS/JS  
**Location:** `tetaprojects/fullstack-todo/`  
**Date:** 2026-10-07

---

## Files Created

### Backend (Node.js, stdlib only)
| File | Purpose |
|------|---------|
| `server.js` | HTTP server with port 0 support for tests |
| `router.js` | URL parsing, route matching, static file serving |
| `handlers.js` | Request handlers for all API endpoints |
| `store.js` | In-memory todo storage with CRUD, filter, sort |
| `validators.js` | Input validation for create/update/bulk-delete |

### Frontend
| File | Purpose |
|------|---------|
| `index.html` | SPA with form, filter tabs, todo list, stats bar |
| `static/style.css` | Dark mode via CSS custom properties, responsive at 480px |
| `static/app.js` | Fetch API, DOM manipulation, inline edit, theme toggle |

### Tests
| File | Tests | Type |
|------|-------|------|
| `tests/test-store.js` | 28 | Unit — data store operations |
| `tests/test-validators.js` | 20 | Unit — validation logic |
| `tests/test-api.js` | 25 | Integration — full HTTP round-trips |
| `tests/test-static.js` | 11 | Integration — static serving, MIME, XSS |
| **Total** | **84** | **84/84 pass** |

---

## API Endpoints Implemented

| Method | Path | Status |
|--------|------|--------|
| GET | `/` | Serves index.html |
| GET | `/static/*` | Serves CSS/JS with correct MIME types |
| GET | `/api/todos` | List (supports `?status=active\|completed&sort=date\|priority`) |
| POST | `/api/todos` | Create todo (201) |
| PUT | `/api/todos/:id` | Update todo |
| DELETE | `/api/todos/:id` | Delete todo (204) |
| PATCH | `/api/todos/:id/toggle` | Toggle complete/incomplete |
| POST | `/api/todos/bulk-delete` | Delete completed todos by IDs |
| GET | `/api/todos/stats` | Returns {total, active, completed, overdue} |

---

## Security Checks

| Check | Result |
|-------|--------|
| XSS in todo text | **SAFE** — uses `textContent`, not `innerHTML` for user data |
| Path traversal `/static/../server.js` | **BLOCKED** — `path.basename()` strips traversal |
| Invalid JSON body | Returns 400 with error message |
| Text injection (500+ chars) | Rejected by validator |
| Priority injection | Only `high/medium/low` accepted |

---

## Mutation Testing Results

**Score: 85.0% (17/20 killed)**

| ID | Mutation | Result |
|----|----------|--------|
| M1 | Remove priority default | KILLED |
| M2 | Toggle always sets true | KILLED |
| M3 | Toggle never clears completedAt | KILLED |
| M4 | bulkDelete ignores completed check | KILLED |
| M5 | Stats counts completed as overdue | KILLED |
| M6 | Accept text > 500 chars | KILLED |
| M7 | Accept any priority value | KILLED |
| M8 | Accept non-boolean completed | KILLED |
| M9 | Return 200 instead of 201 on create | KILLED |
| M10 | Return 200 instead of 204 on delete | KILLED |
| M11 | Ignore status filter | KILLED |
| M12 | Reverse priority sort order | KILLED |
| M13 | Parse ID as float instead of int | **SURVIVED** |
| M14 | Accept empty ids array | KILLED |
| M15 | Update returns {} for nonexistent | KILLED |
| M16 | Sort by date does nothing | KILLED |
| M17 | Active filter returns completed | KILLED |
| M18 | getAll returns reference (mutability) | **SURVIVED** |
| M19 | Accept malformed JSON silently | **SURVIVED** |
| M20 | Stats active count wrong | KILLED |

### Surviving Mutation Analysis

1. **M13 (float ID parse):** `parseFloat("3")` still returns `3`, so integer-only IDs work identically. Tests don't send float-like IDs (e.g., `3.5`). **Gap:** No test for non-integer URL path segments.

2. **M18 (mutability leak):** `getAll()` returns the internal array reference instead of a copy. Tests don't modify the returned array, so no assertion breaks. **Gap:** No test verifying immutability of returned data.

3. **M19 (malformed JSON):** `readBody()` accepting malformed JSON as `{}` doesn't cause failures because an empty-body POST to `/api/todos` fails validation ("text is required"). **Gap:** However, a PUT with malformed JSON would silently produce a no-op update instead of a 400 error.

---

## Findings

| ID | Severity | Category | Description |
|----|----------|----------|-------------|
| FT-01 | LOW | Test Gap | No test for float/non-integer IDs in URL path — M13 survived |
| FT-02 | LOW | Design | `getAll()` returns mutable reference — could cause bugs if callers modify the array |
| FT-03 | MEDIUM | Test Gap | No test sends malformed JSON body to PUT endpoint — M19 survived |
| FT-04 | LOW | Feature | `escapeHtml()` function defined in app.js but never called (textContent used instead) — dead code |
| FT-05 | LOW | UX | Dark mode toggle saves to localStorage but `[data-theme="light"]` has no custom CSS (falls through to `:root` defaults) |

---

## UI Features Verified (Code Review)

- [x] Add todo: text + priority dropdown + optional due date
- [x] Todo list: checkboxes, priority badges (high=red, medium=yellow, low=green)
- [x] Filter tabs: All | Active | Completed
- [x] Inline edit (click text to edit, Enter/Escape/blur to save/cancel)
- [x] Delete button with confirmation dialog
- [x] Stats bar: "N active, N completed, N overdue"
- [x] Dark mode toggle with localStorage persistence
- [x] Responsive: CSS media query at 480px breakpoint
- [x] Empty state: "No todos yet!" message
- [x] Bulk delete completed button (shown only when completed exist)
