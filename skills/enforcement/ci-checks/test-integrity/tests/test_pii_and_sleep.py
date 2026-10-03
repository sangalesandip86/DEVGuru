"""Tests for fixture_pii_scan.py and no_fixed_sleep_check.py (stdlib unittest)."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_pii_scan as pii  # noqa: E402
import no_fixed_sleep_check as nfs  # noqa: E402


def tree(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def run(mod, *args) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(list(args))
    return rc, json.loads(buf.getvalue()) if buf.getvalue() else {}


class PiiScanTests(unittest.TestCase):
    def kinds(self, text, **kw):
        return [f["type"] for f in pii.scan_text("tests/fixtures/x.json", text, kw.get("domains", set()), set())]

    def test_reserved_values_pass(self):
        text = json.dumps({"email": "ada@example.com", "alt": "bob@shop.test", "card": "4242 4242 4242 4242",
                           "iban": "DE89370400440532013000", "phone": "+1 (555) 555-0123", "ip": "192.0.2.10",
                           "uk": "+44 7700 900123", "private_ip": "10.0.0.5"})
        self.assertEqual(self.kinds(text), [])

    def test_real_looking_values_flagged(self):
        text = "\n".join([
            "email: jane.doe@gmail.com",
            "card: 4532015112830366",            # Luhn-valid, not a test card
            "iban: GB29NWBK60161331926819",       # valid checksum, not in example list
            "ssn: 123-45-6789",
            "phone: (212) 867-5309",
            "ip: 8.8.8.8",
        ])
        kinds = self.kinds(text)
        for k in ("EMAIL", "PAN", "IBAN", "SSN", "PHONE", "PUBLIC_IP"):
            self.assertIn(k, kinds)

    def test_luhn_invalid_and_ids_not_flagged(self):
        self.assertEqual(self.kinds("order: 4532015112830367\nuuid: 1111111111111111"), [])

    def test_secret_like_is_info_only(self):
        findings = pii.scan_text("tests/a.ts", "const t = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.sig'", set(), set())
        self.assertEqual([(f["type"], f["severity"]) for f in findings], [("SECRET_LIKE", "info")])

    def test_values_are_masked_in_output(self):
        f = pii.scan_text("t", "jane.doe@gmail.com", set(), set())[0]
        self.assertNotIn("jane.doe@gmail.com", f["value_masked"])

    def test_cli_scans_only_test_assets_and_allowlist(self):
        root = tree({"tests/fixtures/users.json": '{"e": "real.person@corp-mail.com"}',
                     "src/config.json": '{"e": "ops@corp-mail.com"}'})
        rc, rep = run(pii, str(root))
        self.assertEqual(rc, 1)
        self.assertEqual({f["file"] for f in rep["findings"]}, {"tests/fixtures/users.json"})
        allow = Path(tempfile.mkdtemp()) / "allow.json"
        allow.write_text(json.dumps(["real.person@corp-mail.com"]), encoding="utf-8")
        rc, _ = run(pii, str(root), "--allowlist", str(allow))
        self.assertEqual(rc, 0)
        rc, _ = run(pii, str(root), "--allow-domain", "corp-mail.com")
        self.assertEqual(rc, 0)

    def test_inline_suppression_is_not_honoured(self):
        root = tree({"tests/f.json": '{"e": "jane@gmail.com"}  // pii-scan: allow'})
        rc, _ = run(pii, str(root))
        self.assertEqual(rc, 1)

    def test_bad_input(self):
        rc, _ = run(pii, "/no/such/path")
        self.assertEqual(rc, 2)


class NoFixedSleepTests(unittest.TestCase):
    def test_flags_per_language(self):
        root = tree({
            "e2e/login.spec.ts": "await page.waitForTimeout(2000)\ncy.wait(500)\ncy.wait('@login')\n",
            "tests/test_api.py": "import time\ntime.sleep(1)\n",
            "src/test/java/LoginTest.java": "Thread.sleep(1000);",
            "integration_test/app_test.dart": "await Future.delayed(const Duration(seconds: 2));",
            "pkg/api_test.go": "time.Sleep(100 * time.Millisecond)",
            "src/app.ts": "setTimeout(() => {}, 1000)",   # not a test path: ignored
        })
        rc, rep = run(nfs, str(root))
        self.assertEqual(rc, 1)
        rules = sorted(v["rule"] for v in rep["violations"])
        self.assertEqual(rules, ["dart-future-delayed", "go-time-sleep", "js-cy-wait-number",
                                 "js-wait-for-timeout", "jvm-thread-sleep", "py-time-sleep"])

    def test_comments_and_state_waits_pass(self):
        root = tree({"e2e/a.spec.ts": "// never use page.waitForTimeout(1000)\n"
                                      "await expect(page.getByRole('button')).toBeVisible()\n"
                                      "await page.waitForResponse('**/api/orders')\n"})
        rc, rep = run(nfs, str(root))
        self.assertEqual(rc, 0, rep)

    def test_reviewed_allowlist(self):
        root = tree({"e2e/legacy/old.spec.ts": "await page.waitForTimeout(100)"})
        cfg = Path(tempfile.mkdtemp()) / "c.json"
        cfg.write_text(json.dumps({"allow": [{"path_glob": "e2e/legacy/*", "rule": "js-wait-for-timeout",
                                              "reason": "legacy suite, migration tracked in ST-90"}]}), encoding="utf-8")
        rc, _ = run(nfs, str(root), "--config", str(cfg))
        self.assertEqual(rc, 0)
        cfg.write_text(json.dumps({"allow": [{"path_glob": "e2e/**"}]}), encoding="utf-8")  # no reason
        rc, _ = run(nfs, str(root), "--config", str(cfg))
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
