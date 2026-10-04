"""Tests for checkpoint_validate.py — checkpoint schema + gate-skip detection."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import checkpoint_validate as cv


def _write_json(tmp: Path, data: dict) -> Path:
    p = tmp / "checkpoint.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


VALID_CP = {
    "run_id": "R-001",
    "requested": {"start": "INTAKE", "end": "PLAN"},
    "completed_stages": ["INTAKE", "ARCHITECTURE"],
    "stopped_at": "PLAN",
    "stop_reason": "GATE_FAILED",
    "ledger_cursor": "ENTRY-42",
    "handoff": {"to": "architect"},
    "next_preflight": {},
    "created_at": "2026-10-03T12:00:00Z",
}


class StructureTest(unittest.TestCase):
    def test_valid_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_json(Path(tmp), VALID_CP)
            r = cv.validate(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["findings"], [])

    def test_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_json(Path(tmp), {"run_id": "R-1"})
            r = cv.validate(p)
            self.assertFalse(r["ok"])
            self.assertTrue(any("missing required fields" in f["message"] for f in r["findings"]))

    def test_invalid_stage(self):
        cp = {**VALID_CP, "completed_stages": ["INTAKE", "BOGUS"]}
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_json(Path(tmp), cp)
            r = cv.validate(p)
            self.assertFalse(r["ok"])
            self.assertTrue(any("BOGUS" in f["message"] for f in r["findings"]))

    def test_invalid_stop_reason(self):
        cp = {**VALID_CP, "stop_reason": "BORED"}
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_json(Path(tmp), cp)
            r = cv.validate(p)
            self.assertFalse(r["ok"])
            self.assertTrue(any("BORED" in f["message"] for f in r["findings"]))

    def test_bad_cursor(self):
        cp = {**VALID_CP, "ledger_cursor": "cursor-42"}
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_json(Path(tmp), cp)
            r = cv.validate(p)
            self.assertFalse(r["ok"])
            self.assertTrue(any("ENTRY-" in f["message"] for f in r["findings"]))

    def test_empty_cursor_is_ok(self):
        cp = {**VALID_CP, "ledger_cursor": ""}
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_json(Path(tmp), cp)
            r = cv.validate(p)
            self.assertTrue(r["ok"])

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "checkpoint.json"
            p.write_text("not json", encoding="utf-8")
            r = cv.validate(p)
            self.assertFalse(r["ok"])
            self.assertEqual(r["findings"][0]["severity"], "ERROR")


class GateSkipTest(unittest.TestCase):
    def test_missing_gate_result_detected(self):
        evidence = {
            "gate_results": [],
            "reviews": [],
            "approvals": [],
        }
        stages_data = {
            "stages": {
                "INTAKE": {
                    "exit_gate": [
                        {"kind": "script", "ref": "plan_lint.py"},
                    ],
                },
            },
        }
        problems = cv.validate_gates(
            {"completed_stages": ["INTAKE"]}, evidence, stages_data
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("plan_lint", problems[0])

    def test_gate_present_no_problem(self):
        evidence = {
            "gate_results": [{"source": "plan_lint"}],
            "reviews": [],
            "approvals": [],
        }
        stages_data = {
            "stages": {
                "INTAKE": {
                    "exit_gate": [
                        {"kind": "script", "ref": "plan_lint.py"},
                    ],
                },
            },
        }
        problems = cv.validate_gates(
            {"completed_stages": ["INTAKE"]}, evidence, stages_data
        )
        self.assertEqual(problems, [])

    def test_judgment_missing(self):
        evidence = {"gate_results": [], "reviews": [], "approvals": []}
        stages_data = {
            "stages": {
                "REVIEW": {
                    "exit_gate": [
                        {"kind": "judgment", "ref": "code-review", "role": "reviewer"},
                    ],
                },
            },
        }
        problems = cv.validate_gates(
            {"completed_stages": ["REVIEW"]}, evidence, stages_data
        )
        self.assertIn("REVIEW", problems[0])
        self.assertIn("reviewer", problems[0])

    def test_approval_missing(self):
        evidence = {"gate_results": [], "reviews": [], "approvals": []}
        stages_data = {
            "stages": {
                "RELEASE": {
                    "exit_gate": [
                        {"kind": "approval", "ref": "release-sign-off", "when": "always"},
                    ],
                },
            },
        }
        problems = cv.validate_gates(
            {"completed_stages": ["RELEASE"]}, evidence, stages_data
        )
        self.assertIn("approval", problems[0])

    def test_approval_conditional_skipped(self):
        evidence = {"gate_results": [], "reviews": [], "approvals": []}
        stages_data = {
            "stages": {
                "RELEASE": {
                    "exit_gate": [
                        {"kind": "approval", "ref": "release-sign-off", "when": "risk>=HIGH"},
                    ],
                },
            },
        }
        problems = cv.validate_gates(
            {"completed_stages": ["RELEASE"]}, evidence, stages_data
        )
        self.assertEqual(problems, [])


class CLITest(unittest.TestCase):
    def test_check_mode_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_json(Path(tmp), VALID_CP)
            code = cv.main(["--checkpoint", str(p), "--check"])
            self.assertEqual(code, 0)

    def test_check_mode_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write_json(Path(tmp), {"run_id": "R-bad"})
            code = cv.main(["--checkpoint", str(p), "--check"])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
