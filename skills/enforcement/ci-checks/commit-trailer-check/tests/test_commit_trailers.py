"""Tests for check_commit_trailers.py (finding K2)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_commit_trailers as ct


class RegexTest(unittest.TestCase):
    def test_coauthor_match(self):
        msg = "fix stuff\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        self.assertTrue(ct.COAUTHOR_RE.search(msg))

    def test_assisted_match(self):
        msg = "fix stuff\n\nAssisted-by: GPT-4"
        self.assertTrue(ct.ASSISTED_RE.search(msg))

    def test_run_id_match(self):
        msg = "fix stuff\n\nADLC-Run: R-abc123"
        self.assertTrue(ct.RUN_ID_RE.search(msg))

    def test_no_trailer(self):
        msg = "plain commit without any trailer"
        self.assertFalse(ct.COAUTHOR_RE.search(msg))
        self.assertFalse(ct.RUN_ID_RE.search(msg))


class CheckCommitsTest(unittest.TestCase):
    def _mock_log(self, messages: dict[str, str]):
        """Return a git_log mock that returns messages by SHA."""
        def fake_log(args):
            sha = args[-1]
            return messages.get(sha, "")
        return fake_log

    @patch.object(ct, "git_log")
    def test_clean_commit(self, mock_log):
        mock_log.side_effect = self._mock_log({
            "abc": "feat: add X\n\nCo-Authored-By: Claude <x>\nADLC-Run: R-1"
        })
        findings = ct.check_commits(["abc"])
        self.assertEqual(findings, [])

    @patch.object(ct, "git_log")
    def test_ai_without_run_id(self, mock_log):
        mock_log.side_effect = self._mock_log({
            "abc": "feat: add X\n\nCo-Authored-By: Claude <x>"
        })
        findings = ct.check_commits(["abc"])
        self.assertEqual(len(findings), 1)
        self.assertIn("ADLC-Run", findings[0]["issues"][0])

    @patch.object(ct, "git_log")
    def test_human_only_commit(self, mock_log):
        mock_log.side_effect = self._mock_log({
            "abc": "feat: manual change\n\nSigned-off-by: Dev <dev@ex.com>"
        })
        findings = ct.check_commits(["abc"])
        self.assertEqual(findings, [])

    @patch.object(ct, "git_log")
    def test_empty_message(self, mock_log):
        mock_log.side_effect = self._mock_log({"abc": ""})
        findings = ct.check_commits(["abc"])
        self.assertEqual(findings, [])


class CLITest(unittest.TestCase):
    def test_no_args_exits_2(self):
        code = ct.main([])
        self.assertEqual(code, 2)

    @patch.object(ct, "git_log", return_value="")
    def test_base_no_commits(self, mock_log):
        code = ct.main(["--base", "main"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
