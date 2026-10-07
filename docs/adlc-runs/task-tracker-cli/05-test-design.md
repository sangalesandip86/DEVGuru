# Task Tracker CLI — Test Design (Implementation-Blind)

**Change Set:** CS-2e894c06  
**Stage:** TEST (design)  
**Role:** qa-derive  
**Date:** 2026-10-07  
**Source:** Acceptance criteria from 03-plan-stories.md only — no implementation code reviewed.

---

## Test Strategy

- **Approach:** Black-box testing derived from acceptance criteria.
- **Framework:** Python `unittest` (stdlib).
- **Isolation:** All tests use temporary directories; never touch `~/.task-tracker/`.
- **Coverage target:** ≥80% line coverage per NFR-005.

---

## Test Cases by Story

### TC-ST001: Storage Layer

| ID | AC Ref | Test | Expected |
|----|--------|------|----------|
| TC-001.1 | AC-ST001.1 | Load from non-existent path | Returns default `{"next_id": 1, "tasks": []}`, directory created |
| TC-001.2 | AC-ST001.2 | Load from valid existing JSON | Returns parsed data matching file contents |
| TC-001.3 | AC-ST001.3 | Load from corrupted JSON | Raises `StorageError` |
| TC-001.4 | AC-ST001.4 | Save and reload data | Saved data matches after round-trip |
| TC-001.5 | AC-ST001.5 | Storage path construction | Uses `Path.home() / ".task-tracker" / "tasks.json"` |

### TC-ST002: Task Model

| ID | AC Ref | Test | Expected |
|----|--------|------|----------|
| TC-002.1 | AC-ST002.1 | Task fields present | id (int), description (str), status (str), created_at (str), completed_at (str|None) |
| TC-002.2 | AC-ST002.2 | from_dict round-trip | `Task.from_dict(d)` produces Task with matching fields |
| TC-002.3 | AC-ST002.3 | to_dict produces JSON-safe dict | All values are str, int, or None |

### TC-ST003: Add Command

| ID | AC Ref | Test | Expected |
|----|--------|------|----------|
| TC-003.1 | AC-ST003.1 | Add first task | ID=1, status="todo", created_at set, completed_at=None |
| TC-003.2 | AC-ST003.2 | Add second task | ID=2, next_id incremented to 3 |
| TC-003.3 | AC-ST003.3 | Persistence | Task exists in JSON after add |
| TC-003.4 | AC-ST003.4 | Output message | Prints "Added task {id}: {description}" |
| TC-003.5 | AC-ST003.5 | Multi-word description | `add Buy milk and eggs` stores full phrase |

### TC-ST004: List Command

| ID | AC Ref | Test | Expected |
|----|--------|------|----------|
| TC-004.1 | AC-ST004.1 | List all (default) | Shows both todo and done tasks |
| TC-004.2 | AC-ST004.2 | List --status todo | Shows only todo tasks |
| TC-004.3 | AC-ST004.3 | List --status done | Shows only done tasks |
| TC-004.4 | AC-ST004.4 | Output format | Table with ID, Status, Description, Created columns |
| TC-004.5 | AC-ST004.5 | Empty list | Prints "No tasks found." |

### TC-ST005: Done Command

| ID | AC Ref | Test | Expected |
|----|--------|------|----------|
| TC-005.1 | AC-ST005.1 | Mark todo as done | status → "done", completed_at set |
| TC-005.2 | AC-ST005.2 | Persistence after done | JSON file reflects change |
| TC-005.3 | AC-ST005.3 | Success output | Prints "Task {id} marked as done." |
| TC-005.4 | AC-ST005.4 | Non-existent ID | Prints "Error: Task {id} not found.", exit code 1 |
| TC-005.5 | AC-ST005.5 | Already-done task | Prints "Task {id} is already done.", no change |

### TC-ST006: Stats Command

| ID | AC Ref | Test | Expected |
|----|--------|------|----------|
| TC-006.1 | AC-ST006.1 | Counts correct | total, done, todo match actual counts |
| TC-006.2 | AC-ST006.2 | Percentage format | Integer percentage (e.g., "67%") |
| TC-006.3 | AC-ST006.3 | Empty task list | "0 total", "0%" |

### TC-ST007: CLI Entry Point

| ID | AC Ref | Test | Expected |
|----|--------|------|----------|
| TC-007.1 | AC-ST007.1 | Module invocation | `python -m task_tracker add "test"` succeeds |
| TC-007.2 | AC-ST007.2 | Unknown command | Prints help, exit code ≠ 0 |
| TC-007.3 | AC-ST007.3 | Help flag | `--help` shows usage text |
| TC-007.4 | AC-ST007.4 | Error display | Exceptions shown as user-friendly messages, no tracebacks |

---

## Edge Cases (Cross-cutting)

| ID | Scenario | Expected |
|----|----------|----------|
| TC-E01 | Very long description (1000+ chars) | Accepted and stored correctly |
| TC-E02 | Description with special characters (`"`, `\`, `'`) | Stored and displayed correctly |
| TC-E03 | done with non-integer ID argument | Error message, exit code 1 |
| TC-E04 | list with invalid --status value | Error message from argparse |
| TC-E05 | Storage file deleted between operations | Graceful re-initialization |

---

## Traceability Matrix

| Story | ACs | Test Cases | Coverage |
|-------|-----|------------|----------|
| ST-001 | 5 | TC-001.1 – TC-001.5 | 100% |
| ST-002 | 3 | TC-002.1 – TC-002.3 | 100% |
| ST-003 | 5 | TC-003.1 – TC-003.5 | 100% |
| ST-004 | 5 | TC-004.1 – TC-004.5 | 100% |
| ST-005 | 5 | TC-005.1 – TC-005.5 | 100% |
| ST-006 | 3 | TC-006.1 – TC-006.3 | 100% |
| ST-007 | 4 | TC-007.1 – TC-007.4 | 100% |
| ST-008 | 4 | (meta: ST-008 describes the test implementation itself) | — |
