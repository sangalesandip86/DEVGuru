# Expense Splitter CLI — Epic & Story Decomposition

**Change Set:** CS-b13e340f  
**Stage:** PLAN  
**Role:** product-planner  
**Date:** 2026-10-07

---

## Epic: EP-001 — Expense Splitter CLI

**Goal:** Deliver a working Python CLI that splits group expenses with penny rounding and balance simplification.

---

## Stories

### ST-001: Storage layer (FOUNDATION)
**Type:** FOUNDATION | **Priority:** P0 | **Size:** S  
**Description:** JSON persistence at `~/.expense-splitter/data.json` with atomic writes.

**Acceptance Criteria:**
- AC-ST001.1: `load()` returns empty data structure when no file exists, creates directory.
- AC-ST001.2: `load()` reads and validates existing JSON.
- AC-ST001.3: `load()` raises `StorageError` on corrupted JSON.
- AC-ST001.4: `save(data)` atomically writes via tempfile + os.replace.
- AC-ST001.5: `EXPENSE_SPLITTER_FILE` env var overrides default path.

### ST-002: Data models (FOUNDATION)
**Type:** FOUNDATION | **Priority:** P0 | **Size:** XS  
**Description:** Expense and Settlement dataclasses with serialization.

**Acceptance Criteria:**
- AC-ST002.1: Expense has: id, payer, amount (float), description, split_with (list[str]), created_at.
- AC-ST002.2: Settlement has: id, from_person, to_person, amount (float), created_at.
- AC-ST002.3: Both have `to_dict()` and `from_dict()` methods.

### ST-003: Ledger business logic (FOUNDATION)
**Type:** FOUNDATION | **Priority:** P0 | **Size:** M  
**Depends on:** ST-002  
**Description:** Pure business logic for splits, balances, and settlements.

**Acceptance Criteria:**
- AC-ST003.1: `compute_shares(amount, n)` returns list of n cents-based shares totaling amount exactly.
- AC-ST003.2: Penny rounding: $10 / 3 → [$3.34, $3.33, $3.33] (first person gets remainder).
- AC-ST003.3: `compute_balances(expenses, settlements, people)` returns simplified net balances.
- AC-ST003.4: Balance simplification: A owes B $5, B owes A $3 → A owes B $2.
- AC-ST003.5: `validate_settle(from_p, to_p, amount, balances)` raises ValueError if amount > owed or no debt.
- AC-ST003.6: Zero-balance pairs are omitted from results.

### ST-004: Add person command (FEATURE)
**Type:** FEATURE | **Priority:** P0 | **Size:** XS  
**Depends on:** ST-001  
**Description:** `add-person <name>` with case-insensitive uniqueness.

**Acceptance Criteria:**
- AC-ST004.1: Name stored lowercase, trimmed.
- AC-ST004.2: Duplicate rejected with error to stderr, exit 1.
- AC-ST004.3: Prints `"Added person: {name}"`.

### ST-005: Add expense command (FEATURE)
**Type:** FEATURE | **Priority:** P0 | **Size:** M  
**Depends on:** ST-001, ST-002, ST-003  
**Description:** `add-expense <payer> <amount> <description> [--split-with ...]`.

**Acceptance Criteria:**
- AC-ST005.1: Creates Expense with auto-incremented ID.
- AC-ST005.2: `--split-with` omitted → split among ALL people.
- AC-ST005.3: Amount > 0 validated; amount = 0 or negative → error.
- AC-ST005.4: Unknown payer or split member → error.
- AC-ST005.5: Penny rounding applied per ST-003.
- AC-ST005.6: Prints `"Expense #{id}: {payer} paid ${amount} for '{desc}' (split {n} ways)"`.

### ST-006: Balances command (FEATURE)
**Type:** FEATURE | **Priority:** P0 | **Size:** S  
**Depends on:** ST-003  
**Description:** `balances` shows simplified net debts.

**Acceptance Criteria:**
- AC-ST006.1: Shows `"{A} owes {B}: ${amount}"` for each net debt.
- AC-ST006.2: Zero balances omitted.
- AC-ST006.3: All settled → `"All balances are settled."`.

### ST-007: Settle command (FEATURE)
**Type:** FEATURE | **Priority:** P0 | **Size:** S  
**Depends on:** ST-001, ST-002, ST-003  
**Description:** `settle <from> <to> <amount>` records a payment.

**Acceptance Criteria:**
- AC-ST007.1: Creates Settlement with auto-incremented ID.
- AC-ST007.2: Validates amount > 0, ≤ debt owed.
- AC-ST007.3: Unknown persons → error.
- AC-ST007.4: Prints `"{from} paid {to} ${amount}. Remaining: ${remaining}"`.

### ST-008: Summary command (FEATURE)
**Type:** FEATURE | **Priority:** P0 | **Size:** S  
**Depends on:** ST-006  
**Description:** `summary` shows all expenses, people, and balances.

**Acceptance Criteria:**
- AC-ST008.1: Lists all people.
- AC-ST008.2: Lists all expenses with id, payer, amount, description.
- AC-ST008.3: Shows current net balances.

### ST-009: Export command (FEATURE)
**Type:** FEATURE | **Priority:** P0 | **Size:** S  
**Depends on:** ST-001, ST-002  
**Description:** `export --format csv` outputs CSV to stdout.

**Acceptance Criteria:**
- AC-ST009.1: CSV headers: id,payer,amount,description,split_with,created_at.
- AC-ST009.2: Commas in descriptions properly escaped.
- AC-ST009.3: Empty expense list → headers only.

### ST-010: CLI wiring + error handling (INTEGRATION)
**Type:** INTEGRATION | **Priority:** P0 | **Size:** S  
**Depends on:** ST-004 through ST-009  
**Description:** argparse setup, `__main__.py`, top-level error handling.

**Acceptance Criteria:**
- AC-ST010.1: `python -m expense_splitter add-person alice` works.
- AC-ST010.2: Errors caught at top level, printed to stderr, no tracebacks.
- AC-ST010.3: Exit code 0 on success, 1 on error.
- AC-ST010.4: `--help` shows usage.

### ST-011: Tests (TEST)
**Type:** TEST | **Priority:** P0 | **Size:** L  
**Depends on:** ST-010  
**Description:** Unit tests for each module + integration tests via subprocess.

**Acceptance Criteria:**
- AC-ST011.1: Unit tests for ledger: penny rounding, balance simplification, validation.
- AC-ST011.2: Unit tests for storage: init, load, save, corrupt handling.
- AC-ST011.3: Unit tests for commands: each command's happy path and error cases.
- AC-ST011.4: Integration tests: CLI via subprocess for end-to-end flows.
- AC-ST011.5: All tests use temp directories.

---

## Dependency Graph

```
ST-001 (Storage) ──────┐
ST-002 (Models) ───┐   │
                   ├───┤
ST-003 (Ledger) ───┘   │
                       ├──► ST-004 (Add Person)
                       ├──► ST-005 (Add Expense)
                       ├──► ST-006 (Balances)
                       ├──► ST-007 (Settle)
                       ├──► ST-008 (Summary)
                       ├──► ST-009 (Export)
                       └──► ST-010 (CLI) ──► ST-011 (Tests)
```
