"""Tests for bootstrap_project.py — cold-start scaffolding."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import bootstrap_project as bp


class TestBootstrapProject(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        (self.root / ".git").mkdir()  # prevent find_git_root from walking up

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bootstrap_creates_plans_directories(self):
        result = bp.bootstrap(self.root, "test-system")
        for d in bp.PLANS_DIRS:
            self.assertTrue((self.root / d).is_dir(), f"{d} not created")
        self.assertIn("plans/requirements", result["created"])

    def test_bootstrap_creates_manifest(self):
        bp.bootstrap(self.root, "acme")
        manifest = self.root / bp.MANIFEST_NAME
        self.assertTrue(manifest.exists())
        data = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["system"], "acme")
        self.assertTrue(data["draft"])
        self.assertEqual(len(data["repos"]), 1)
        self.assertIn("app", data["repos"][0]["roles"])
        self.assertIn("planning", data["repos"][0]["roles"])

    def test_bootstrap_creates_requirement_when_title_given(self):
        bp.bootstrap(self.root, "acme", title="Add payments", statement="Process credit cards")
        req_path = self.root / "plans" / "intake" / "REQ-1.json"
        self.assertTrue(req_path.exists())
        data = json.loads(req_path.read_text(encoding="utf-8"))
        self.assertEqual(data["id"], "REQ-1")
        self.assertEqual(data["title"], "Add payments")
        self.assertEqual(data["statement"], "Process credit cards")

    def test_bootstrap_skips_no_requirement_without_title(self):
        result = bp.bootstrap(self.root, "acme")
        req_path = self.root / "plans" / "intake" / "REQ-1.json"
        self.assertFalse(req_path.exists())
        self.assertNotIn("plans/intake/REQ-1.json", result["created"])

    def test_bootstrap_creates_adlc_directory(self):
        bp.bootstrap(self.root, "acme")
        self.assertTrue((self.root / ".adlc").is_dir())

    def test_bootstrap_idempotent(self):
        bp.bootstrap(self.root, "acme", title="First")
        result2 = bp.bootstrap(self.root, "acme", title="Second")
        self.assertTrue(len(result2["skipped"]) > 0)
        req = json.loads((self.root / "plans" / "intake" / "REQ-1.json").read_text(encoding="utf-8"))
        self.assertEqual(req["title"], "First")

    def test_check_bootstrapped_false_on_empty(self):
        self.assertFalse(bp.check_bootstrapped(self.root))

    def test_check_bootstrapped_true_after_bootstrap(self):
        bp.bootstrap(self.root, "acme")
        self.assertTrue(bp.check_bootstrapped(self.root))

    def test_main_check_exit_codes(self):
        self.assertEqual(bp.main(["--root", str(self.root), "--check"]), 1)
        bp.bootstrap(self.root, "acme")
        self.assertEqual(bp.main(["--root", str(self.root), "--check"]), 0)

    def test_main_bootstrap(self):
        code = bp.main(["--root", str(self.root), "--system", "test", "--title", "Hello"])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "plans").is_dir())
        self.assertTrue((self.root / "plans" / "intake" / "REQ-1.json").exists())

    def test_repo_name_from_path(self):
        self.assertEqual(bp.repo_name_from_path(Path("/foo/my-project")), "my-project")
        self.assertEqual(bp.repo_name_from_path(Path("/foo/My Project")), "my-project")

    def test_requirement_default_statement(self):
        bp.bootstrap(self.root, "acme", title="Build API")
        req = json.loads((self.root / "plans" / "intake" / "REQ-1.json").read_text(encoding="utf-8"))
        self.assertEqual(req["statement"], "Implement: Build API")


if __name__ == "__main__":
    unittest.main()
