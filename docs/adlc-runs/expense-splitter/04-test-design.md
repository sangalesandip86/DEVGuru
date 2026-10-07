# Expense Splitter CLI — Test Design

> Stage: TEST (design) | Role: @qa-derive | Run: expense-splitter-run-001
> Change Set: CS-b13e340f | Implementation-blind: NO (post-implementation)

## 1. Test Scope

Derived from `03-plan-stories.md` acceptance criteria and `02-architecture-adr.md` contracts.

### 1.1 Unit Test Targets

| Module | Key Behaviors | AC Ref |
|--------|--------------|--------|
| models.py | Expense/Settlement creation, serialization roundtrip | ST-002 |
| storage.py | Create-on-miss, corrupt JSON, missing keys, atomic save | ST-001 |
| ledger.py | compute_shares (penny rounding), compute_balances (simplification), validate_settle | ST-003 |
| formatters.py | format_balances, format_summary, format_csv (comma escaping) | ST-009, ST-010 |
| commands.py | add_person, add_expense, balances, settle, summary, export_csv | ST-004–ST-009 |

### 1.2 Integration Test Targets (CLI via subprocess)

| Scenario | Commands | Verification |
|----------|----------|-------------|
| Happy path: add-person | `add-person Alice` | exit 0, "Added person: alice" |
| Duplicate person | `add-person Alice` × 2 | exit 1, stderr "already exists" |
| Happy path: add-expense | `add-person` + `add-expense` | exit 0, "Expense #1" |
| Custom split | `add-expense --split-with` | exit 0, correct split count |
| Unknown payer | `add-expense eve ...` | exit 1, stderr "Unknown person" |
| Negative amount | `add-expense alice -5 ...` | exit 1 |
| Balances: no debt | `add-person` only | exit 0, "settled" |
| Balances: with debt | `add-person` + `add-expense` | exit 0, "owes" |
| Settle: valid | full flow | exit 0, "Remaining: $0.00" |
| Settle: over-settle | amount > debt | exit 1, "Cannot settle" |
| Summary | full flow | exit 0, People/Expenses/Balances sections |
| Export CSV | full flow | exit 0, proper header + data rows |
| Error routing | bad input | exit 1, stderr only, no stdout |
| End-to-end | 3-person multi-expense + settle | correct net balances |

## 2. Test Case Matrix

### 2.1 compute_shares (8 cases)

| ID | Input | Expected | Rationale |
|----|-------|----------|-----------|
| CS-01 | (10.00, 2) | [5.00, 5.00] | Even split |
| CS-02 | (10.00, 3) | [3.34, 3.33, 3.33] | Penny rounding — first gets extra |
| CS-03 | (25.00, 1) | [25.00] | Single person |
| CS-04 | (0.00, 3) | [0.00, 0.00, 0.00] | Zero amount |
| CS-05 | (100.00, 7) | sum=100.00 | Large split, no penny loss |
| CS-06 | (0.01, 3) | [0.01, 0.00, 0.00] | Minimal amount |
| CS-07 | (10.00, 0) | ValueError | Division by zero guard |
| CS-08 | (999999.99, 3) | sum≈999999.99 | Large amount precision |

### 2.2 compute_balances (6 cases)

| ID | Scenario | Expected |
|----|----------|----------|
| CB-01 | 2 people, 1 expense | debtor→creditor with correct amount |
| CB-02 | Cross-expenses | Net simplification |
| CB-03 | All settled | Empty list |
| CB-04 | 3-way split | Two debtors, correct totals |
| CB-05 | Payer not in split | Full amount owed by split members |
| CB-06 | No expenses | Empty list |

### 2.3 validate_settle (6 cases)

| ID | Scenario | Expected |
|----|----------|----------|
| VS-01 | Valid partial settle | Remaining debt returned |
| VS-02 | Exact settle | Remaining = 0.00 |
| VS-03 | Over-settle | ValueError "Cannot settle" |
| VS-04 | No debt exists | ValueError |
| VS-05 | Self-settle | ValueError |
| VS-06 | Unknown person | ValueError |

### 2.4 Storage (6 cases)

| ID | Scenario | Expected |
|----|----------|----------|
| ST-01 | Missing file | Creates with defaults |
| ST-02 | Valid file | Loads correctly |
| ST-03 | Corrupt JSON | StorageError |
| ST-04 | Missing keys | StorageError "missing required keys" |
| ST-05 | Save + reload | Roundtrip integrity |
| ST-06 | Nested dirs | Creates parent directories |

### 2.5 Commands (24 cases)

Covered in test_commands.py: add_person (4), add_expense (8), balances (3), settle (5), summary (2), export_csv (3).

### 2.6 Formatters (10 cases)

Covered in test_formatters.py: format_balances (4), format_summary (2), format_csv (3), comma escaping (1).

### 2.7 CLI Integration (18 cases)

Covered in test_cli.py via subprocess execution.

## 3. Coverage Summary

| Category | Designed | Implemented | Gap |
|----------|----------|-------------|-----|
| compute_shares | 8 | 8 | 0 |
| compute_balances | 6 | 6 | 0 |
| validate_settle | 6 | 6 | 0 |
| validation helpers | 5 | 5 | 0 |
| Storage | 6 | 6 | 0 |
| Models | 5 | 5 | 0 |
| Commands | 24 | 24 | 0 |
| Formatters | 10 | 10 | 0 |
| CLI Integration | 18 | 18 | 0 |
| **Total** | **88** | **88** | **0** |

## 4. Not Covered (known gaps)

- Concurrent file access (no locking in storage.py)
- Unicode in person names and descriptions
- Very long descriptions (display formatting)
- File permission errors (OS-level)
- `__main__.py` entry point directly (covered via `-m expense_splitter`)

## 5. Mutation Test Candidates

High-value mutations for future verification:
1. `compute_shares`: change `<` to `<=` in remainder distribution → off-by-one
2. `compute_balances`: remove net simplification → show gross instead of net
3. `validate_settle`: change `>` to `>=` in over-settle check → exact settle rejected
4. `storage._validate_shape`: remove a required key → corrupt data accepted
5. `commands.add_person`: remove `.strip().lower()` → case sensitivity breaks
