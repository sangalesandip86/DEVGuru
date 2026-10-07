# ADR-001: Quiz Engine CLI Architecture

**Change Set:** CS-01ecb4a1  
**Stage:** ARCHITECTURE  
**Role:** architect  
**Date:** 2026-10-07  
**Status:** ACCEPTED

---

## 1. Context

REQ-001 specifies a Python CLI quiz engine with 6 commands, JSON storage, scoring, shuffle, timed mode, and export. Single-user, stdlib-only.

## 2. Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.10+ | Per NFR-001 |
| CLI framework | `argparse` (stdlib) | Sufficient for 6 subcommands with flags |
| Storage format | JSON | Per REQ-004; human-readable |
| Storage location | `~/.quiz-engine/data.json` | Per requirement |
| Test framework | `unittest` (stdlib) | No external deps |
| Randomization | `random.shuffle` with seed tracking | For reproducible shuffle in tests |
| Time tracking | `time.monotonic()` | Wall-clock independent |

## 3. Data Model

### Question
```json
{"id": 0, "text": "What is 2+2?", "options": ["1","2","3","4"], "correct_answer": 3, "explanation": "Basic math"}
```

### Quiz
```json
{"id": 1, "title": "Math 101", "questions": [...], "created_at": "2026-10-07T10:00:00"}
```

### Attempt
```json
{"id": 1, "quiz_id": 1, "answers": [3,1,2,0], "score": 75.0, "completed_at": "2026-10-07T10:05:00", "time_taken_seconds": 120}
```

### Storage File
```json
{
  "next_quiz_id": 2,
  "next_attempt_id": 2,
  "quizzes": [...],
  "attempts": [...]
}
```

## 4. Module Layout

```
tetaprojects/quiz-engine-cli/
  pyproject.toml
  quiz_engine/
    __init__.py
    __main__.py        # Entry point
    cli.py             # argparse setup, command dispatch
    commands.py        # Command implementations (create, list, take, results, stats, export)
    models.py          # Question, Quiz, Attempt dataclasses
    storage.py         # JSON load/save with atomic writes
    scoring.py         # Score calculation, shuffle logic, timed mode
    validators.py      # Input validation (questions file, answer indices)
    formatters.py      # Output formatting (tables, CSV, JSON export)
  tests/
    __init__.py
    test_models.py     # Unit tests for dataclasses
    test_commands.py   # Unit tests for command logic
    test_storage.py    # Unit tests for persistence
    test_scoring.py    # Unit tests for scoring/shuffle/timed
    test_validators.py # Unit tests for validation
    test_formatters.py # Unit tests for output formatting
    test_cli.py        # Integration tests (subprocess)
    sample_quiz.json   # Test fixture
```

## 5. Key Design Decisions

### 5.1 Separation of concerns
- **cli.py**: argument parsing only — no business logic
- **commands.py**: orchestrates operations, delegates to scoring/storage/formatters
- **scoring.py**: pure functions for score calculation, shuffle index mapping
- **validators.py**: pure functions for input validation, returns error messages
- **formatters.py**: pure functions for output formatting (tables, CSV, JSON)
- **storage.py**: only module that touches filesystem

### 5.2 Error handling
- `validators.py` returns `list[str]` of error messages (empty = valid)
- `storage.py` raises `StorageError` for I/O issues
- `cli.py` catches all exceptions, prints to stderr, exits 1

### 5.3 Shuffle tracking
- When `--shuffle` is used, create a mapping of `shuffled_index -> original_index`
- Answers are recorded using original question indices for consistent scoring
- Mapping is not persisted (shuffle is per-attempt)

### 5.4 Timed mode
- Record `start_time = time.monotonic()` before first question
- After each answer, check elapsed time
- If time exceeded, remaining questions get `answer = -1` (wrong)
- `time_taken_seconds` is always recorded, even without `--timed`

### 5.5 Non-interactive mode
- `--answers 1,3,2,0` provides all answers at once
- Must match question count; error if too few or too many
- Enables automated testing without stdin mocking
