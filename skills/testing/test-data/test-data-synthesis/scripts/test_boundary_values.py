"""Tests for boundary_values.py (stdlib unittest)."""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boundary_values as bv  # noqa: E402

SPEC = {
    "entity": "Transfer",
    "fields": {
        "amount": {"type": "number", "min": 0.01, "max": 10000, "precision": 2, "required": True, "nullable": False},
        "currency": {"type": "enum", "enum": ["EUR", "USD"], "required": True, "nullable": False},
        "memo": {"type": "string", "min_length": 0, "max_length": 5, "nullable": True},
        "count": {"type": "integer", "min": 1, "max": 10, "nullable": False},
        "iban": {"type": "string", "pattern": "^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$", "nullable": False},
        "date": {"type": "date", "min": "2024-01-01", "max": "2024-12-31", "nullable": False},
        "tags": {"type": "array", "min_items": 1, "max_items": 2, "items": {"type": "string", "max_length": 3}},
    },
}


def values(result, field, expect):
    return [c["value"] for c in result["fields"][field] if c["expect"] == expect]


class BoundaryValueTests(unittest.TestCase):
    def setUp(self):
        self.r = bv.generate(json.loads(json.dumps(SPEC)), seed=7)

    def test_integer_bva(self):
        self.assertEqual(sorted(v for v in values(self.r, "count", "valid") if isinstance(v, int)), [1, 2, 5, 9, 10])
        self.assertIn(0, values(self.r, "count", "invalid"))
        self.assertIn(11, values(self.r, "count", "invalid"))

    def test_number_respects_precision(self):
        inv = values(self.r, "amount", "invalid")
        self.assertIn(0.0, inv)          # min - 0.01
        self.assertIn(10000.01, inv)     # max + 0.01
        self.assertIn("0.011", inv)      # too many decimals
        self.assertIn(0.01, values(self.r, "amount", "valid"))

    def test_string_lengths_and_multibyte(self):
        valid = values(self.r, "memo", "valid")
        self.assertIn("", valid)
        self.assertIn("ééééé", valid)
        self.assertTrue(any(isinstance(v, str) and len(v) == 6 for v in values(self.r, "memo", "invalid")))

    def test_required_and_nullable(self):
        self.assertIn(bv.SENTINEL_MISSING, values(self.r, "amount", "invalid"))
        self.assertIn(None, values(self.r, "amount", "invalid"))
        self.assertIn(None, values(self.r, "memo", "valid"))
        self.assertIn(bv.SENTINEL_MISSING, values(self.r, "memo", "valid"))

    def test_pattern_without_examples_raises_question_not_invented_value(self):
        self.assertEqual([v for v in values(self.r, "iban", "valid") if v != bv.SENTINEL_MISSING], [])
        self.assertTrue(any(q["field"] == "iban" and "examples_valid" in q["question"] for q in self.r["questions"]))

    def test_unspecified_is_never_labelled(self):
        unspecified = [c for c in self.r["fields"]["memo"] if c["why"] == "whitespace only"]
        self.assertEqual(unspecified[0]["expect"], "unspecified")
        self.assertTrue(any(q["field"] == "memo" for q in self.r["questions"]))

    def test_date_and_leap_day(self):
        self.assertIn("2023-12-31", values(self.r, "date", "invalid"))
        self.assertIn("2024-02-29", values(self.r, "date", "valid"))
        self.assertIn("2024-02-30", values(self.r, "date", "invalid"))

    def test_array_bounds(self):
        self.assertIn([], values(self.r, "tags", "invalid"))
        self.assertTrue(any(isinstance(v, list) and len(v) == 3 for v in values(self.r, "tags", "invalid")))

    def test_datasets_one_factor_at_a_time(self):
        happy = self.r["datasets"]["happy"][0]["payload"]
        self.assertEqual(happy["count"], 5)
        for rec in self.r["datasets"]["negative"]:
            diff = {k for k in set(happy) | set(rec["payload"]) if happy.get(k, "∅") != rec["payload"].get(k, "∅")}
            self.assertLessEqual(diff, {rec["varies"]}, rec)
        self.assertTrue(all(r["expect"] == "invalid" for r in self.r["datasets"]["negative"]))

    def test_deterministic_with_seed(self):
        a = bv.generate(json.loads(json.dumps(SPEC)), seed=3)
        b = bv.generate(json.loads(json.dumps(SPEC)), seed=3)
        self.assertEqual(json.dumps(a, sort_keys=True, default=str), json.dumps(b, sort_keys=True, default=str))
        c = bv.generate(json.loads(json.dumps(SPEC)), seed=4)
        self.assertNotEqual(json.dumps(a, sort_keys=True, default=str), json.dumps(c, sort_keys=True, default=str))

    def test_cli_and_bad_input(self):
        self.assertEqual(bv.main(["/no/such/spec.json"]), 2)
        with self.assertRaises(ValueError):
            bv.generate({"fields": {"x": {"type": "blob"}}})
        p = Path(__file__).with_name("_tmp_spec.json")
        p.write_text(json.dumps(SPEC), encoding="utf-8")
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(bv.main([str(p), "--seed", "1"]), 0)
            self.assertEqual(json.loads(buf.getvalue())["seed"], 1)
        finally:
            p.unlink()


if __name__ == "__main__":
    unittest.main()
