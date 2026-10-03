import sqlite3
import unittest

from tests._support import CI, DEVELOPER, HUMAN_LEAD, TempEnv

from adlc_mcp.app import build_modules
from adlc_mcp.kernel.errors import PermissionDenied, ValidationError

V1 = {"fields": {"id": {"type": "string", "required": True}, "amount": {"type": "integer", "required": True}}}
V2_REMOVES_AMOUNT = {"fields": {"id": {"type": "string", "required": True}}}
V2_ADDS_OPTIONAL = {"fields": {**V1["fields"], "note": {"type": "string", "required": False}}}
CONSUMER_NEEDS_NOTE = {"fields": {"id": {"type": "string", "required": True}, "note": {"type": "string", "required": True}}}


class CRTestCase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv("contract_registry")
        self.registry = build_modules(self.env.config)
        self.cr = self.registry.get("contract_registry").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def register(self, ctype="http"):
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc", version="1", spec=V1,
                                  type=ctype, consumers=["billing"])
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc", version="1", spec=V1,
                                  type=ctype, party="billing")


class Deployments(CRTestCase):
    def test_record_deployment_is_system_only(self):
        self.register()
        for who in (DEVELOPER, HUMAN_LEAD):
            with self.assertRaises(PermissionDenied):
                self.cr.record_deployment(who, app="billing", version="5", environment="prod",
                                          contract_versions={"orders": "1"})
        self.cr.record_deployment(CI, app="billing", version="5", environment="prod", contract_versions={"orders": "1"})
        with self.assertRaises(sqlite3.IntegrityError):
            self.cr._store.conn.execute("DELETE FROM deployments")
        self.assertTrue(all(r["ok"] for r in self.cr.verify()))


class Compatibility(CRTestCase):
    def test_unknown_deployed_counterpart_is_incompatible(self):
        self.register()
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc", version="2",
                                  spec=V2_ADDS_OPTIONAL, type="http")
        r = self.cr.check_compatibility(DEVELOPER, contract_id="orders", candidate_version="2", party="order-svc",
                                        environment="prod")
        self.assertEqual((r["result"], r["verification"]), ("INCOMPATIBLE", "NOT_VERIFIED"))
        self.assertIn("no recorded deployment", r["reasons"][0])

    def test_against_recorded_deployed_versions(self):
        self.register()
        self.cr.record_deployment(CI, app="billing", version="5", environment="prod", contract_versions={"orders": "1"})
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc", version="2",
                                  spec=V2_ADDS_OPTIONAL, type="http")
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc", version="3",
                                  spec=V2_REMOVES_AMOUNT, type="http")
        ok = self.cr.check_compatibility(DEVELOPER, contract_id="orders", candidate_version="2", party="order-svc",
                                         environment="prod")
        self.assertEqual((ok["result"], ok["verification"]), ("COMPATIBLE", "VERIFIED"))
        bad = self.cr.check_compatibility(DEVELOPER, contract_id="orders", candidate_version="3", party="order-svc",
                                          environment="prod")
        self.assertEqual(bad["result"], "INCOMPATIBLE")
        self.assertIn("amount", bad["checks"][0]["issues"][0])

    def test_event_consumer_checked_against_all_retained_producer_versions(self):
        self.register("event")
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc", version="2",
                                  spec=V2_ADDS_OPTIONAL, type="event")
        self.cr.record_deployment(CI, app="order-svc", version="10", environment="prod", contract_versions={"orders": "1"})
        self.cr.record_deployment(CI, app="order-svc", version="11", environment="prod", contract_versions={"orders": "2"})
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc", version="2",
                                  spec=CONSUMER_NEEDS_NOTE, type="event", party="billing")
        r = self.cr.check_compatibility(DEVELOPER, contract_id="orders", candidate_version="2", party="billing",
                                        environment="prod")
        # v2 producer sends `note` only optionally and v1 events in the topic lack it entirely.
        self.assertEqual(r["result"], "INCOMPATIBLE")
        self.assertEqual(len(r["checks"]), 2)

    def test_versions_immutable_and_provider_fixed(self):
        self.register()
        with self.assertRaises(ValidationError):
            self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc", version="1",
                                      spec=V2_REMOVES_AMOUNT, type="http")
        with self.assertRaises(ValidationError):
            self.cr.register_contract(DEVELOPER, contract_id="orders", provider="other", version="9", spec=V1, type="http")


class Drift(CRTestCase):
    def test_detect_drift(self):
        self.register()
        r = self.cr.detect_drift(DEVELOPER, contract_id="orders", observed_spec={
            "fields": {"id": {"type": "integer"}, "extra": {"type": "string"}}})
        self.assertTrue(r["drift"])
        p = r["payloads"]["default"]
        self.assertEqual((p["missing_in_observed"], p["undeclared_in_observed"], p["type_mismatch"]),
                         (["amount"], ["extra"], ["id"]))
        self.assertFalse(self.cr.detect_drift(DEVELOPER, contract_id="orders", observed_spec=V1)["drift"])


if __name__ == "__main__":
    unittest.main()
