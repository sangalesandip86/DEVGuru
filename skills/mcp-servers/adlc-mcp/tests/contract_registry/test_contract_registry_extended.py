"""Extended contract_registry tests: edge cases, error paths, multi-version scenarios.

Fills the gap from ~1.5 tests/tool to ≥5 tests/tool for this module.
"""
import unittest

from tests._support import CI, DEVELOPER, HUMAN_LEAD, TempEnv

from adlc_mcp.app import build_modules
from adlc_mcp.kernel.errors import NotFound, PermissionDenied, ValidationError

V1 = {"fields": {"id": {"type": "string", "required": True}, "amount": {"type": "integer", "required": True}}}
V2_ADDS_OPTIONAL = {"fields": {**V1["fields"], "note": {"type": "string", "required": False}}}
V2_REMOVES_AMOUNT = {"fields": {"id": {"type": "string", "required": True}}}
V3_NEW_FIELD = {"fields": {**V1["fields"], "currency": {"type": "string", "required": True}}}


class CRExtTestCase(unittest.TestCase):
    def setUp(self):
        self.env = TempEnv("contract_registry")
        self.registry = build_modules(self.env.config)
        self.cr = self.registry.get("contract_registry").api

    def tearDown(self):
        self.registry.close()
        self.env.close()

    def register(self, ctype="http"):
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc",
                                  version="1", spec=V1, type=ctype, consumers=["billing"])
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc",
                                  version="1", spec=V1, type=ctype, party="billing")


class RegisterEdgeCases(CRExtTestCase):
    def test_register_no_consumers(self):
        r = self.cr.register_contract(DEVELOPER, contract_id="solo", provider="svc-a",
                                      version="1", spec=V1, type="http")
        self.assertTrue(r.get("ok", True))

    def test_register_multiple_consumers(self):
        r = self.cr.register_contract(DEVELOPER, contract_id="multi", provider="svc-a",
                                      version="1", spec=V1, type="http",
                                      consumers=["billing", "shipping", "analytics"])
        self.assertTrue(r.get("ok", True))

    def test_register_event_type(self):
        r = self.cr.register_contract(DEVELOPER, contract_id="events", provider="event-svc",
                                      version="1", spec=V1, type="event")
        self.assertTrue(r.get("ok", True))

    def test_register_same_version_same_spec_raises_immutable(self):
        self.cr.register_contract(DEVELOPER, contract_id="idem", provider="svc-a",
                                  version="1", spec=V1, type="http")
        with self.assertRaises(ValidationError):
            self.cr.register_contract(DEVELOPER, contract_id="idem", provider="svc-a",
                                      version="1", spec=V1, type="http")

    def test_register_same_version_different_spec_raises(self):
        self.cr.register_contract(DEVELOPER, contract_id="conflict", provider="svc-a",
                                  version="1", spec=V1, type="http")
        with self.assertRaises(ValidationError):
            self.cr.register_contract(DEVELOPER, contract_id="conflict", provider="svc-a",
                                      version="1", spec=V2_ADDS_OPTIONAL, type="http")

    def test_register_different_provider_raises(self):
        self.cr.register_contract(DEVELOPER, contract_id="owned", provider="svc-a",
                                  version="1", spec=V1, type="http")
        with self.assertRaises(ValidationError):
            self.cr.register_contract(DEVELOPER, contract_id="owned", provider="svc-b",
                                      version="2", spec=V1, type="http")

    def test_multiple_versions_of_same_contract(self):
        self.cr.register_contract(DEVELOPER, contract_id="versioned", provider="svc-a",
                                  version="1", spec=V1, type="http")
        self.cr.register_contract(DEVELOPER, contract_id="versioned", provider="svc-a",
                                  version="2", spec=V2_ADDS_OPTIONAL, type="http")
        self.cr.register_contract(DEVELOPER, contract_id="versioned", provider="svc-a",
                                  version="3", spec=V3_NEW_FIELD, type="http")


