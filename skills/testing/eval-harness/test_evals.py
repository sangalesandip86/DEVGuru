"""Layer A: Structural eval tests for deterministic skill scripts.

Runs each script with canned inputs and validates the JSON output against
assertion schemas. No LLM calls — tests the deterministic layer only.

Run:  python -m unittest skills/testing/eval-harness/test_evals.py -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "skills" / "change-management" / "risk-tiering" / "scripts"))
sys.path.insert(0, str(REPO / "skills" / "skill-routing" / "skill-router" / "scripts"))
sys.path.insert(0, str(REPO / "skills" / "enforcement" / "ci-checks" / "planning-gates"))
sys.path.insert(0, str(REPO / "skills" / "enforcement" / "ci-checks" / "test-integrity"))

import eval_runner  # noqa: E402
import path_tier_lookup as ptl  # noqa: E402
import route as skill_route  # noqa: E402
import plan_lint  # noqa: E402
import impact_plan_check as ipc  # noqa: E402

ASSERTIONS_DIR = HERE / "evals"


def load_assertions(skill: str) -> dict:
    return json.loads((ASSERTIONS_DIR / skill / "assertions.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Risk Tiering Evals
# ---------------------------------------------------------------------------
class RiskTieringEvals(unittest.TestCase):
    """Eval: path_tier_lookup.py produces correct tiers for known inputs."""

    def setUp(self):
        self.assertions = load_assertions("risk-tiering")

    def _validate(self, result: dict, checks: list[dict] | None = None) -> None:
        errors = eval_runner.validate_output(result, self.assertions, {"checks": checks or []})
        self.assertEqual(errors, [], f"Assertion failures: {errors}")

    def test_basic_paths(self):
        result = ptl.compute_path_tier(["src/auth/login.py", "README.md"])
        self._validate(result, [
            {"field": "computed", "op": "eq", "value": True},
            {"field": "tier", "op": "in", "value": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
        ])
        self.assertEqual(len(result["paths"]), 2)

    def test_no_paths_is_high(self):
        result = ptl.compute_path_tier([])
        self._validate(result, [
            {"field": "computed", "op": "eq", "value": False},
            {"field": "tier", "op": "eq", "value": "HIGH"},
        ])

    def test_control_file_is_critical(self):
        result = ptl.compute_path_tier(["CLAUDE.md"])
        self._validate(result, [
            {"field": "tier", "op": "eq", "value": "CRITICAL"},
        ])
        self.assertTrue(
            any(h["rule"] == "control-files" for p in result["paths"] for h in p["matched"]),
            "CLAUDE.md should match control-files rule",
        )

    def test_agents_md_is_critical(self):
        result = ptl.compute_path_tier(["AGENTS.md"])
        self._validate(result, [
            {"field": "tier", "op": "eq", "value": "CRITICAL"},
        ])

    def test_ci_workflow_is_critical(self):
        result = ptl.compute_path_tier([".github/workflows/ci.yml"])
        self._validate(result, [
            {"field": "tier", "op": "eq", "value": "CRITICAL"},
        ])

    def test_docs_only_is_low(self):
        result = ptl.compute_path_tier(["docs/readme.md"])
        self._validate(result)
        self.assertIn(result["tier"], ["LOW", "MEDIUM"])

    def test_effective_tier_takes_max(self):
        self.assertEqual(ptl.effective_tier("LOW", "HIGH"), "HIGH")
        self.assertEqual(ptl.effective_tier("CRITICAL", "LOW"), "CRITICAL")
        self.assertEqual(ptl.effective_tier(None, "MEDIUM"), "MEDIUM")
        self.assertEqual(ptl.effective_tier(None, None), "HIGH")

    def test_mixed_paths_takes_highest(self):
        result = ptl.compute_path_tier(["README.md", "CLAUDE.md"])
        self._validate(result, [
            {"field": "tier", "op": "eq", "value": "CRITICAL"},
        ])

    def test_auth_paths_tier(self):
        result = ptl.compute_path_tier(["src/auth/middleware.ts", "src/auth/rbac.ts"])
        self._validate(result, [
            {"field": "computed", "op": "eq", "value": True},
        ])
        self.assertIn(result["tier"], ["MEDIUM", "HIGH", "CRITICAL"])

    def test_decompose_required_on_many_files(self):
        paths = [f"src/file_{i}.py" for i in range(100)]
        result = ptl.compute_path_tier(paths, changed_lines=5000)
        self._validate(result)

    def test_type_floor_via_cli(self):
        result = ptl.compute_path_tier(["docs/readme.md"])
        base_tier = result["tier"]
        combined = ptl.effective_tier("HIGH", base_tier)
        self.assertEqual(combined, "HIGH")


# ---------------------------------------------------------------------------
# Skill Routing Evals
# ---------------------------------------------------------------------------
class SkillRoutingEvals(unittest.TestCase):
    """Eval: route.py produces correct bindings for known inputs."""

    def setUp(self):
        self.assertions = load_assertions("skill-routing")

    def _validate(self, result: dict, checks: list[dict] | None = None) -> None:
        errors = eval_runner.validate_output(result, self.assertions, {"checks": checks or []})
        self.assertEqual(errors, [], f"Assertion failures: {errors}")

    def test_always_mandatory_present(self):
        result = skill_route.route({})
        self._validate(result, [
            {"field": "bindings", "op": "subset",
             "value": ["grounding/evidence-gate", "grounding/trust-boundaries",
                        "core/evidence-ledger"]},
        ])
        self.assertEqual(len(result["bindings"]), len(skill_route.ALWAYS_MANDATORY))

    def test_feature_story_type(self):
        result = skill_route.route({}, story_type="FEATURE_STORY")
        self._validate(result, [
            {"field": "tier_floor", "op": "eq", "value": "LOW"},
        ])

    def test_security_story_binds_security_skills(self):
        result = skill_route.route({}, story_type="SECURITY_STORY")
        self._validate(result, [
            {"field": "tier_floor", "op": "eq", "value": "HIGH"},
        ])
        self.assertIn("testing/security-testing/sast-scanner", result["bindings"])
        self.assertIn("testing/security-testing/secret-scanning", result["bindings"])
        self.assertIn("testing/security-testing/sca-dependency-audit", result["bindings"])

    def test_api_contract_story(self):
        result = skill_route.route({}, story_type="API_CONTRACT")
        self._validate(result, [
            {"field": "tier_floor", "op": "eq", "value": "HIGH"},
        ])
        self.assertIn("contracts/contract-registry", result["bindings"])
        self.assertIn("contracts/compatibility-check", result["bindings"])

    def test_ui_story_binds_playwright(self):
        result = skill_route.route({}, story_type="UI_STORY")
        self.assertIn("testing/web-ui-automation/playwright-expert", result["bindings"])
        self.assertIn("testing/web-ui-automation/visual-regression", result["bindings"])

    def test_keyword_trigger_payment(self):
        result = skill_route.route({}, paths=["payment/processor.py"])
        self._validate(result)
        self.assertIn("testing/security-testing/sast-scanner", result["bindings"])
        self.assertEqual(result["tier_floor"], "HIGH")

    def test_keyword_trigger_auth(self):
        result = skill_route.route({}, paths=["src/auth/login.ts"])
        self.assertEqual(result["tier_floor"], "HIGH")
        self.assertIn("testing/security-testing/secret-scanning", result["bindings"])

    def test_keyword_trigger_migration(self):
        result = skill_route.route({}, paths=["db/migrations/001_add_users.sql"])
        self.assertEqual(result["tier_floor"], "HIGH")

    def test_stack_driven_playwright(self):
        result = skill_route.route({"e2e_driver": ["playwright"]})
        self.assertIn("testing/web-ui-automation/playwright-expert", result["bindings"])

    def test_stack_driven_pact(self):
        result = skill_route.route({"contract_testing": ["pact"]})
        self.assertIn("testing/api-contract-testing/pact-consumer-driven", result["bindings"])

    def test_stack_driven_cucumber(self):
        result = skill_route.route({"bdd": ["cucumber-js"]})
        self.assertIn("testing/test-design/bdd-feature-authoring", result["bindings"])

    def test_per_package_stack(self):
        result = skill_route.route({
            "packages": [
                {"name": "web", "stack": {"e2e_driver": ["selenium"]}},
                {"name": "api", "stack": {"contract_testing": ["pact"]}},
            ],
        })
        self.assertIn("testing/web-ui-automation/selenium-expert", result["bindings"])
        self.assertIn("testing/api-contract-testing/pact-consumer-driven", result["bindings"])

    def test_code_change_adds_roles(self):
        result = skill_route.route({}, paths=["src/app.py"])
        self.assertIn("code-reviewer", result["roles"])
        self.assertIn("qa-derive", result["roles"])

    def test_docs_only_no_code_roles(self):
        result = skill_route.route({}, paths=["docs/readme.md"])
        self.assertEqual(result["roles"], [])

    def test_documentation_story_low_floor(self):
        result = skill_route.route({}, story_type="DOCUMENTATION")
        self.assertEqual(result["tier_floor"], "LOW")

    def test_infrastructure_story(self):
        result = skill_route.route({}, story_type="INFRASTRUCTURE")
        self.assertIn("change-management/snapshot", result["bindings"])
        self.assertEqual(result["tier_floor"], "MEDIUM")


# ---------------------------------------------------------------------------
# Planning Gates Evals
# ---------------------------------------------------------------------------
class PlanLintEvals(unittest.TestCase):
    """Eval: plan_lint.py catches invalid plans and passes valid ones."""

    def _plans_dir(self, stories: list[dict], reqs: list[dict] | None = None) -> Path:
        self._tmpdir = tempfile.TemporaryDirectory()
        p = Path(self._tmpdir.name)
        (p / "stories").mkdir()
        (p / "requirements").mkdir()
        for r in (reqs or [{"id": "REQ-1", "title": "Requirement one",
                            "statement": "A long statement for validation.",
                            "requested_by": "product-manager",
                            "business_outcome": "Better outcome for users",
                            "source_refs": [{"ref": "x", "trust_level": "EXTERNAL_UNSTRUCTURED"}]}]):
            (p / "requirements" / f"{r['id']}.yaml").write_text(
                json.dumps(r), encoding="utf-8")
        for s in stories:
            (p / "stories" / f"{s['id']}.yaml").write_text(
                json.dumps(s), encoding="utf-8")
        return p

    def tearDown(self):
        if hasattr(self, "_tmpdir"):
            self._tmpdir.cleanup()

    def _story(self, **overrides):
        s = {
            "id": "ST-1", "title": "A story", "type": "FEATURE_STORY",
            "objective": "Do it", "persona": "User", "value_statement": "so value",
            "requirement_id": "REQ-1", "scope": ["x"], "out_of_scope": [],
            "affected_paths": ["app/**"],
            "acceptance_criteria": [
                {"id": "ST-1/AC-1", "given": "a user exists",
                 "when": "the user logs in", "then": "they see the dashboard",
                 "kind": "functional", "verification": "automated"},
            ],
            "touches": {"ui": False, "api_contracts": [], "data_migration": False, "infra": False},
            "data_classification": "INTERNAL", "size": "S",
            "source_refs": [{"ref": "x", "trust_level": "EXTERNAL_UNSTRUCTURED"}],
        }
        s.update(overrides)
        return s

    def test_valid_story_passes(self):
        plans = self._plans_dir([self._story()])
        result = plan_lint.lint(plans)
        self.assertEqual(result["errors"], [])

    def test_status_field_rejected(self):
        plans = self._plans_dir([self._story(status="READY")])
        result = plan_lint.lint(plans)
        self.assertTrue(len(result["errors"]) > 0)
        status_errors = [e for e in result["errors"] if "status" in e.get("error", "").lower()]
        self.assertTrue(len(status_errors) > 0, "Expected status field rejection")

    def test_missing_ac_gwt_rejected(self):
        s = self._story()
        s["acceptance_criteria"] = [{"id": "ST-1/AC-1", "kind": "functional", "verification": "automated"}]
        plans = self._plans_dir([s])
        result = plan_lint.lint(plans)
        self.assertTrue(len(result["errors"]) > 0)

    def test_bad_ac_id_prefix(self):
        s = self._story()
        s["acceptance_criteria"] = [
            {"id": "ST-2/AC-1", "given": "a user exists",
             "when": "the user logs in", "then": "they see the dashboard",
             "kind": "functional", "verification": "automated"},
        ]
        plans = self._plans_dir([s])
        result = plan_lint.lint(plans)
        self.assertTrue(len(result["errors"]) > 0)

    def test_duplicate_ac_ids(self):
        s = self._story()
        s["acceptance_criteria"] = [
            {"id": "ST-1/AC-1", "given": "a user exists",
             "when": "the user logs in", "then": "they see the dashboard",
             "kind": "functional", "verification": "automated"},
            {"id": "ST-1/AC-1", "given": "a record exists",
             "when": "the record is deleted", "then": "it is removed",
             "kind": "functional", "verification": "automated"},
        ]
        plans = self._plans_dir([s])
        result = plan_lint.lint(plans)
        self.assertTrue(len(result["errors"]) > 0)


# ---------------------------------------------------------------------------
# Impact Plan Evals
# ---------------------------------------------------------------------------
class ImpactPlanEvals(unittest.TestCase):
    """Eval: impact_plan_check.py detects undeclared and missing test files."""

    def test_all_matched(self):
        planned = [{"path": "tests/test_foo.py", "action": "create"}]
        actual = {"tests/test_foo.py": "create"}
        result = ipc.compare(planned, actual)
        self.assertEqual(len(result["matched"]), 1)
        self.assertEqual(len(result["undeclared"]), 0)
        self.assertEqual(len(result["missing"]), 0)

    def test_undeclared_detected(self):
        planned = []
        actual = {"tests/test_new.py": "create"}
        result = ipc.compare(planned, actual)
        self.assertEqual(len(result["undeclared"]), 1)
        self.assertEqual(result["undeclared"][0]["path"], "tests/test_new.py")

    def test_missing_detected(self):
        planned = [
            {"path": "tests/test_a.py", "action": "create"},
            {"path": "tests/test_b.py", "action": "create"},
        ]
        actual = {"tests/test_a.py": "create"}
        result = ipc.compare(planned, actual)
        self.assertEqual(len(result["missing"]), 1)
        self.assertEqual(result["missing"][0]["path"], "tests/test_b.py")

    def test_action_mismatch(self):
        planned = [{"path": "tests/test_a.py", "action": "create"}]
        actual = {"tests/test_a.py": "modify"}
        result = ipc.compare(planned, actual)
        self.assertEqual(len(result["action_mismatch"]), 1)

    def test_test_file_detection(self):
        self.assertTrue(ipc.is_test_file("tests/test_foo.py"))
        self.assertTrue(ipc.is_test_file("src/app.spec.ts"))
        self.assertTrue(ipc.is_test_file("features/login.feature"))
        self.assertTrue(ipc.is_test_file("test/widget_test.dart"))
        self.assertFalse(ipc.is_test_file("src/app.py"))
        self.assertFalse(ipc.is_test_file("lib/utils.ts"))


# ---------------------------------------------------------------------------
# Eval Runner Self-Test
# ---------------------------------------------------------------------------
class EvalRunnerSelfTest(unittest.TestCase):
    """Test the eval_runner's validation logic."""

    def test_required_field_missing(self):
        errors = eval_runner.validate_output(
            {"tier": "HIGH"},
            {"required_fields": ["tier", "computed"]},
            {"checks": []},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("computed", errors[0])

    def test_enum_violation(self):
        errors = eval_runner.validate_output(
            {"tier": "ULTRA"},
            {"enum_fields": {"tier": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]}},
            {"checks": []},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("ULTRA", errors[0])

    def test_type_check(self):
        errors = eval_runner.validate_output(
            {"paths": "not-a-list"},
            {"type_fields": {"paths": "list"}},
            {"checks": []},
        )
        self.assertEqual(len(errors), 1)

    def test_check_operations(self):
        output = {"tier": "HIGH", "items": ["a", "b", "c"], "ok": True, "count": 5}

        self.assertEqual(eval_runner.validate_output(output, {},
            {"checks": [{"field": "tier", "op": "eq", "value": "HIGH"}]}), [])

        self.assertEqual(eval_runner.validate_output(output, {},
            {"checks": [{"field": "tier", "op": "ne", "value": "LOW"}]}), [])

        self.assertEqual(eval_runner.validate_output(output, {},
            {"checks": [{"field": "tier", "op": "in", "value": ["HIGH", "CRITICAL"]}]}), [])

        self.assertEqual(eval_runner.validate_output(output, {},
            {"checks": [{"field": "items", "op": "contains", "value": "b"}]}), [])

        self.assertEqual(eval_runner.validate_output(output, {},
            {"checks": [{"field": "items", "op": "not_contains", "value": "x"}]}), [])

        self.assertEqual(eval_runner.validate_output(output, {},
            {"checks": [{"field": "count", "op": "gte", "value": 3}]}), [])

        self.assertEqual(eval_runner.validate_output(output, {},
            {"checks": [{"field": "ok", "op": "truthy"}]}), [])

        self.assertEqual(eval_runner.validate_output(output, {},
            {"checks": [{"field": "items", "op": "subset", "value": ["a", "c"]}]}), [])

        self.assertEqual(eval_runner.validate_output(output, {},
            {"checks": [{"field": "items", "op": "len_gte", "value": 2}]}), [])

    def test_discover_cases(self):
        cases = eval_runner.discover_cases()
        self.assertGreater(len(cases), 0, "Should discover eval cases")
        skills_found = {c["skill"] for c in cases}
        self.assertIn("risk-tiering", skills_found)
        self.assertIn("skill-routing", skills_found)


if __name__ == "__main__":
    unittest.main()
