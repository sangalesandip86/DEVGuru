# Expense Splitter CLI — Code & Security Review

> Stage: REVIEW | Roles: @code-reviewer + @security-reviewer
> Run: expense-splitter-run-001 | Change Set: CS-b13e340f

---

## Code Review

### Architecture Conformance

| ADR Decision | Implementation | Status |
|-------------|---------------|--------|
| 7-module layout | cli, commands, ledger, storage, models, formatters + `__main__` | PASS |
| Cents-based penny rounding | `compute_shares` uses `round(amount * 100)`, integer math | PASS |
| Balance simplification | `compute_balances` nets (A,B)−(B,A) pairs | PASS |
| Case-insensitive names | `strip().lower()` in `add_person`, `add_expense`, `settle` | PASS |
| Atomic save | `tempfile.mkstemp` + `os.replace` | PASS |
| Env var override | `EXPENSE_SPLITTER_FILE` in `storage._default_path()` | PASS |

### Code Quality Findings

| ID | File:Line | Severity | Finding |
|----|-----------|----------|---------|
| CR-01 | ledger.py:7 | LOW | `round(amount * 100)` can produce floating-point rounding surprises for amounts like $1.005. Using `int(amount * 100 + 0.5)` or `decimal.Decimal` would be more precise. Acceptable for CLI tool with 2-decimal user input. |
| CR-02 | ledger.py:80 | LOW | `amount > owed + 0.001` epsilon comparison is pragmatic but ad-hoc. Could drift on very small amounts. Acceptable for the stated requirement. |
| CR-03 | commands.py:34 | INFO | `if split_with is None or len(split_with) == 0` — the `len` check handles empty list from external callers but CLI never passes an empty list (argparse gives `None` or a string). Defensive, acceptable. |
| CR-04 | models.py:16 | INFO | `create()` class methods duplicate `__init__` — standard pattern for dataclasses that need computed defaults (`created_at`). Fine. |
| CR-05 | formatters.py:42 | FIXED | `csv.writer` defaulted to `\r\n` line terminator in `StringIO`. Fixed during test pass to `lineterminator="\n"`. |

### Test Coverage Assessment

- **88 tests** across 6 test files
- **Unit tests**: models (5), storage (6), ledger (22), formatters (10), commands (24)
- **Integration tests**: CLI via subprocess (18), covering error routing to stderr
- **Edge cases covered**: penny rounding, zero amount, negative amount, self-settle, unknown persons, corrupt storage, case insensitivity
- **Missing edge cases**: Unicode names, concurrent access, extremely long descriptions

### Verdict: **ACCEPT** with LOW-severity notes

---

## Security Review

### Threat Model

| Threat | Mitigation | Status |
|--------|-----------|--------|
| Path traversal via EXPENSE_SPLITTER_FILE | `Path()` resolution; no user-controlled path segments beyond env var | ACCEPTABLE |
| JSON injection | `json.dumps` with no `allow_nan` override; `json.loads` validates structure | PASS |
| Temp file race condition | `tempfile.mkstemp` + `os.replace` is atomic on both POSIX and Windows | PASS |
| Command injection | No shell=True anywhere; subprocess tests use list args | PASS |
| Denial of service (huge file) | No file size check on load; acceptable for local CLI | ACCEPTABLE |
| Information disclosure | Errors to stderr; no tracebacks leak to user | PASS |

### Security Findings

| ID | File:Line | Severity | Finding |
|----|-----------|----------|---------|
| SR-01 | storage.py:64 | LOW | Temp file created with default permissions (umask). On multi-user systems, another user could potentially read the temp file before `os.replace`. Acceptable for single-user CLI. |
| SR-02 | storage.py:52 | INFO | `read_text` reads entire file into memory. No size guard. For a personal CLI, this is fine; a library would want a limit. |
| SR-03 | cli.py:66-68 | PASS | Error handler catches specific exceptions only. No broad `except Exception`. Stack traces don't leak to end users. |

### OWASP CLI Checklist

- [x] No eval/exec on user input
- [x] No shell=True subprocess calls
- [x] No hardcoded secrets
- [x] No network calls
- [x] No unsafe deserialization (json only, validated)
- [x] Atomic file writes (no partial corruption)
- [x] Errors to stderr, not stdout

### Verdict: **ACCEPT** — no HIGH/CRITICAL findings

---

## Combined Review Summary

| Dimension | Score | Max |
|-----------|-------|-----|
| Architecture conformance | 6 | 6 |
| Code correctness | 4 | 5 |
| Error handling | 5 | 5 |
| Test coverage | 4 | 5 |
| Security posture | 4 | 5 |
| **Total** | **23** | **26** |

**Overall: ACCEPT** — production-ready for a personal CLI tool.
