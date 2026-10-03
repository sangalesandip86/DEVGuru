import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan-api-calls.py"
spec = importlib.util.spec_from_file_location("scan_api_calls", SCRIPT)
scan_api_calls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan_api_calls)


class ScanApiCallsTest(unittest.TestCase):
    def test_outbound_inbound_and_cross_match(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            Path(a, "client.py").write_text(
                "import requests\n"
                "requests.get('https://billing.internal/v1/fees')\n"
                "requests.post(url)\n"
                "fetch('/api/refunds/42')\n", encoding="utf-8")
            Path(b, "server.ts").write_text(
                "router.get('/api/refunds/:id', handler)\n", encoding="utf-8")
            known = {"billing.internal": "acme/billing"}
            ra = scan_api_calls.scan_repo("web", Path(a), known)
            rb = scan_api_calls.scan_repo("refunds", Path(b), known)

            by_loc = {c["location"]: c for c in ra["outbound"]}
            self.assertEqual(by_loc["client.py:2"]["status"], "RESOLVED")
            self.assertEqual(by_loc["client.py:2"]["target"], "acme/billing")
            self.assertEqual(by_loc["client.py:3"]["status"], "UNRESOLVED")
            self.assertEqual(rb["inbound"][0]["route"], "/api/refunds/{}")

            edges = scan_api_calls.cross_match([ra, rb])
            self.assertEqual(len(edges), 1)
            self.assertEqual((edges[0]["source"], edges[0]["target"]), ("web", "refunds"))


if __name__ == "__main__":
    unittest.main()
