# ADR-001: Expense Splitter CLI Architecture

**Change Set:** CS-b13e340f  
**Stage:** ARCHITECTURE  
**Role:** architect  
**Date:** 2026-10-07  
**Status:** ACCEPTED

---

## 1. Context

REQ-001 specifies a Python CLI for splitting group expenses. Single-user, stdlib-only, JSON storage. This ADR captures technology decisions, data model, and module layout.

## 2. Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.10+ | Per NFR-001 |
| CLI framework | `argparse` (stdlib) | No external deps; subcommands for 6 commands |
| Storage format | JSON | Per requirement; human-readable |
| Storage location | `~/.expense-splitter/data.json` | Per requirement |
| Test framework | `unittest` (stdlib) | No external deps; meets NFR-005 |
| CSV output | `csv` module (stdlib) | Handles quoting/escaping properly |
| Decimal arithmetic | `round()` with int cents internally | Avoids floating-point errors for penny rounding |

## 3. Data Model

### Person
```json
{"name": "alice"}
```

### Expense
```json
{
  "id": 1,
  "payer": "alice",
  "amount": 10.00,
  "description": "Lunch",
  "split_with": ["alice", "bob", "carol"],
  "created_at": "2026-10-07T12:00:00"
}
```

### Settlement
```json
{
  "id": 1,
  "from_person": "bob",
  "to_person": "alice",
  "amount": 3.33,
  "created_at": "2026-10-07T12:30:00"
}
```

### Storage File (`data.json`)
```json
{
  "next_expense_id": 2,
  "next_settlement_id": 2,
  "people": ["alice", "bob", "carol"],
  "expenses": [...],
  "settlements": [...]
}
```

## 4. Module Layout

```
tetaprojects/expense-splitter-cli/
  pyproject.toml
  expense_splitter/
    __init__.py
    __main__.py          # Entry: python -m expense_splitter
    cli.py               # argparse setup, command dispatch, error handling
    commands.py           # Command implementations (add_person, add_expense, etc.)
    ledger.py            # Business logic: compute shares, balances, simplify debts
    storage.py           # JSON load/save, auto-create directory
    models.py            # Dataclasses: Expense, Settlement
    formatters.py        # Output formatting: tables, CSV export
  tests/
    __init__.py
    test_models.py       # Unit: dataclass construction/serialization
    test_ledger.py       # Unit: split calculation, balance simplification, penny rounding
    test_storage.py      # Unit: JSON persistence
    test_commands.py     # Unit: command functions
    test_formatters.py   # Unit: CSV and table formatting
    test_cli.py          # Integration: full CLI via subprocess
```

## 5. Key Design Decisions

### 5.1 Penny rounding strategy
Split amounts are computed in cents (integers) to avoid floating-point errors:
1. Convert amount to cents: `total_cents = round(amount * 100)`
2. Base share: `base = total_cents // n`
3. Remainder: `rem = total_cents % n`
4. First `rem` people get `base + 1` cents; rest get `base` cents
5. Convert back to dollars for display

### 5.2 Balance simplification
- Maintain a balance matrix `balances[A][B]` = amount A owes B.
- When computing net balances, for each pair (A, B): net = balances[A][B] - balances[B][A].
- If net > 0: A owes B net. If net < 0: B owes A |net|. If 0: omit.

### 5.3 Separation of concerns
- **cli.py**: argument parsing only, error catching at top level.
- **commands.py**: orchestration — loads data, calls ledger, saves, returns output strings.
- **ledger.py**: pure business logic — no I/O, no formatting. Takes data dicts, returns results.
- **storage.py**: only module that touches filesystem.
- **formatters.py**: only module that formats output (tables, CSV).
- **models.py**: dataclasses with to_dict/from_dict.

### 5.4 Case-insensitive names
Names stored in lowercase. Input normalized via `.strip().lower()` at the CLI boundary.

### 5.5 Error handling
- `storage.py` raises `StorageError` for I/O issues.
- `ledger.py` raises `ValueError` for business rule violations (unknown person, invalid amount, over-settle).
- `cli.py` catches both, prints to stderr, exits with code 1.

## 6. Risks

| Risk | Mitigation |
|------|-----------|
| Float precision in amounts | Use cents (int) for internal calculations |
| Large groups slow balance computation | O(n²) is fine for <100 people |
| Concurrent writes | Out of scope per A-002 |
