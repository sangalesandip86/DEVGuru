# ADR-001: Task Tracker CLI Architecture

**Change Set:** CS-2e894c06  
**Stage:** ARCHITECTURE  
**Role:** architect  
**Date:** 2026-10-07  
**Status:** ACCEPTED

---

## 1. Context

REQ-001 specifies a Python CLI tool for personal task management. The tool is single-user, stdlib-only, with JSON file storage. This ADR captures the technology decisions, data model, and module layout.

## 2. Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.10+ | Per NFR-001 |
| CLI framework | `argparse` (stdlib) | No external deps; sufficient for 4 commands |
| Storage format | JSON | Per requirement; human-readable, stdlib `json` module |
| Storage location | `~/.task-tracker/tasks.json` | Per requirement |
| Test framework | `unittest` (stdlib) | No external deps; meets NFR-005 |
| Entry point | `__main__.py` + `setup` in pyproject.toml | Allows `python -m task_tracker` and `task-tracker` after install |

## 3. Data Model

### Task Object
```json
{
  "id": 1,
  "description": "Buy groceries",
  "status": "todo",
  "created_at": "2026-10-07T10:30:00",
  "completed_at": null
}
```

### Storage File (`tasks.json`)
```json
{
  "next_id": 4,
  "tasks": [
    {"id": 1, "description": "...", "status": "todo", "created_at": "...", "completed_at": null},
    {"id": 2, "description": "...", "status": "done", "created_at": "...", "completed_at": "..."}
  ]
}
```

- `next_id`: monotonically increasing counter, never reused (per A-002).
- `tasks`: ordered list of all task objects.

## 4. Module Layout

```
task-tracker-cli/
  pyproject.toml
  task_tracker/
    __init__.py
    __main__.py          # Entry point: parse args, dispatch to commands
    cli.py               # argparse setup, command dispatch
    commands.py           # add(), list_tasks(), done(), stats()
    storage.py           # load/save JSON, auto-create directory
    models.py            # Task dataclass, serialization
  tests/
    __init__.py
    test_commands.py     # Unit tests for each command
    test_storage.py      # Unit tests for storage layer
    test_cli.py          # Integration tests for CLI parsing
```

## 5. Key Design Decisions

### 5.1 Separation of concerns
- **cli.py** handles argument parsing only — no business logic.
- **commands.py** contains the four command implementations. Each returns a result; printing is done by the caller.
- **storage.py** is the only module that touches the filesystem.
- **models.py** defines the Task dataclass and its JSON serialization.

### 5.2 Error handling strategy
- `storage.py` raises specific exceptions for I/O errors and corrupt JSON.
- `cli.py` catches exceptions at the top level, prints user-friendly messages, and exits with code 1.
- No bare `except:` clauses.

### 5.3 ID generation
- `next_id` in the storage file ensures IDs survive across sessions.
- On first use, storage file is initialized with `{"next_id": 1, "tasks": []}`.

## 6. Risks

| Risk | Mitigation |
|------|-----------|
| Concurrent writes corrupt JSON | Out of scope per A-001; single-user tool |
| Large task lists slow down read/write | Acceptable for personal use; thousands of tasks load in ms |
