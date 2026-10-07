# REQ-001: Expense Splitter CLI — Requirement Specification

**Change Set:** CS-b13e340f  
**Stage:** INTAKE  
**Role:** product-owner  
**Date:** 2026-10-07  
**Status:** READY_FOR_APPROVAL

---

## 1. Requirement Summary

Build a Python command-line expense splitter that lets a group of friends track shared expenses, compute who owes whom, and settle debts — all with persistent JSON storage.

## 2. User Stories

### US-001: Add a person
**As a** user, **I want to** add a person to the expense group, **so that** they can participate in splits.
- **Command:** `expense-splitter add-person <name>`
- **AC-001.1:** A new person is added with a unique, case-insensitive name.
- **AC-001.2:** Duplicate names (case-insensitive) are rejected with an error.
- **AC-001.3:** Confirmation message printed: `"Added person: {name}"`.

### US-002: Add an expense
**As a** user, **I want to** record an expense paid by someone, **so that** costs can be split fairly.
- **Command:** `expense-splitter add-expense <payer> <amount> <description> [--split-with name1,name2,...]`
- **AC-002.1:** Expense created with auto-incremented ID, payer, amount, description, split_with list, created_at.
- **AC-002.2:** If `--split-with` omitted, split among ALL people in the group.
- **AC-002.3:** Amount validated: must be > 0, up to 2 decimal places.
- **AC-002.4:** Payer must be a known person; all names in `--split-with` must be known.
- **AC-002.5:** Penny rounding: if 3 people split $10.00, shares are $3.33, $3.33, $3.34 (last person gets remainder).
- **AC-002.6:** Confirmation: `"Expense #{id}: {payer} paid ${amount} for '{description}' (split {n} ways)"`.
- **AC-002.7:** Payer can be included in the split (they owe themselves, which nets to zero for their portion).

### US-003: View balances
**As a** user, **I want to** see who owes whom, **so that** I know the current state of debts.
- **Command:** `expense-splitter balances`
- **AC-003.1:** Shows simplified net balances (A owes B $5 + B owes A $3 → A owes B $2).
- **AC-003.2:** Zero-balance pairs are omitted.
- **AC-003.3:** Amounts shown to 2 decimal places.
- **AC-003.4:** If all balances are settled, prints `"All balances are settled."`.

### US-004: Settle a debt
**As a** user, **I want to** record a payment between people, **so that** debts are reduced.
- **Command:** `expense-splitter settle <from> <to> <amount>`
- **AC-004.1:** Records a settlement reducing the debt from `from` to `to`.
- **AC-004.2:** Amount must be > 0 and ≤ the current debt owed.
- **AC-004.3:** Both names must be known persons.
- **AC-004.4:** Error if settling more than owed or if no debt exists in that direction.
- **AC-004.5:** Confirmation: `"{from} paid {to} ${amount}. Remaining: ${remaining}"`.

### US-005: View summary
**As a** user, **I want to** see all expenses and current balances, **so that** I have a complete picture.
- **Command:** `expense-splitter summary`
- **AC-005.1:** Lists all people.
- **AC-005.2:** Lists all expenses with ID, payer, amount, description, date.
- **AC-005.3:** Shows current net balances.

### US-006: Export to CSV
**As a** user, **I want to** export transactions as CSV, **so that** I can use them in spreadsheets.
- **Command:** `expense-splitter export --format csv`
- **AC-006.1:** Outputs CSV to stdout with headers: id, payer, amount, description, split_with, created_at.
- **AC-006.2:** Descriptions with commas are properly escaped (quoted).
- **AC-006.3:** Empty expense list outputs headers only.

## 3. Non-Functional Requirements

- **NFR-001:** Python 3.10+ with stdlib only (no external dependencies).
- **NFR-002:** Storage directory `~/.expense-splitter/` auto-created on first use.
- **NFR-003:** Graceful error handling for corrupted JSON, missing files, invalid inputs.
- **NFR-004:** Exit code 0 on success, 1 on user error. Errors to stderr.
- **NFR-005:** Must include unit tests and integration tests (CLI via subprocess).

## 4. Assumptions

| ID | Assumption | Impact | Expires |
|----|-----------|--------|---------|
| A-001 | Single currency (USD) | No currency conversion needed | 2027-06-30 |
| A-002 | Single-user tool, no concurrency | Simplifies storage | 2027-06-30 |
| A-003 | Names are simple strings (no commas, used as identifiers) | Simplifies parsing of --split-with | 2027-06-30 |

## 5. Out of Scope
- Multi-currency support
- Percentage-based splits (unequal)
- Expense editing or deletion
- Web/mobile interface
- Authentication or multi-user access
