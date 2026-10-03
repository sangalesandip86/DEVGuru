"""Tests for test_integrity_guard.py (stdlib unittest)."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_integrity_guard as g  # noqa: E402


def tree(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def run(base: dict, head: dict, *extra: str) -> tuple[int, dict]:
    b, h = tree(base), tree(head)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = g.main(["--base", str(b), "--head", str(h), *extra])
    return rc, json.loads(buf.getvalue())


def types(report: dict, status: str | None = None) -> list[str]:
    return [f["type"] for f in report["findings"] if status is None or f["status"] == status]


CART_BASE = """import { total } from '../src/cart'

// ST-12/AC-3
test('total applies discount', () => {
  expect(total([100], 0.1)).toBe(90)
  expect(total([], 0.1)).toBe(0)
})

test('rejects negative', () => {
  expect(() => total([-1], 0)).toThrow()
})
"""


class IntegrityGuardTests(unittest.TestCase):
    def test_clean_addition_passes(self):
        head = CART_BASE + """
// ST-12/AC-4
test('total of two items', () => {
  expect(total([1, 2], 0)).toBe(3)
})
"""
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head})
        self.assertEqual(rc, 0, rep)
        self.assertEqual(rep["verdict"], "PASS")

    def test_expectation_change_blocked_without_ac_change(self):
        head = CART_BASE.replace("toBe(90)", "toBe(95)")
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head})
        self.assertEqual(rc, 1)
        f = [f for f in rep["findings"] if f["type"] == "EXPECTATION_CHANGED"][0]
        self.assertEqual(f["status"], "open")
        self.assertEqual(f["ac_tags"], ["ST-12/AC-3"])

    def test_expectation_change_allowed_when_ac_changed(self):
        head = CART_BASE.replace("toBe(90)", "toBe(95)")
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head},
                      "--ac-changed", "ST-12/AC-3")
        self.assertEqual(rc, 0, rep)
        self.assertEqual(types(rep, "ac-covered"), ["EXPECTATION_CHANGED"])

    def test_untagged_test_cannot_be_ac_covered(self):
        head = CART_BASE.replace("toThrow()", "not.toThrow()")
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head},
                      "--ac-changed", "ST-12/AC-3")
        self.assertEqual(rc, 1)
        f = [f for f in rep["findings"] if f["status"] == "open"][0]
        self.assertIn("no ST-n/AC-n tag", f["detail"])

    def test_assertion_removed(self):
        head = CART_BASE.replace("  expect(total([], 0.1)).toBe(0)\n", "")
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head})
        self.assertEqual(rc, 1)
        self.assertIn("ASSERTION_REMOVED", types(rep))

    def test_test_removed_and_file_deleted(self):
        head = CART_BASE.split("test('rejects negative'")[0]
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head})
        self.assertIn("TEST_REMOVED", types(rep))
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {})
        self.assertEqual(types(rep), ["TEST_FILE_DELETED"])
        self.assertEqual(rc, 1)

    def test_skip_focus_and_xfail(self):
        head = CART_BASE.replace("test('rejects negative'", "test.skip('rejects negative'")
        _, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head})
        self.assertIn("SKIP_ADDED", types(rep))
        head = CART_BASE.replace("test('rejects negative'", "test.only('rejects negative'")
        _, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head})
        self.assertIn("FOCUS_ADDED", types(rep))
        py_base = "def test_total():\n    assert total([1]) == 1\n"
        py_head = "import pytest\n@pytest.mark.xfail\ndef test_total():\n    assert total([1]) == 1\n"
        _, rep = run({"tests/test_cart.py": py_base}, {"tests/test_cart.py": py_head})
        self.assertIn("SKIP_ADDED", types(rep))

    def test_timeout_loosened(self):
        base = "test('loads', async ({ page }) => {\n  await expect(page.getByRole('row')).toHaveCount(3, { timeout: 5000 })\n})\n"
        head = base.replace("5000", "60000")
        _, rep = run({"e2e/list.spec.ts": base}, {"e2e/list.spec.ts": head})
        self.assertEqual(types(rep), ["TIMEOUT_OR_TOLERANCE_LOOSENED"])
        _, rep = run({"e2e/list.spec.ts": head}, {"e2e/list.spec.ts": base})  # tightening is fine
        self.assertNotIn("TIMEOUT_OR_TOLERANCE_LOOSENED", types(rep))

    def test_new_test_without_assertions(self):
        head = CART_BASE + "\ntest('smoke', () => {\n  total([1], 0)\n})\n"
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head})
        self.assertEqual(rc, 1)
        self.assertIn("NO_ASSERTIONS", types(rep))

    def test_swallowed_assertion(self):
        base = "def test_total():\n    assert total([1]) == 1\n"
        head = "def test_total():\n    try:\n        assert total([1]) == 1\n    except AssertionError:\n        pass\n"
        _, rep = run({"tests/test_cart.py": base}, {"tests/test_cart.py": head})
        self.assertIn("SWALLOWED_ASSERTION", types(rep))

    def test_sut_mocked_warns(self):
        head = "vi.mock('../src/cart')\n" + CART_BASE
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head})
        self.assertIn("SUT_MOCKED", types(rep))
        self.assertEqual(rc, 0)  # heuristic -> warn only

    def test_snapshot_mass_update(self):
        base = {f"src/__snapshots__/c{i}.test.tsx.snap": "a" for i in range(7)}
        head = {k: "b" for k in base}
        rc, rep = run(base, head, "--snapshot-threshold", "5")
        self.assertEqual(rc, 1)
        self.assertEqual(types(rep), ["SNAPSHOT_MASS_UPDATE"])

    def test_feature_example_rows_removed(self):
        base = ("@ST-7/AC-1\nScenario Outline: limits\n  When I transfer <amount>\n  Then I see <result>\n"
                "  Examples:\n    | amount | result |\n    | 0      | error  |\n    | 1      | ok     |\n")
        head = base.replace("    | 0      | error  |\n", "")
        rc, rep = run({"features/transfer.feature": base}, {"features/transfer.feature": head})
        self.assertIn("EXAMPLE_ROWS_REMOVED", types(rep))
        self.assertEqual(rc, 1)

    def test_overrides_accept_reviewed_finding(self):
        head = CART_BASE.replace("toBe(90)", "toBe(95)")
        _, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head})
        fid = [f["id"] for f in rep["findings"] if f["type"] == "EXPECTATION_CHANGED"][0]
        ov = Path(tempfile.mkdtemp()) / "ov.json"
        ov.write_text(json.dumps([{"finding_id": fid, "ledger_entry": "ENTRY-77"}]), encoding="utf-8")
        rc, rep = run({"tests/cart.test.ts": CART_BASE}, {"tests/cart.test.ts": head}, "--overrides", str(ov))
        self.assertEqual(rc, 0)
        self.assertEqual(rep["findings"][0]["accepted_by"], "ENTRY-77")

    def test_unified_diff_input(self):
        diff = """diff --git a/tests/cart.test.ts b/tests/cart.test.ts
--- a/tests/cart.test.ts
+++ b/tests/cart.test.ts
@@ -3,5 +3,5 @@
 // ST-12/AC-3
 test('total applies discount', () => {
-  expect(total([100], 0.1)).toBe(90)
+  expect(total([100], 0.1)).toBe(95)
   expect(total([], 0.1)).toBe(0)
"""
        p = Path(tempfile.mkdtemp()) / "d.diff"
        p.write_text(diff, encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = g.main(["--diff", str(p), "--ac-changed", "ST-12/AC-3"])
        rep = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(types(rep, "ac-covered"), ["EXPECTATION_CHANGED"])

    def test_bad_input(self):
        self.assertEqual(g.main([]), 2)
        self.assertEqual(g.main(["--diff", "x", "--ac-changed", "AC-1"]), 2)


if __name__ == "__main__":
    unittest.main()
