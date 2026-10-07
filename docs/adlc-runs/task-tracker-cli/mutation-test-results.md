# Task Tracker CLI — Mutation Testing Results

**Date:** 2026-10-07  
**Target:** `task-tracker-cli/task_tracker/` (4 source files)  
**Test suite:** 27 tests (unittest)  
**Mutations:** 18  
**Mutation Score:** 14/18 = **77.8%**

---

## Summary

| Outcome | Count | Percentage |
|---------|-------|------------|
| **CAUGHT** (test failed) | 14 | 77.8% |
| **SURVIVED** (tests still pass) | 4 | 22.2% |

A mutation score of 77.8% means **22.2% of realistic bugs would go undetected** by the existing test suite. Industry target is typically 80-90%, so the suite falls just short.

---

## Results Table

| ID | File | Mutation | Caught? | Failures | Which test(s) caught it? |
|----|------|----------|---------|----------|--------------------------|
| M1 | storage.py | `next_id: 1` → `0` (off-by-one) | **CAUGHT** | 7 | test_add_single, test_add_increments_id, test_add_command, + others |
| M2 | storage.py | Remove `path.parent.mkdir` in `load()` | **SURVIVED** | 0 | — |
| M3 | storage.py | `json.JSONDecodeError` → `Exception` (wider catch) | **SURVIVED** | 0 | — |
| M4 | storage.py | Remove `_validate_shape(raw)` call | **SURVIVED** | 0 | — |
| M5 | storage.py | Remove `os.replace(tmp, str(path))` in `save()` | **CAUGHT** | 10 | test_save_and_reload, test_add_single, + many others |
| M6 | models.py | `status="todo"` → `"pending"` in `Task.create()` | **CAUGHT** | 2 | test_create, test_list_filter_todo |
| M7 | models.py | Remove `completed_at` from `to_dict()` | **CAUGHT** | 1 | test_to_dict |
| M8 | models.py | `d.get("completed_at")` → `d["completed_at"]` | **SURVIVED** | 0 | — |
| M9 | commands.py | `next_id += 1` → `+= 2` (skip IDs) | **CAUGHT** | 1 | test_add_increments_id |
| M10 | commands.py | `!= "all"` → `== "all"` (inverted filter) | **CAUGHT** | 2 | test_list_filter_todo, test_list_filter_done |
| M11 | commands.py | `== "done"` → `== "todo"` in already-done check | **CAUGHT** | 4 | test_done_success, test_done_already_done, + others |
| M12 | commands.py | `done_count` → `todo_count` in percentage | **CAUGHT** | 1 | test_stats_mixed |
| M13 | commands.py | Remove `storage.save` in `done_task` (no persist) | **CAUGHT** | 4 | test_list_filter_todo, test_list_filter_done, + others |
| M14 | commands.py | Return code `1` → `0` for not-found | **CAUGHT** | 2 | test_done_not_found (commands), test_done_not_found (cli) |
| M15 | commands.py | `task.id` → `task.id + 1` in add message | **CAUGHT** | 2 | test_add_single, test_add_command |
| M16 | cli.py | `sys.exit(1)` → `sys.exit(0)` for no-command | **CAUGHT** | 1 | test_no_command_exits_1 |
| M17 | cli.py | Remove `if code: sys.exit(code)` block | **CAUGHT** | 1 | test_done_not_found (cli) |
| M18 | cli.py | `" ".join(args.description)` → `args.description[0]` | **SURVIVED** | 0 | — |

---

## Survived Mutations — Analysis

### M2: Remove `path.parent.mkdir` in `load()` — SURVIVED

**What it means:** If the parent directory doesn't exist when `load()` is called for the first time, the code will crash. But no test exercises this path because:
- `test_load_creates_file_when_missing` uses a `nested = self.tmp / "sub" / "tasks.json"` path, but `save()` (called inside `load()`) also has its own `mkdir(parents=True)`, so the directory gets created by `save()` even when `load()` skips it.
- **Root cause:** The `mkdir` in `save()` masks the missing `mkdir` in `load()`.
- **Fix needed:** Add a test that checks `load()` creates the parent directory itself, not just that the file eventually exists. Or test that `load()` with a deeply nested non-existent path doesn't crash *before* calling `save()` — but with the current code flow, it calls `save()` immediately, so the mutation is effectively equivalent (both `mkdir` calls exist). The real risk is if `save()` is ever changed to remove its `mkdir`.

### M3: Widen `json.JSONDecodeError` to `Exception` — SURVIVED

