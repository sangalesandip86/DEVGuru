# Task Tracker CLI — Epic & Story Decomposition

**Change Set:** CS-2e894c06  
**Stage:** PLAN  
**Role:** product-planner  
**Date:** 2026-10-07

---

## Epic: EP-001 — Task Tracker CLI

**Goal:** Deliver a working Python CLI that manages personal tasks with JSON persistence.  
**Milestone:** M-001 — MVP (all 4 commands working with tests)

---

## Stories

### ST-001: Storage layer (FOUNDATION)
**Type:** FOUNDATION  
**Priority:** P0 — blocks all other stories  
**Size:** S  

**Description:** Implement the storage module that reads/writes tasks to `~/.task-tracker/tasks.json`, including auto-creation of the directory and file.

**Acceptance Criteria:**
- AC-ST001.1: `load()` returns `{"next_id": 1, "tasks": []}` when no file exists, and creates the directory.
- AC-ST001.2: `load()` reads and parses an existing valid JSON file.
- AC-ST001.3: `load()` raises `StorageError` on corrupted JSON.
- AC-ST001.4: `save(data)` atomically writes the data to the JSON file.
- AC-ST001.5: Storage path uses `pathlib.Path.home() / ".task-tracker" / "tasks.json"`.

---

### ST-002: Task model (FOUNDATION)
**Type:** FOUNDATION  
**Priority:** P0  
**Size:** XS  

**Description:** Define the Task dataclass with serialization to/from dict.

**Acceptance Criteria:**
- AC-ST002.1: Task has fields: `id` (int), `description` (str), `status` (str: "todo"|"done"), `created_at` (str, ISO 8601), `completed_at` (str|None).
- AC-ST002.2: `Task.from_dict(d)` creates a Task from a dictionary.
- AC-ST002.3: `Task.to_dict()` returns a plain dictionary suitable for JSON serialization.

---

### ST-003: Add command (FEATURE)
**Type:** FEATURE  
**Priority:** P0  
**Size:** S  
**Depends on:** ST-001, ST-002  

**Description:** Implement the `add <description>` command.

**Acceptance Criteria:**
- AC-ST003.1: Creates a task with auto-incremented ID from `next_id`, status "todo", `created_at` = now, `completed_at` = None.
- AC-ST003.2: Increments `next_id` in storage.
- AC-ST003.3: Persists the new task to JSON.
- AC-ST003.4: Prints `"Added task {id}: {description}"`.
- AC-ST003.5: Multi-word descriptions are handled correctly.

---

### ST-004: List command (FEATURE)
**Type:** FEATURE  
**Priority:** P0  
**Size:** S  
**Depends on:** ST-001, ST-002  

**Description:** Implement the `list [--status done|todo|all]` command.

**Acceptance Criteria:**
- AC-ST004.1: With no flag, shows all tasks.
- AC-ST004.2: `--status todo` filters to status == "todo".
- AC-ST004.3: `--status done` filters to status == "done".
- AC-ST004.4: Output formatted as a readable table: ID | Status | Description | Created.
- AC-ST004.5: Empty list prints `"No tasks found."`.

---

### ST-005: Done command (FEATURE)
**Type:** FEATURE  
**Priority:** P0  
**Size:** S  
**Depends on:** ST-001, ST-002  

**Description:** Implement the `done <id>` command.

**Acceptance Criteria:**
- AC-ST005.1: Sets task status to "done" and `completed_at` to current timestamp.
- AC-ST005.2: Persists the change.
- AC-ST005.3: Prints `"Task {id} marked as done."`.
- AC-ST005.4: If ID not found, prints `"Error: Task {id} not found."` and exits with code 1.
- AC-ST005.5: If task already done, prints `"Task {id} is already done."` and does nothing.

---

### ST-006: Stats command (FEATURE)
**Type:** FEATURE  
**Priority:** P0  
**Size:** XS  
**Depends on:** ST-001, ST-002  

**Description:** Implement the `stats` command.

**Acceptance Criteria:**
- AC-ST006.1: Prints total, done, and todo counts.
- AC-ST006.2: Prints completion percentage as integer (e.g., "67%").
- AC-ST006.3: With no tasks, shows "0 total" and "0%" completion.

---

### ST-007: CLI entry point (INTEGRATION)
**Type:** INTEGRATION  
**Priority:** P0  
**Size:** S  
**Depends on:** ST-003, ST-004, ST-005, ST-006  

**Description:** Wire up argparse and `__main__.py` to dispatch to command functions.

**Acceptance Criteria:**
- AC-ST007.1: `python -m task_tracker add "Buy milk"` works.
- AC-ST007.2: Unknown commands print help and exit with code 1.
- AC-ST007.3: `--help` shows usage for each subcommand.
- AC-ST007.4: Errors are caught at the top level and printed without tracebacks.

---

### ST-008: Unit tests (TEST)
**Type:** TEST  
**Priority:** P0  
**Size:** M  
**Depends on:** ST-007  

**Description:** Write unit tests for all modules achieving ≥80% coverage.

**Acceptance Criteria:**
- AC-ST008.1: Tests for storage: init, load, save, corrupt file handling.
- AC-ST008.2: Tests for each command: add, list (all filters), done (success + errors), stats (empty + populated).
- AC-ST008.3: Tests use a temporary directory, never `~/.task-tracker/`.
- AC-ST008.4: All tests pass with `python -m unittest discover`.

---

## Dependency Graph

```
ST-001 (Storage) ──┐
                    ├──► ST-003 (Add) ──┐
ST-002 (Model)  ───┤                    │
                    ├──► ST-004 (List) ──┤
                    ├──► ST-005 (Done) ──┼──► ST-007 (CLI) ──► ST-008 (Tests)
                    └──► ST-006 (Stats) ─┘
```
