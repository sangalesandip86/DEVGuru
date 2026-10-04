"""Tests for scripts/sanitize_check.py — every failure path must be fail-closed."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import sanitize_check as sc  # noqa: E402

CLEAN = "When a story changes input handling, require at least one negative AC per validated field."


class SanitizeCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.project = self.dir / "project"
        self.project.mkdir()
        (self.project / "notes.md").write_text(
            "The overnight batch for the trading desk recomputes value at risk for every book "
            "using historical simulation over two hundred and fifty days.\n", encoding="utf-8")
        self.blocklist = self.dir / "bl.json"
        self.blocklist.write_text(json.dumps({"terms": ["QuantumLedger", "acme-risk", "Head of Desk Ops"]}),
                                  encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def candidate(self, text: str, name: str = "lesson.txt") -> str:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def run_check(self, text, **kw):
        return sc.run([self.candidate(text)], kw.get("blocklist", self.blocklist),
                      kw.get("paths", [self.project]))

    def test_clean_passes(self):
        r = self.run_check(CLEAN)
        self.assertEqual(r["result"], "PASS", r)

    def test_blocklist_term_fails_case_insensitive(self):
        r = self.run_check("Lesson: quantumledger feed lacked negative AC.")
        self.assertEqual(r["result"], "FAIL")
        self.assertEqual(r["findings"][0]["term"], "QuantumLedger")

    def test_blocklist_whole_word_only(self):
        self.assertEqual(self.run_check("Acme-riskless is not a term.")["result"], "PASS")

    def test_pii_email_fails_reserved_passes(self):
        self.assertEqual(self.run_check("Contact jane.doe@corpmail.de for details")["result"], "FAIL")
        self.assertEqual(self.run_check("Use buyer@example.com as the synthetic user")["result"], "PASS")

    def test_secret_fails(self):
        r = self.run_check("token = ghp_abcdefghijklmnopqrstuvwxyz0123456789")
        self.assertEqual(r["result"], "FAIL")
        self.assertTrue(all("ghp_abcdefghijklmnop" not in json.dumps(f) for f in r["findings"]))

    def test_card_number_fails(self):
        self.assertEqual(self.run_check("card 4111 1111 1111 1112 ok? and 5500005555555559")["result"], "FAIL")

    def test_verbatim_overlap_fails(self):
        r = self.run_check("Note: recomputes value at risk for every book using historical simulation.")
        self.assertEqual(r["result"], "FAIL")
        self.assertEqual(r["findings"][0]["check"], "verbatim_overlap")

    def test_short_overlap_passes(self):
        self.assertEqual(self.run_check("value at risk for every book")["result"], "PASS")

    def test_json_input_checks_string_values(self):
        p = self.candidate(json.dumps({"advice": CLEAN, "what_failed": "QuantumLedger AC"}), "l.json")
        self.assertEqual(sc.run([p], self.blocklist, [self.project])["result"], "FAIL")

    def test_fail_closed_without_blocklist(self):
        r = sc.run([self.candidate(CLEAN)], None, [self.project])
        self.assertEqual(r["result"], "FAIL")
        r = sc.run([self.candidate(CLEAN)], self.dir / "missing.json", [self.project])
        self.assertEqual(r["result"], "FAIL")

    def test_fail_closed_without_project_paths(self):
        self.assertEqual(sc.run([self.candidate(CLEAN)], self.blocklist, [])["result"], "FAIL")

    def test_fail_closed_unreadable_input(self):
        self.assertEqual(sc.run([str(self.dir / "nope.txt")], self.blocklist, [self.project])["result"], "FAIL")

    def test_candidate_inside_project_not_self_matched(self):
        p = self.project / "lesson.txt"
        p.write_text(CLEAN, encoding="utf-8")
        self.assertEqual(sc.run([str(p)], self.blocklist, [self.project])["result"], "PASS")

    def test_cli_exit_codes(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sc.main([self.candidate(CLEAN), "--blocklist", str(self.blocklist),
                                      "--project-path", str(self.project)]), 0)
            self.assertEqual(sc.main([self.candidate("QuantumLedger"), "--blocklist", str(self.blocklist),
                                      "--project-path", str(self.project)]), 1)
            self.assertEqual(sc.main([self.candidate(CLEAN), "--project-path", str(self.project)]), 2)


class GlossaryBlocklistIntegrationTest(unittest.TestCase):
    """End-to-end: build a blocklist from a project glossary, then verify sanitize_check
    catches glossary terms in lesson content (P1/J2)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "test-project"
        self.root.mkdir()
        plans = self.root / "plans"
        plans.mkdir()
        (plans / "glossary.yaml").write_text(
            "terms:\n"
            "  - term: QuantumLedger\n"
            "  - term: Value-at-Risk\n"
            "    acronym: VaR\n"
            "  - term: Head of Desk Ops\n",
            encoding="utf-8",
        )
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
        sys.path.insert(0, str(SCRIPTS))
        import build_blocklist as bb
        self.bb = bb

    def tearDown(self):
        self.tmp.cleanup()

    def _blocklist_path(self) -> Path:
        result = self.bb.build([self.root], corpus=None)
        bl_path = Path(self.tmp.name) / "blocklist.json"
        bl_path.write_text(json.dumps(result), encoding="utf-8")
        return bl_path

    def test_glossary_term_in_blocklist(self):
        result = self.bb.build([self.root], corpus=None)
        terms = set(result["terms"])
        self.assertIn("QuantumLedger", terms)
        self.assertIn("Value-at-Risk", terms)
        self.assertIn("VaR", terms)
        self.assertIn("Head of Desk Ops", terms)

    def test_glossary_term_caught_by_sanitize_check(self):
        bl = self._blocklist_path()
        r = sc.run(
            [self._write("The QuantumLedger feed missed negative ACs.")],
            bl, [self.root / "src"],
        )
        self.assertEqual(r["result"], "FAIL")
        blocklist_findings = [f for f in r["findings"] if f["check"] == "blocklist"]
        self.assertTrue(blocklist_findings, "glossary term should be caught")
        self.assertEqual(blocklist_findings[0]["term"], "QuantumLedger")

    def test_multi_word_glossary_term_caught(self):
        bl = self._blocklist_path()
        r = sc.run(
            [self._write("Reported by Head of Desk Ops in the morning standup.")],
            bl, [self.root / "src"],
        )
        self.assertEqual(r["result"], "FAIL")
        terms_found = {f["term"] for f in r["findings"] if f["check"] == "blocklist"}
        self.assertIn("Head of Desk Ops", terms_found)

    def test_acronym_from_glossary_caught(self):
        bl = self._blocklist_path()
        r = sc.run(
            [self._write("The VaR calculation was off by a factor of two.")],
            bl, [self.root / "src"],
        )
        self.assertEqual(r["result"], "FAIL")
        terms_found = {f["term"] for f in r["findings"] if f["check"] == "blocklist"}
        self.assertIn("VaR", terms_found)

    def test_clean_content_passes_with_real_blocklist(self):
        bl = self._blocklist_path()
        r = sc.run(
            [self._write("When a story changes input handling, require negative AC per field.")],
            bl, [self.root / "src"],
        )
        self.assertEqual(r["result"], "PASS", r)

    def _write(self, text: str) -> str:
        p = Path(self.tmp.name) / "candidate.txt"
        p.write_text(text, encoding="utf-8")
        return str(p)


class PiiScannerImportTest(unittest.TestCase):
    """Verify the fixture_pii_scan import-by-path mechanism works (P1/J2)."""

    def test_load_pii_scanner_succeeds(self):
        scanner = sc.load_pii_scanner()
        if sc.PII_SCAN.is_file():
            self.assertIsNotNone(scanner, "fixture_pii_scan.py exists but failed to load")
            self.assertTrue(callable(scanner), "scan_text should be callable")
        else:
            self.assertIsNone(scanner, "scanner should be None when file is missing")

    def test_pii_scanner_path_is_correct(self):
        expected = (Path(__file__).resolve().parents[2] / "enforcement" / "ci-checks"
                    / "test-integrity" / "fixture_pii_scan.py")
        self.assertEqual(sc.PII_SCAN, expected)

    def test_pii_scanner_detects_secret(self):
        scanner = sc.load_pii_scanner()
        if scanner is None:
            self.skipTest("fixture_pii_scan.py not available")
        findings = scanner("<test>", "password = ghp_abcdefghij1234567890abcdefghij1234", set(), set())
        self.assertTrue(len(findings) > 0, "scanner should detect GitHub PAT")


if __name__ == "__main__":
    unittest.main()