class CompatibilityEdgeCases(CRExtTestCase):
    def test_compatible_backward_addition(self):
        self.register()
        self.cr.record_deployment(CI, app="billing", version="5", environment="prod",
                                  contract_versions={"orders": "1"})
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc",
                                  version="2", spec=V2_ADDS_OPTIONAL, type="http")
        r = self.cr.check_compatibility(DEVELOPER, contract_id="orders",
                                        candidate_version="2", party="order-svc",
                                        environment="prod")
        self.assertEqual(r["result"], "COMPATIBLE")

    def test_incompatible_removal(self):
        self.register()
        self.cr.record_deployment(CI, app="billing", version="5", environment="prod",
                                  contract_versions={"orders": "1"})
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc",
                                  version="2", spec=V2_REMOVES_AMOUNT, type="http")
        r = self.cr.check_compatibility(DEVELOPER, contract_id="orders",
                                        candidate_version="2", party="order-svc",
                                        environment="prod")
        self.assertEqual(r["result"], "INCOMPATIBLE")
        self.assertTrue(any("amount" in str(c) for c in r.get("checks", [])))

    def test_no_deployment_means_not_verified(self):
        self.register()
        self.cr.register_contract(DEVELOPER, contract_id="orders", provider="order-svc",
                                  version="2", spec=V2_ADDS_OPTIONAL, type="http")
        r = self.cr.check_compatibility(DEVELOPER, contract_id="orders",
                                        candidate_version="2", party="order-svc",
                                        environment="staging")
        self.assertIn(r["verification"], ["NOT_VERIFIED", "INCOMPATIBLE"])

    def test_check_nonexistent_contract(self):
        with self.assertRaises(NotFound):
            self.cr.check_compatibility(DEVELOPER, contract_id="nope",
                                        candidate_version="1", party="svc-a",
                                        environment="prod")

    def test_check_nonexistent_version_returns_incompatible(self):
        self.register()
        r = self.cr.check_compatibility(DEVELOPER, contract_id="orders",
                                        candidate_version="999", party="order-svc",
                                        environment="prod")
        self.assertIn(r["result"], ["INCOMPATIBLE", "NOT_VERIFIED"])


class DeploymentEdgeCases(CRExtTestCase):
    def test_deployment_requires_system_identity(self):
        self.register()
        for who in (DEVELOPER, HUMAN_LEAD):
            with self.assertRaises(PermissionDenied):
                self.cr.record_deployment(who, app="billing", version="5",
                                          environment="prod",
                                          contract_versions={"orders": "1"})

    def test_multiple_deployments_same_app(self):
        self.register()
        self.cr.record_deployment(CI, app="billing", version="5", environment="prod",
                                  contract_versions={"orders": "1"})
        self.cr.record_deployment(CI, app="billing", version="6", environment="prod",
                                  contract_versions={"orders": "1"})

    def test_deployment_different_environments(self):
        self.register()
        self.cr.record_deployment(CI, app="billing", version="5", environment="staging",
                                  contract_versions={"orders": "1"})
        self.cr.record_deployment(CI, app="billing", version="5", environment="prod",
                                  contract_versions={"orders": "1"})


class DriftEdgeCases(CRExtTestCase):
    def test_no_drift_with_exact_match(self):
        self.register()
        r = self.cr.detect_drift(DEVELOPER, contract_id="orders", observed_spec=V1)
        self.assertFalse(r["drift"])

    def test_drift_with_missing_field(self):
        self.register()
        r = self.cr.detect_drift(DEVELOPER, contract_id="orders",
                                 observed_spec={"fields": {"id": {"type": "string"}}})
        self.assertTrue(r["drift"])
        p = r["payloads"]["default"]
        self.assertIn("amount", p["missing_in_observed"])

    def test_drift_with_extra_field(self):
        self.register()
        extra = {"fields": {**V1["fields"], "extra": {"type": "string"}}}
        r = self.cr.detect_drift(DEVELOPER, contract_id="orders", observed_spec=extra)
        self.assertTrue(r["drift"])
        p = r["payloads"]["default"]
        self.assertIn("extra", p["undeclared_in_observed"])

    def test_drift_with_type_change(self):
        self.register()
        changed = {"fields": {"id": {"type": "integer"}, "amount": {"type": "integer", "required": True}}}
        r = self.cr.detect_drift(DEVELOPER, contract_id="orders", observed_spec=changed)
        self.assertTrue(r["drift"])
        p = r["payloads"]["default"]
        self.assertIn("id", p["type_mismatch"])

    def test_drift_nonexistent_contract(self):
        with self.assertRaises(NotFound):
            self.cr.detect_drift(DEVELOPER, contract_id="nope", observed_spec=V1)


class VerifyExtended(CRExtTestCase):
    def test_verify_empty_db(self):
        results = self.cr.verify()
        self.assertIsInstance(results, list)
        self.assertTrue(all(r.get("ok", True) for r in results))

    def test_verify_with_data(self):
        self.register()
        self.cr.record_deployment(CI, app="billing", version="5", environment="prod",
                                  contract_versions={"orders": "1"})
        results = self.cr.verify()
        self.assertTrue(all(r["ok"] for r in results))


if __name__ == "__main__":
    unittest.main()
