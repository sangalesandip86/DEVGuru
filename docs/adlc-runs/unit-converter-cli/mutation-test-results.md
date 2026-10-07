# Unit Converter CLI — Mutation Test Results

**Date:** 2026-10-07  
**Target:** `unit-converter-cli/unit_converter/` (converter.py + cli.py)  
**Baseline:** 29/29 tests pass  
**Mutations applied:** 15  
**Mutation score:** 11/15 caught = **73.3%**

---

## Summary Table

| ID | File | Mutation | Caught? | Failures | Which test(s) caught it? |
|----|------|----------|---------|----------|--------------------------|
| M1 | converter.py | `v * 0.621371` → `v * 0.6214` (km→miles precision) | **SURVIVED** | 0 | — |
| M2 | converter.py | `v * 9/5 + 32` → `v * 9/5 + 30` (C→F offset) | CAUGHT | 6 | test_c_to_f_freezing, test_c_to_f_boiling, test_c_to_f_crossover, test_celsius_word, test_negative_celsius, test_temperature (CLI) |
| M3 | converter.py | `(v-32)*5/9` → `(v-32)*9/5` (F→C formula) | CAUGHT | 1 | test_f_to_c |
| M4 | converter.py | Remove `"liter": "liters"` alias | CAUGHT | 1 | test_singular_alias |
| M5 | converter.py | Remove `.lower()` (case-sensitive) | CAUGHT | 8 | test_case_insensitive + 7 others using uppercase unit names |
| M6 | converter.py | Swap `(from_norm, to_norm)` → `(to_norm, from_norm)` | CAUGHT | 18 | Nearly all conversion tests |
| M7 | converter.py | `result:.2f` → `result:.0f` (no decimals) | CAUGHT | 20 | Nearly all output-checking tests |
| M8 | converter.py | Remove `if from_norm == to_norm:` block | CAUGHT | 1 | test_same_unit |
| M9 | converter.py | `f"Unknown unit: {unit}"` → `"Unknown unit"` | **SURVIVED** | 0 | — |
| M10 | converter.py | Remove `("kg", "lbs")` conversion pair | CAUGHT | 1 | test_kg_to_lbs |
| M11 | converter.py | `v * 2.20462` → `v / 2.20462` (inverse kg→lbs) | CAUGHT | 1 | test_kg_to_lbs |
| M12 | converter.py | Add `"meter": "km"` (wrong alias) | **SURVIVED** | 0 | — |
| M13 | cli.py | `type=float` → `type=int` (lose decimals) | **SURVIVED** | 0 | — |
| M14 | cli.py | Remove `sys.exit(1)` | CAUGHT | 2 | test_unknown_unit_exits_1, test_error_goes_to_stderr |
| M15 | cli.py | Remove `file=sys.stderr` | CAUGHT | 2 | test_error_goes_to_stderr, test_unknown_unit_exits_1 |

---

## Survived Mutations — Analysis

### M1: Precision change (0.621371 → 0.6214) — SURVIVED

**Why:** The test `test_km_to_miles` checks `assertEqual(convert(100, "km", "miles"), "100 km = 62.14 miles")`. Both the correct factor (0.621371 × 100 = 62.1371, formatted as 62.14) and the mutated factor (0.6214 × 100 = 62.14) produce the same 2-decimal output for the test input of 100.

**Fix needed:** Add a test with an input that distinguishes precision, e.g., `convert(1000, "km", "miles")` → `"1000 km = 621.37 miles"` (mutant would produce `621.40`).

**Severity:** MEDIUM — a conversion factor error could give slightly wrong results for large values without any test detecting it.

### M9: Generic error message — SURVIVED

**Why:** Tests (`test_unknown_from_unit`, `test_unknown_to_unit`) only check that a `ConversionError` is raised. They don't check the error message content, so removing the unit name from the error is undetected.

**Fix needed:** Add `assertIn("foobar", str(exc))` to the unknown-unit tests to verify the error includes the offending unit.

**Severity:** LOW — the error still occurs; it's just less helpful. But for a CLI tool, error message quality matters.

### M12: Wrong alias mapping ("meter" → "km") — SURVIVED

**Why:** No test uses `"meter"` as an input unit. The alias map silently accepts a wrong entry without any test noticing. A user typing `convert 100 meter miles` would get a km→miles conversion instead of an error.

**Fix needed:** Either test that `"meter"` is not accepted (negative test for wrong aliases), or test each alias maps to the correct canonical unit.

**Severity:** HIGH — a wrong alias silently produces wrong results. This is a correctness issue the test suite cannot detect.

### M13: type=float → type=int — SURVIVED

**Why:** Every CLI integration test uses integer inputs (`100`, `0`, `-40`). No test sends a decimal like `3.5` via the CLI. With `type=int`, argparse would reject `3.5` as invalid, or silently truncate it — either way, no test catches it.

**Fix needed:** Add a CLI test with decimal input: `self._run_cli(["3.5", "kg", "lbs"])` and verify the output shows the correct decimal conversion.

**Severity:** HIGH — this means the CLI could silently reject or truncate decimal inputs with no test catching the regression.

---

## Mutation Score Breakdown

| Category | Mutations | Caught | Survived | Score |
|----------|-----------|--------|----------|-------|
| Conversion formulas (M2, M3, M6, M11) | 4 | 4 | 0 | 100% |
| Conversion precision (M1) | 1 | 0 | 1 | 0% |
| Alias handling (M4, M5, M12) | 3 | 2 | 1 | 67% |
| Output formatting (M7, M9) | 2 | 1 | 1 | 50% |
| Feature removal (M8, M10) | 2 | 2 | 0 | 100% |
| CLI error handling (M14, M15) | 2 | 2 | 0 | 100% |
| CLI input parsing (M13) | 1 | 0 | 1 | 0% |
| **Total** | **15** | **11** | **4** | **73.3%** |

---

## Conclusions

1. **Core conversion formulas are well-tested** (100% mutation kill rate) — major formula errors are always caught.

2. **Precision and edge values are undertested** — M1 shows the test suite can't distinguish slightly wrong conversion factors. Tests use "round number" inputs (100, 0) that often mask precision errors.

3. **Alias correctness is partially tested** — M4 and M5 are caught, but M12 shows new wrong aliases can be added silently. There's no "alias exhaustiveness" or "alias correctness" test.

4. **Error message quality is untested** — M9 shows error content isn't verified. Tests only check that errors occur, not what they say.

5. **CLI decimal input handling is untested** — M13 is the most dangerous survivor. Changing `float` to `int` in the parser goes completely undetected, meaning users could lose decimal precision silently.

6. **Industry benchmark:** A mutation score of 73.3% is below the 80% threshold typically expected for quality test suites. The 4 surviving mutations represent real testing gaps.
