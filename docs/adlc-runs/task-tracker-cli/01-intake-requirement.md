# REQ-001: Task Tracker CLI — Requirement Specification

**Change Set:** CS-2e894c06  
**Stage:** INTAKE  
**Role:** product-owner  
**Date:** 2026-10-07  
**Status:** READY_FOR_APPROVAL

---

## 1. Requirement Summary

Build a Python command-line task tracker that lets users manage personal to-do items from the terminal with persistent JSON storage.

## 2. User Stories

### US-001: Add a task
**As a** user, **I want to** add a task with a description, **so that** I can track what I need to do.
- **Command:** `task-tracker add <description>`
- **AC-001.1:** A new task is created with an auto-incremented integer ID.
- **AC-001.2:** The task has status "todo", a `created_at` timestamp (ISO 8601), and `completed_at` is null.
- **AC-001.3:** The task is persisted to `~/.task-tracker/tasks.json`.
- **AC-001.4:** The CLI prints confirmation with the assigned task ID.

### US-002: List tasks
**As a** user, **I want to** list tasks filtered by status, **so that** I can see what's done and what remains.
- **Command:** `task-tracker list [--status done|todo|all]`
- **AC-002.1:** Default (no flag) shows all tasks.
- **AC-002.2:** `--status todo` shows only incomplete tasks.
- **AC-002.3:** `--status done` shows only completed tasks.
- **AC-002.4:** Output is a readable table with columns: ID, Status, Description, Created.

### US-003: Complete a task
**As a** user, **I want to** mark a task as done, **so that** I can track my progress.
- **Command:** `task-tracker done <id>`
- **AC-003.1:** The task's status changes from "todo" to "done".
- **AC-003.2:** `completed_at` is set to the current timestamp.
- **AC-003.3:** If the ID doesn't exist, print an error and exit with code 1.
- **AC-003.4:** If the task is already done, print a message and do nothing.

### US-004: View statistics
**As a** user, **I want to** see summary statistics, **so that** I know my overall progress.
- **Command:** `task-tracker stats`
- **AC-004.1:** Shows total count, done count, todo count.
- **AC-004.2:** Shows completion percentage (0% if no tasks).
- **AC-004.3:** Works correctly with an empty task list.

## 3. Non-Functional Requirements

- **NFR-001:** Python 3.10+ with stdlib only (no external dependencies).
- **NFR-002:** The storage directory `~/.task-tracker/` is auto-created on first use.
- **NFR-003:** Graceful error handling for corrupted JSON, missing files, invalid IDs.
- **NFR-004:** Exit code 0 on success, 1 on user error.
- **NFR-005:** Must include unit tests with ≥80% coverage.

## 4. Assumptions

| ID | Assumption | Impact | Expires |
|----|-----------|--------|---------|
| A-001 | Single-user tool, no concurrency handling needed | Simplifies storage layer | 2026-12-31 |
| A-002 | Task IDs are never reused (monotonically increasing) | Deletion not in scope | 2026-12-31 |
| A-003 | Description is a single string (spaces allowed, no multiline) | Simplifies parsing | 2026-12-31 |

## 5. Out of Scope
- Task deletion or editing
- Priority levels or tags
- Due dates
- Multi-user or remote sync
- Configuration file
