"""Tests for scripts/build_blocklist.py."""
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
import build_blocklist as bb  # noqa: E402


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class BuildBlocklistTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "risk-platform"
        r = self.root
        write(r, "plans/glossary.yaml", "terms:\n  - term: Value-at-Risk\n    acronym: VaR\n  - term: Book\n")
        write(r, "plans/requirements/REQ-7.yaml",
              "id: REQ-7\ntitle: Intraday Horizon dashboard\nrequested_by: Head of Desk Ops\n"
              "statement: Feed from QuantumLedger via ingest_positions_v2 at feeds.acmebank.io\n")
        write(r, "adlc.workspace.yaml",
              "version: 1\nsystem: horizon\nrepos:\n  - name: horizon-api\n    roles: [app]\n    service: positions-svc\n")
        write(r, ".github/CODEOWNERS", "* @acme-risk/quant-devs @jdoe\n/docs/ alice@acmebank.io\n")
        write(r, "package.json", json.dumps({"name": "@acme-risk/horizon-web"}))
        write(r, "svc/pyproject.toml", '[project]\nname = "horizon_pricing"\n')
        write(r, ".git/config", '[remote "origin"]\n\turl = git@github.com:acme-risk/risk-platform.git\n')

    def tearDown(self):
        self.tmp.cleanup()

    def build(self):
        return bb.build([self.root], corpus=None)

    def test_collects_project_terms(self):
        terms = set(self.build()["terms"])
        for expected in ["Value-at-Risk", "VaR", "REQ-7", "Intraday Horizon dashboard", "Head of Desk Ops",
                         "QuantumLedger", "ingest_positions_v2", "feeds.acmebank.io", "horizon", "horizon-api",
                         "positions-svc", "acme-risk", "quant-devs", "jdoe", "acmebank.io", "horizon-web",
                         "@acme-risk/horizon-web", "horizon_pricing", "risk-platform"]:
            self.assertIn(expected, terms)

    def test_excludes_common_words(self):
        terms = {t.lower() for t in self.build()["terms"]}
        for generic in ["app", "version", "terms", "github.com", "req", "requested_by"]:
            self.assertNotIn(generic, terms)

    def test_generic_corpus_excludes_platform_words(self):
        corpus = Path(self.tmp.name) / "corpus"
        write(corpus, "x/SKILL.md", "Each story has a horizon, a book and a dashboard.")
        terms = {t.lower() for t in bb.build([self.root], corpus=corpus)["terms"]}
        self.assertNotIn("horizon", terms)
        self.assertNotIn("book", terms)
        self.assertIn("quantumledger", terms)

    def test_cli_writes_file(self):
        out = Path(self.tmp.name) / "bl.json"
        with redirect_stdout(io.StringIO()):
            rc = bb.main(["--root", str(self.root), "--out", str(out), "--no-generic-corpus"])
        self.assertEqual(rc, 0)
        self.assertIn("terms", json.loads(out.read_text(encoding="utf-8")))

    def test_missing_root_is_error(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(bb.main(["--root", str(Path(self.tmp.name) / "nope")]), 2)


if __name__ == "__main__":
    unittest.main()
