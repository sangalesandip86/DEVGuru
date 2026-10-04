"""Tests for route.py — deterministic skill routing."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import route


EMPTY_STACK = {"languages": [], "e2e_driver": [], "unit_runner": [], "bdd": [],
               "contract_testing": [], "has_tests": False}


class AlwaysMandatoryTest(unittest.TestCase):
    def test_empty_input_returns_always_mandatory(self):
        result = route.route(EMPTY_STACK)
        for skill in route.ALWAYS_MANDATORY:
            self.assertIn(skill, result["bindings"])

    def test_tier_defaults_low(self):
        result = route.route(EMPTY_STACK)
        self.assertEqual(result["tier_floor"], "LOW")


class StoryTypeTest(unittest.TestCase):
    def test_api_contract(self):
        result = route.route(EMPTY_STACK, story_type="API_CONTRACT")
        self.assertIn("contracts/compatibility-check", result["bindings"])
        self.assertEqual(result["tier_floor"], "HIGH")

    def test_documentation(self):
        result = route.route(EMPTY_STACK, story_type="DOCUMENTATION")
        self.assertEqual(result["tier_floor"], "LOW")

    def test_unknown_type_no_crash(self):
        result = route.route(EMPTY_STACK, story_type="UNKNOWN_TYPE")
        self.assertEqual(result["tier_floor"], "LOW")


class KeywordTriggerTest(unittest.TestCase):
    def test_auth_path(self):
        result = route.route(EMPTY_STACK, paths=["src/auth/login.ts"])
        self.assertIn("testing/security-testing/sast-scanner", result["bindings"])
        self.assertEqual(result["tier_floor"], "HIGH")

    def test_billing_keyword(self):
        result = route.route(EMPTY_STACK, paths=["billing/api.py"])
        self.assertIn("testing/security-testing/sast-scanner", result["bindings"])

    def test_migration_path(self):
        result = route.route(EMPTY_STACK, paths=["db/migrations/001.sql"])
        self.assertIn("change-management/risk-tiering", result["bindings"])

    def test_llm_keyword(self):
        result = route.route(EMPTY_STACK, paths=["src/llm/chat.py"])
        self.assertIn("testing/ai-agent-testing/ai-agent-test-design", result["bindings"])


class StackDrivenTest(unittest.TestCase):
    def test_playwright(self):
        stack = {**EMPTY_STACK, "e2e_driver": ["playwright"]}
        result = route.route(stack)
        self.assertIn("testing/web-ui-automation/playwright-expert", result["bindings"])

    def test_pact(self):
        stack = {**EMPTY_STACK, "contract_testing": ["pact"]}
        result = route.route(stack)
        self.assertIn("testing/api-contract-testing/pact-consumer-driven", result["bindings"])

    def test_bdd_cucumber(self):
        stack = {**EMPTY_STACK, "bdd": ["cucumber-js"]}
        result = route.route(stack)
        self.assertIn("testing/test-design/bdd-feature-authoring", result["bindings"])


class PerPackageTest(unittest.TestCase):
    def test_package_stack_bindings(self):
        stack = {
            **EMPTY_STACK,
            "packages": [
                {"name": "mobile", "path": "apps/mobile",
                 "stack": {"e2e_driver": ["detox"], "unit_runner": [], "bdd": [], "contract_testing": []}},
            ],
        }
        result = route.route(stack)
        self.assertIn("testing/mobile-automation/detox-react-native", result["bindings"])
        self.assertTrue(any("mobile:detox" in t for t in result["triggers"]))


class RoleBindingTest(unittest.TestCase):
    def test_code_change_adds_roles(self):
        result = route.route(EMPTY_STACK, paths=["src/app.ts"])
        self.assertIn("code-reviewer", result["roles"])
        self.assertIn("qa-derive", result["roles"])

    def test_docs_only_no_code_roles(self):
        result = route.route(EMPTY_STACK, paths=["docs/README.md"])
        self.assertEqual(result["roles"], [])


class TierEscalationTest(unittest.TestCase):
    def test_multiple_triggers_highest_tier(self):
        result = route.route(EMPTY_STACK, story_type="UI_STORY",
                             paths=["src/auth/login.ts"])
        self.assertEqual(result["tier_floor"], "HIGH")


if __name__ == "__main__":
    unittest.main()