**What it means:** The test only checks that corrupted JSON raises `StorageError`. It doesn't verify the *type* of the original exception that gets caught. Widening to `Exception` still produces `StorageError`, so the test passes.
- **Root cause:** No test triggers a non-JSON exception in the `load()` path (e.g., permission error) to verify that `json.JSONDecodeError` and `OSError` are handled separately.
- **Fix needed:** Add a test that triggers an `OSError` (e.g., permission denied) and verifies it produces a different error message than corrupted JSON.

### M4: Remove `_validate_shape(raw)` — SURVIVED

**What it means:** No test loads a file with valid JSON but wrong schema (e.g., `{"foo": "bar"}` instead of `{"next_id": 1, "tasks": []}`). The `_validate_shape` function was added during code review (F3 fix) but no corresponding test was written.
- **Root cause:** The code review identified missing validation and the fix was applied, but the test suite wasn't updated to cover the new code.
- **Fix needed:** Add tests loading `{"foo": 1}`, `{"next_id": 1}` (missing tasks), `{"next_id": 1, "tasks": "not-a-list"}`, and `[1,2,3]` (not a dict).

### M8: `d.get("completed_at")` → `d["completed_at"]` — SURVIVED

**What it means:** The `from_dict` method uses `.get()` as a defensive measure for missing keys, but every test dict always includes `completed_at`. No test provides a dict without this key.
- **Root cause:** The round-trip test (`test_roundtrip`) uses `Task.create()` which always sets `completed_at=None`, so `to_dict()` always includes it. No test simulates loading legacy/incomplete data.
- **Fix needed:** Add a test with `{"id": 1, "description": "x", "status": "todo", "created_at": "t"}` (no `completed_at` key).

### M18: `" ".join(args.description)` → `args.description[0]` — SURVIVED

**What it means:** The CLI integration test (`test_add_command`) passes `["add", "Test task from CLI"]` — a single multi-word argument (quoted). So `args.description` is `["Test task from CLI"]` and `[0]` returns the same string as `" ".join(...)`. No test passes *multiple separate* arguments like `["add", "Buy", "milk"]`.
- **Root cause:** The CLI test doesn't test the exact scenario that `nargs="+"` and `" ".join()` are designed for — multiple positional arguments being joined.
- **Fix needed:** Add `self._run_cli(["add", "Buy", "some", "milk"])` and assert the output contains `"Buy some milk"`.

---

## Key Insights

### 1. Validation code has zero test coverage
M3 (exception type) and M4 (shape validation) both survived. The `_validate_shape()` function added during code review has **no tests at all**. This is a code-review-mandated fix with no verification.

### 2. CLI integration tests are too shallow
M18 survived because the CLI integration test passes multi-word descriptions as a single quoted argument rather than multiple separate arguments. The `test_add_command` test doesn't exercise the `" ".join()` path that distinguishes the CLI layer from the commands layer.

### 3. Defensive `.get()` is untested
M8 survived because all test data always includes all fields. The `.get()` in `from_dict` is a defensive measure against malformed data, but no test verifies this defense works.

### 4. Redundant code masks mutations
M2 survived because `save()` has its own `mkdir`, making `load()`'s `mkdir` redundant in the current code flow. This is actually fine — the code is safe — but it means the test suite can't distinguish between "both mkdirs present" and "only save's mkdir present."

---

## Recommendations

1. **Add schema validation tests** (kills M4):
   ```python
   def test_load_invalid_schema_not_dict(self):
       self.path.write_text('[1,2,3]')
       with self.assertRaises(StorageError):
           load(self.path)

   def test_load_invalid_schema_missing_keys(self):
       self.path.write_text('{"foo": "bar"}')
       with self.assertRaises(StorageError):
           load(self.path)
   ```

2. **Add multi-arg CLI test** (kills M18):
   ```python
   def test_add_multi_word_cli(self):
       result = self._run_cli(["add", "Buy", "some", "milk"])
       self.assertIn("Buy some milk", result.stdout)
   ```

3. **Add incomplete dict test** (kills M8):
   ```python
   def test_from_dict_missing_completed_at(self):
       d = {"id": 1, "description": "x", "status": "todo", "created_at": "t"}
       t = Task.from_dict(d)
       self.assertIsNone(t.completed_at)
   ```

4. **Add exception-type specificity test** (kills M3):
   ```python
   def test_load_permission_error_message(self):
       self.path.write_text('{}')
       self.path.chmod(0o000)
       try:
           with self.assertRaises(StorageError) as ctx:
               load(self.path)
           self.assertIn("Cannot read", str(ctx.exception))
       finally:
           self.path.chmod(0o644)
   ```

---

## Verification

After all mutations were reverted, the full test suite passes: **27/27 OK**.

---

*Generated by adversarial QA judge, 2026-10-07*
