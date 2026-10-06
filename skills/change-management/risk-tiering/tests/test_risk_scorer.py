"""Tests for the quantitative risk scorer."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import risk_scorer  # noqa: E402


class SigmoidTests(unittest.TestCase):
    def test_midpoint(self):
        self.assertAlmostEqual(risk_scorer.sigmoid(0), 0.5)

    def test_monotonic(self):
        prev = 0.0
        for x in range(-10, 11):
            val = risk_scorer.sigmoid(x)
            self.assertGreaterEqual(val, prev)
            prev = val

    def test_bounds(self):
        self.assertGreater(risk_scorer.sigmoid(-100), 0.0)
        self.assertLessEqual(risk_scorer.sigmoid(100), 1.0)
        self.assertGreater(risk_scorer.sigmoid(100), 0.99)

    def test_negative_overflow(self):
        self.assertAlmostEqual(risk_scorer.sigmoid(-700), 0.0, places=10)


class LogScaleTests(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(risk_scorer.log_scale(0), 0.0)

    def test_reference(self):
        self.assertAlmostEqual(risk_scorer.log_scale(10), 1.0)

    def test_capped(self):
        self.assertAlmostEqual(risk_scorer.log_scale(10000), 1.0)

    def test_negative(self):
        self.assertEqual(risk_scorer.log_scale(-5), 0.0)


class SensitiveMatchTests(unittest.TestCase):
    def test_auth_path(self):
        self.assertEqual(risk_scorer.count_sensitive_matches(["src/auth/login.py"]), 1)

    def test_migration(self):
        self.assertEqual(risk_scorer.count_sensitive_matches(["db/migrations/001.sql"]), 1)

    def test_payment(self):
        self.assertEqual(risk_scorer.count_sensitive_matches(["src/payment/charge.py"]), 1)

    def test_safe_path(self):
        self.assertEqual(risk_scorer.count_sensitive_matches(["src/main.py"]), 0)

    def test_multiple(self):
        paths = ["src/auth/login.py", "db/migrations/001.sql", "src/main.py"]
        self.assertEqual(risk_scorer.count_sensitive_matches(paths), 2)

    def test_windows_paths(self):
        self.assertEqual(risk_scorer.count_sensitive_matches(["src\\auth\\login.py"]), 1)


class TierTests(unittest.TestCase):
    def test_low_tier(self):
        result = risk_scorer.compute_risk_score({
            "lines_changed": 10, "files_changed": 2,
            "file_paths": ["src/main.py"],
        })
        self.assertEqual(result["tier"], "LOW")
        self.assertLess(result["score"], 0.25)

    def test_medium_tier(self):
        result = risk_scorer.compute_risk_score({
            "lines_changed": 200, "files_changed": 8,
            "churn_ratio": 0.3, "file_paths": ["src/app.py"],
        })
        self.assertEqual(result["tier"], "MEDIUM")
        self.assertGreaterEqual(result["score"], 0.25)
        self.assertLess(result["score"], 0.50)

    def test_high_tier(self):
        result = risk_scorer.compute_risk_score({
            "lines_changed": 500, "files_changed": 15,
            "file_paths": ["src/payment/charge.py"],
        })
        self.assertEqual(result["tier"], "HIGH")
        self.assertGreaterEqual(result["score"], 0.50)
        self.assertLess(result["score"], 0.75)

    def test_critical_tier(self):
        result = risk_scorer.compute_risk_score({
            "lines_changed": 2000, "files_changed": 50,
            "file_paths": ["src/auth/login.py", "db/migrations/001.sql", "src/billing/invoice.py"],
        })
        self.assertEqual(result["tier"], "CRITICAL")
        self.assertGreaterEqual(result["score"], 0.75)

    def test_empty_input(self):
        result = risk_scorer.compute_risk_score({})
        self.assertEqual(result["tier"], "LOW")
        self.assertEqual(result["sensitive_matches"], 0)

    def test_zero_lines_zero_files(self):
        result = risk_scorer.compute_risk_score({"lines_changed": 0, "files_changed": 0})
        self.assertEqual(result["tier"], "LOW")

    def test_model_version(self):
        result = risk_scorer.compute_risk_score({})
        self.assertEqual(result["model_version"], "1.0.0")

    def test_features_present(self):
        result = risk_scorer.compute_risk_score({"lines_changed": 100})
        for key in risk_scorer.WEIGHTS:
            self.assertIn(key, result["features"])

    def test_builtin_check(self):
        self.assertTrue(risk_scorer._check())


if __name__ == "__main__":
    unittest.main()
