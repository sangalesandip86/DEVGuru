import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import path_tier_lookup as ptl  # noqa: E402

CONFIG = json.loads(ptl.DEFAULT_CONFIG.read_text(encoding="utf-8"))
CONTROL, _ = ptl.load_control_files(ptl.DEFAULT_CONTROL_FILES)


def tier(*paths, lines=None):
    return ptl.lookup(list(paths), CONFIG, CONTROL, lines)


class PathTierLookupTest(unittest.TestCase):
    def test_no_paths_is_uncomputable_high(self):
        r = tier()
        self.assertEqual(r["tier"], "HIGH")
        self.assertFalse(r["computed"])

    def test_docs_only_is_low(self):
        self.assertEqual(tier("README.md", "docs/guide/intro.md")["tier"], "LOW")

    def test_unmatched_code_is_default_medium(self):
        self.assertEqual(tier("src/utils/strings.py")["tier"], "MEDIUM")

    def test_docs_plus_code_takes_max(self):
        self.assertEqual(tier("README.md", "src/app.py")["tier"], "MEDIUM")

    def test_payment_path_is_high_with_reason_code(self):
        r = tier("services/payment/refund.py")
        self.assertEqual(r["tier"], "HIGH")
        self.assertIn("SENSITIVE_PATH", r["reason_codes"])

    def test_migration_is_high(self):
        self.assertEqual(tier("app/db/migrations/0042_add_fee.py")["tier"], "HIGH")
        self.assertEqual(tier("schema/V3__fees.sql")["tier"], "HIGH")

    def test_control_files_are_critical(self):
        for p in [".github/workflows/ci.yml", "AGENTS.md", "pkg/CLAUDE.md", ".claude/settings.json",
                  "CODEOWNERS", ".mcp.json"]:
            with self.subTest(p=p):
                self.assertEqual(tier(p)["tier"], "CRITICAL")

    def test_control_file_md_is_not_docs_low(self):
        # AGENTS.md is markdown but is a control file, so docs_only must not win.
        self.assertEqual(tier("services/api/AGENTS.md")["tier"], "CRITICAL")

    def test_windows_and_dot_paths_normalized(self):
        self.assertEqual(tier(".\\services\\auth\\login.ts")["tier"], "HIGH")

    def test_diff_size_cap_requires_decompose(self):
        r = tier("src/a.py", lines=401)
        self.assertTrue(r["decompose_required"])
        self.assertEqual(r["tier"], "MEDIUM")
        self.assertFalse(tier("src/a.py", lines=10)["decompose_required"])

    def test_file_count_cap(self):
        r = tier(*[f"src/f{i}.py" for i in range(26)])
        self.assertTrue(r["decompose_required"])

    def test_missing_control_file_list_uses_fallback(self):
        patterns, source = ptl.load_control_files(Path("does/not/exist.json"))
        self.assertEqual(source, "embedded-fallback")
        self.assertEqual(ptl.lookup([".github/workflows/x.yml"], CONFIG, patterns)["tier"], "CRITICAL")

    def test_bad_config_falls_back_to_high(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            self.assertEqual(ptl.main(["--config", str(bad), "src/a.py"]), 3)

    def test_compute_path_tier_public_api(self):
        r = ptl.compute_path_tier(["services/payment/x.py"])
        self.assertEqual(r["tier"], "HIGH")
        self.assertTrue(r["computed"])
        self.assertEqual(ptl.compute_path_tier(["a.py"], config_path=Path("missing.json"))["tier"], "HIGH")

    def test_effective_tier_type_floor_never_lowers(self):
        self.assertEqual(ptl.effective_tier("HIGH", "LOW"), "HIGH")       # API_CONTRACT floor raises
        self.assertEqual(ptl.effective_tier("LOW", "CRITICAL"), "CRITICAL")  # DOCUMENTATION floor can't lower
        self.assertEqual(ptl.effective_tier(None, "MEDIUM", "HIGH"), "HIGH")
        self.assertEqual(ptl.effective_tier(None, None), "HIGH")
        with self.assertRaises(ValueError):
            ptl.effective_tier("BOGUS")

    def test_cli_type_floor(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ptl.main(["README.md", "--type-floor", "HIGH"])
        out = json.loads(buf.getvalue())
        self.assertEqual((out["tier"], out["effective_tier"]), ("LOW", "HIGH"))

    def test_glob_double_star_root(self):
        self.assertTrue(ptl.glob_to_regex("**/payment/**").match("payment/x.py"))
        self.assertFalse(ptl.glob_to_regex("*.md").match("docs/a.md"))


if __name__ == "__main__":
    unittest.main()
