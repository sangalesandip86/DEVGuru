"""Tests for flaky-detector.py. Run: python -m unittest discover -s <this dir>"""
import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "flaky_detector", Path(__file__).with_name("flaky-detector.py"))
fd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fd)


def junit(*cases: tuple[str, str]) -> str:
    body = []
    for name, outcome in cases:
        inner = {"pass": "", "fail": "<failure message='x'/>",
                 "error": "<error message='x'/>", "skip": "<skipped/>"}[outcome]
        body.append(f'<testcase classname="suite.A" name="{name}">{inner}</testcase>')
    return f'<testsuites><testsuite name="s">{"".join(body)}</testsuite></testsuites>'


class FlakyDetectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, xml: str) -> Path:
        path = self.dir / name
        path.write_text(xml, encoding="utf-8")
        return path

    def run_main(self, *args: str) -> tuple[int, dict]:
        out = StringIO()
        with redirect_stdout(out):
            code = fd.main(list(args))
        return code, json.loads(out.getvalue()) if out.getvalue() else {}

    def test_mixed_outcomes_flagged(self):
        r1 = self.write("r1.xml", junit(("t_ok", "pass"), ("t_flaky", "pass"), ("t_broken", "fail")))
        r2 = self.write("r2.xml", junit(("t_ok", "pass"), ("t_flaky", "fail"), ("t_broken", "error")))
        r3 = self.write("r3.xml", junit(("t_ok", "pass"), ("t_flaky", "pass"), ("t_broken", "fail")))
        code, result = self.run_main(str(r1), str(r2), str(r3))
        self.assertEqual(code, 1)
        self.assertEqual([t["test"] for t in result["flaky"]], ["suite.A::t_flaky"])
        self.assertAlmostEqual(result["flaky"][0]["flake_rate"], 0.3333)
        self.assertEqual(result["consistently_failing"], [{"test": "suite.A::t_broken", "runs": 3}])
        self.assertEqual(result["classification"], "FACT")

    def test_stable_suite_exits_zero(self):
        r1 = self.write("r1.xml", junit(("a", "pass"), ("b", "skip")))
        r2 = self.write("r2.xml", junit(("a", "pass"), ("b", "pass")))
        code, result = self.run_main("--dir", str(self.dir))
        self.assertEqual(code, 0)
        self.assertEqual(result["flaky_count"], 0)

    def test_retry_within_single_run_is_flaky(self):
        r1 = self.write("r1.xml", junit(("a", "fail"), ("a", "pass")))
        r2 = self.write("r2.xml", junit(("a", "pass")))
        code, result = self.run_main(str(r1), str(r2))
        self.assertEqual(code, 1)
        self.assertEqual(result["flaky"][0]["retried_within_run"], 1)

    def test_threshold_filters(self):
        runs = [self.write(f"r{i}.xml", junit(("a", "fail" if i == 0 else "pass"))) for i in range(10)]
        code, result = self.run_main("--threshold", "0.2", *map(str, runs))
        self.assertEqual(code, 0)
        self.assertEqual(result["flaky_count"], 0)

    def test_needs_two_reports(self):
        r1 = self.write("r1.xml", junit(("a", "pass")))
        self.assertEqual(fd.main([str(r1)]), 2)

    def test_bad_xml(self):
        r1 = self.write("r1.xml", "<not-xml")
        r2 = self.write("r2.xml", junit(("a", "pass")))
        self.assertEqual(fd.main([str(r1), str(r2)]), 2)


if __name__ == "__main__":
    unittest.main()
