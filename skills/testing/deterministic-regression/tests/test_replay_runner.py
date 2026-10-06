"""Tests for the deterministic regression replay runner."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import replay_runner  # noqa: E402


GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden-cases"


class ReplayRunnerTests(unittest.TestCase):
    def test_builtin_check(self):
        case = {
            "case_id": "self-test",
            "fixture": {"lines_changed": 10, "files_changed": 2, "file_paths": ["src/main.py"]},
            "steps": [{"action": "risk_routing", "expected": {"tier": "LOW"}}],
        }
        ok, results = replay_runner.run_case(case)
        self.assertTrue(ok)
        self.assertEqual(results[0]["action"], "risk_routing")

    def test_unknown_check(self):
        case = {
            "case_id": "unknown",
            "fixture": {},
            "steps": [{"action": "nonexistent_check", "expected": {}}],
        }
        ok, results = replay_runner.run_case(case)
        self.assertFalse(ok)
        self.assertIn("unknown check", results[0]["detail"])

    def test_fixture_override(self):
        case = {
            "case_id": "override-test",
            "fixture": {"path": "src/main.py"},
            "steps": [
                {"action": "dangerous_path_blocking", "expected": {"blocked": False}},
                {"action": "dangerous_path_blocking", "expected": {"blocked": True},
                 "fixture_override": {"path": ".env"}},
            ],
        }
        ok, results = replay_runner.run_case(case)
        self.assertTrue(ok)

    def test_golden_cases_pass(self):
        if not GOLDEN_DIR.is_dir():
            self.skipTest("golden-cases directory not found")
        passed, failed, reports = replay_runner.run_suite(GOLDEN_DIR)
        for r in reports:
            if not r["ok"]:
                for s in r["steps"]:
                    if not s["ok"]:
                        self.fail(f"{r['case_id']}/{s['action']}: {s['detail']}")
        self.assertEqual(failed, 0, f"{failed} golden cases failed")

    def test_max_fixture_size_enforced(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"case_id": "huge", "fixture": {"data": "x" * 300000}, "steps": []}, f)
            f.flush()
            with self.assertRaises(ValueError):
                replay_runner.load_case(Path(f.name))
        Path(f.name).unlink()

    def test_max_steps_enforced(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "case_id": "many-steps",
                "fixture": {},
                "steps": [{"action": "risk_routing", "expected": {}} for _ in range(100)],
            }, f)
            f.flush()
            with self.assertRaises(ValueError):
                replay_runner.load_case(Path(f.name))
        Path(f.name).unlink()

    def test_empty_case(self):
        case = {"case_id": "empty", "fixture": {}, "steps": []}
        ok, results = replay_runner.run_case(case)
        self.assertTrue(ok)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
