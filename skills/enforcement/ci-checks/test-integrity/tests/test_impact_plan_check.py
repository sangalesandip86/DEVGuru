"""Tests for impact_plan_check.py — impact-plan vs diff comparison (finding E3)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import impact_plan_check as ipc


class IsTestFileTest(unittest.TestCase):
    def test_python_test(self):
        self.assertTrue(ipc.is_test_file("tests/test_foo.py"))

    def test_js_spec(self):
        self.assertTrue(ipc.is_test_file("src/app.spec.ts"))

    def test_feature(self):
        self.assertTrue(ipc.is_test_file("features/login.feature"))

    def test_normal_file(self):
        self.assertFalse(ipc.is_test_file("src/app.py"))

    def test_dart_test(self):
        self.assertTrue(ipc.is_test_file("test/widget_test.dart"))


class CompareTest(unittest.TestCase):
    def test_all_matched(self):
        planned = [{"path": "tests/test_foo.py", "action": "create"}]
        actual = {"tests/test_foo.py": "create"}
        result = ipc.compare(planned, actual)
        self.assertEqual(len(result["matched"]), 1)
        self.assertEqual(len(result["undeclared"]), 0)
        self.assertEqual(len(result["missing"]), 0)

    def test_undeclared(self):
        planned = [{"path": "tests/test_foo.py", "action": "create"}]
        actual = {"tests/test_foo.py": "create", "tests/test_bar.py": "create"}
        result = ipc.compare(planned, actual)
        self.assertEqual(len(result["undeclared"]), 1)
        self.assertEqual(result["undeclared"][0]["path"], "tests/test_bar.py")

    def test_missing(self):
        planned = [
            {"path": "tests/test_foo.py", "action": "create"},
            {"path": "tests/test_bar.py", "action": "create"},
        ]
        actual = {"tests/test_foo.py": "create"}
        result = ipc.compare(planned, actual)
        self.assertEqual(len(result["missing"]), 1)
        self.assertEqual(result["missing"][0]["path"], "tests/test_bar.py")

    def test_action_mismatch(self):
        planned = [{"path": "tests/test_foo.py", "action": "create"}]
        actual = {"tests/test_foo.py": "modify"}
        result = ipc.compare(planned, actual)
        self.assertEqual(len(result["action_mismatch"]), 1)

    def test_delete_not_missing(self):
        planned = [{"path": "tests/test_old.py", "action": "delete"}]
        actual = {}
        result = ipc.compare(planned, actual)
        self.assertEqual(len(result["missing"]), 0)


class CLITest(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.json"
            plan.write_text(json.dumps({
                "files": [{"path": "tests/test_a.py", "action": "create"}],
            }), encoding="utf-8")
            code = ipc.main(["--plan", str(plan),
                             "--actual-files", "tests/test_a.py"])
            self.assertEqual(code, 0)

    def test_fail_undeclared(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.json"
            plan.write_text(json.dumps({"files": []}), encoding="utf-8")
            code = ipc.main(["--plan", str(plan),
                             "--actual-files", "tests/test_a.py"])
            self.assertEqual(code, 1)

    def test_missing_plan(self):
        code = ipc.main(["--plan", "/nonexistent/plan.json",
                         "--actual-files", "tests/test_a.py"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
