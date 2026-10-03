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


if __name__ == "__main__":
    unittest.main()
