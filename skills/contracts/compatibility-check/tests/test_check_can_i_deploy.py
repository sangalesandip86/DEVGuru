import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-can-i-deploy.py"
spec = importlib.util.spec_from_file_location("can_i_deploy", SCRIPT)
cid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cid)


def registry():
    return {
        "contracts": [
            {"id": "billing-api", "type": "http", "provider": "billing", "consumers": ["web"],
             "verifications": [
                 {"provider_version": "1.4.0", "consumer": "web", "consumer_version": "2.0.0", "result": "COMPATIBLE"},
                 {"provider_version": "1.3.0", "consumer": "web", "consumer_version": "2.1.0", "result": "COMPATIBLE"},
                 {"provider_version": "1.5.0", "consumer": "web", "consumer_version": "2.0.0", "result": "INCOMPATIBLE"},
             ]},
            {"id": "refund-events", "type": "event", "provider": "billing", "consumers": ["ledger"],
             "verifications": [
                 {"provider_version": "1.3.0", "consumer": "ledger", "consumer_version": "3.1.0", "result": "COMPATIBLE"},
                 {"provider_version": "1.2.0", "consumer": "ledger", "consumer_version": "3.1.0", "result": "INCOMPATIBLE"},
                 {"provider_version": "1.4.0", "consumer": "ledger", "consumer_version": "3.0.0", "result": "COMPATIBLE"},
             ]},
        ],
        "deployments": [
            {"application": "billing", "version": "1.2.0", "environment": "prod"},
            {"application": "billing", "version": "1.3.0", "environment": "prod", "retained_versions": ["1.2.0", "1.3.0"]},
            {"application": "web", "version": "2.0.0", "environment": "prod"},
            {"application": "ledger", "version": "3.0.0", "environment": "prod"},
        ],
    }


class CanIDeployTest(unittest.TestCase):
    def test_new_provider_against_deployed_consumers(self):
        r = cid.can_i_deploy(registry(), "billing", "1.4.0", "prod")
        self.assertTrue(r["can_deploy"], r)
        self.assertEqual({c["direction"] for c in r["checks"]}, {"new-producer->old-consumer"})

    def test_incompatible_verification_blocks(self):
        r = cid.can_i_deploy(registry(), "billing", "1.5.0", "prod")
        self.assertFalse(r["can_deploy"])

    def test_new_consumer_against_deployed_provider_not_latest(self):
        # web 2.1.0 is verified against billing 1.3.0 (deployed), not some newer billing.
        r = cid.can_i_deploy(registry(), "web", "2.1.0", "prod")
        self.assertTrue(r["can_deploy"], r)
        self.assertEqual(r["checks"][0]["provider_version"], "1.3.0")

    def test_event_consumer_checked_against_retained_producer_versions(self):
        r = cid.can_i_deploy(registry(), "ledger", "3.1.0", "prod")
        self.assertFalse(r["can_deploy"])
        bad = [c for c in r["checks"] if c["result"] == "INCOMPATIBLE"]
        self.assertEqual(bad[0]["provider_version"], "1.2.0")
        self.assertEqual(bad[0]["direction"], "retained-producer->new-consumer")

    def test_missing_verification_is_incompatible_by_default(self):
        r = cid.can_i_deploy(registry(), "web", "9.9.9", "prod")
        self.assertFalse(r["can_deploy"])
        self.assertIn("COMPATIBILITY_UNKNOWN", r["reason_codes"])

    def test_missing_deployment_record_is_incompatible(self):
        r = cid.can_i_deploy(registry(), "billing", "1.4.0", "staging")
        self.assertFalse(r["can_deploy"])
        self.assertIn("no deployment record", r["checks"][0]["reason"])

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "reg.json"
            p.write_text(json.dumps(registry()), encoding="utf-8")
            args = ["--registry", str(p), "--environment", "prod", "--application", "billing"]
            self.assertEqual(cid.main(args + ["--version", "1.4.0"]), 0)
            self.assertEqual(cid.main(args + ["--version", "1.5.0"]), 1)
            self.assertEqual(cid.main(["--registry", str(Path(d) / "nope.json"), "--application", "a",
                                       "--version", "1", "--environment", "prod"]), 2)


if __name__ == "__main__":
    unittest.main()
