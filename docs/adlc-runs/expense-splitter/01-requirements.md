# Expense Splitter CLI — Requirement Specification

**Stage:** INTAKE  
**Date:** 2026-10-07  
**Status:** READY_FOR_APPROVAL

---

## User Stories

### US-001: Add person
**Command:** `expense-splitter add-person <name>`
- AC-001.1: Person added to the group with unique name.
- AC-001.2: Duplicate names rejected with error.
- AC-001.3: Confirmation printed: "Added person: {name}".

### US-002: Add expense
**Command:** `expense-splitter add-expense <payer> <amount> <description> [--split-with name1,name2,...]`
- AC-002.1: Expense recorded with auto-incremented ID.
- AC-002.2: If --split-with omitted, split equally among ALL people.
- AC-002.3: If --split-with given, split only among listed people (payer always included).
- AC-002.4: Penny rounding: if 3 split $10, two get $3.33, last gets $3.34.
- AC-002.5: Error if payer unknown, amount <= 0, or split-with contains unknown person.
- AC-002.6: Persisted to storage.

### US-003: View balances
**Command:** `expense-splitter balances`
- AC-003.1: Show net balances: "A owes B $X.XX".
- AC-003.2: Balances simplified: if A owes B $5 and B owes A $3, show "A owes B $2.00".
- AC-003.3: Zero balances not shown.
- AC-003.4: If no balances, print "All settled up!".

### US-004: Settle
**Command:** `expense-splitter settle <from> <to> <amount>`
- AC-004.1: Records a settlement payment.
- AC-004.2: Error if amount > what from owes to.
- AC-004.3: Error if amount <= 0 or persons unknown.
- AC-004.4: Confirmation: "Settled: {from} paid {to} ${amount}".

### US-005: Summary
**Command:** `expense-splitter summary`
- AC-005.1: Lists all expenses with ID, payer, amount, description, participants.
- AC-005.2: Shows current balances section.

### US-006: Export
**Command:** `expense-splitter export --format csv`
- AC-006.1: Outputs CSV to stdout with header: id,payer,amount,description,date,participants.
- AC-006.2: Descriptions with commas properly escaped/quoted.
- AC-006.3: Empty expense list produces header only.

## Non-Functional Requirements

- NFR-001: Python 3.10+, stdlib only.
- NFR-002: Storage at ~/.expense-splitter/data.json, auto-created.
- NFR-003: Amounts always displayed with 2 decimal places.
- NFR-004: Exit code 0 on success, 1 on error. Errors to stderr.
