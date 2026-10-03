"""Tests for stack_fingerprint.py and test_asset_catalog.py (stdlib unittest)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import stack_fingerprint as sf  # noqa: E402
import test_asset_catalog as tac  # noqa: E402


def make_repo(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


class StackFingerprintTests(unittest.TestCase):
    def test_typescript_react_playwright_cucumber(self):
        root = make_repo({
            "package.json": json.dumps({
                "dependencies": {"react": "18", "react-dom": "18"},
                "devDependencies": {"vitest": "1", "@testing-library/react": "14", "msw": "2",
                                    "@playwright/test": "1.47", "@cucumber/cucumber": "10"}}),
            "playwright.config.ts": "export default {}",
            "src/Button.tsx": "x", "src/Button.test.tsx": "x", "src/Form.tsx": "x",
            "src/Form.test.tsx": "x", "src/util.ts": "x",
            "e2e/login.spec.ts": "x",
            "features/login.feature": "Feature: x",
        })
        fp = sf.fingerprint(root)
        self.assertIn("react", fp["ui_paradigm"])
        self.assertIn("vitest", fp["unit_runner"])
        self.assertIn("msw", fp["mock_libs"])
        self.assertIn("playwright", fp["e2e_driver"])
        self.assertIn("cucumber-js", fp["bdd"])
        self.assertIn("testing-library", fp["component_testing"])
        self.assertEqual(fp["naming_suffixes"][0], "*.test.<js|ts>")
        self.assertIn("e2e", fp["test_dirs"])
        self.assertIn("playwright.config.ts", fp["runner_configs"])

    def test_flutter_mirrored_layout(self):
        root = make_repo({
            "pubspec.yaml": "name: app\ndependencies:\n  flutter:\n    sdk: flutter\n  flutter_bloc: ^8.0.0\n"
                            "dev_dependencies:\n  flutter_test:\n    sdk: flutter\n  integration_test:\n"
                            "    sdk: flutter\n  mocktail: ^1.0.0\n  bloc_test: ^9.0.0\n",
            "lib/main.dart": "x", "lib/login/login_page.dart": "x",
            "test/login/login_page_test.dart": "x", "test/login/login_bloc_test.dart": "x",
            "integration_test/app_test.dart": "x",
        })
        fp = sf.fingerprint(root)
        self.assertEqual(fp["ui_paradigm"], ["flutter"])
        self.assertIn("flutter_test", fp["unit_runner"])
        self.assertIn("mocktail", fp["mock_libs"])
        self.assertIn("bloc_test", fp["mock_libs"])
        self.assertIn("flutter-integration_test", fp["e2e_driver"])
        self.assertEqual(fp["layout"], "mirrored")
        self.assertEqual(fp["naming_suffixes"], ["*_test.dart"])

    def test_java_gradle_and_no_tests(self):
        root = make_repo({
            "build.gradle": 'dependencies { testImplementation "org.junit.jupiter:junit-jupiter:5.10.0"\n'
                            'testImplementation "io.cucumber:cucumber-java:7.0"\n'
                            'testImplementation "io.rest-assured:rest-assured:5.0" }',
            "src/main/java/App.java": "x",
        })
        fp = sf.fingerprint(root)
        self.assertIn("junit", fp["unit_runner"])
        self.assertIn("cucumber-jvm", fp["bdd"])
        self.assertIn("rest-assured", fp["api_testing"])
        self.assertFalse(fp["has_tests"])
        self.assertEqual(fp["layout"], "none")

    def test_skips_node_modules(self):
        root = make_repo({"package.json": "{}", "node_modules/x/a.test.js": "x"})
        self.assertFalse(sf.fingerprint(root)["has_tests"])

    def test_bad_input_exit_code(self):
        self.assertEqual(sf.main(["/definitely/not/here"]), 2)

    def test_writes_stack_json_by_default(self):
        root = make_repo({"package.json": "{}", "src/a.test.ts": "x"})
        self.assertEqual(sf.main([str(root)]), 0)
        data = json.loads((root / ".adlc/catalog/stack.json").read_text(encoding="utf-8"))
        self.assertEqual(data["classification"], "FACT")


class AssetCatalogTests(unittest.TestCase):
    def setUp(self):
        self.root = make_repo({
            "features/step_definitions/login.steps.ts":
                "Given('the user {string} is signed in', async function (u) { secret() })\n"
                "When(/^they open the (\\w+) page$/, async function (p) {})\n",
            "features/step_definitions/legacy.steps.ts":
                "Given('the user {word} is signed in', async () => {})\n",
            "src/test/java/steps/CartSteps.java":
                '@When("the cart contains {int} items")\npublic void x(int n) {}\n',
            "tests/steps/test_cart.py": "@then(parsers.parse('the total is {amount}'))\ndef f(amount): pass\n",
            "Steps/CartSteps.cs": '[Given(@"a cart with (.*) items")]\npublic void G(int n) {}\n',
            "test_driver/steps/login_steps.dart":
                "final s = given1<String, FlutterWorld>('I enter {string}', (v, ctx) async {});\n",
            "tests/fixtures/user.fixtures.ts": "export const u = {}",
            "tests/builders/OrderBuilder.ts": "export class OrderBuilder {}",
            "tests/pages/LoginPage.ts": "export class LoginPage {}",
            "tests/login.spec.ts": "import { LoginPage } from './pages/LoginPage'\n"
                                   "import { OrderBuilder } from './builders/OrderBuilder'\n"
                                   "test('x', async () => { expect(1).toBe(1) })\n",
            "tests/cart.spec.ts": "test.skip('y', async () => { expect(1).toBe(1) })\n",
            "tests/noassert.spec.ts": "test('z', async () => { doThing() })\n",
            "tests/flaky.spec.ts": "test('f', async () => { expect(1).toBe(1) })\n",
        })

    def test_step_patterns_across_frameworks(self):
        cat = tac.catalog(self.root)
        fw = {s["framework"] for s in cat["step_patterns"]}
        self.assertTrue({"cucumber-js", "cucumber-jvm", "behave/pytest-bdd", "specflow/reqnroll",
                         "dart-gherkin"} <= fw, fw)
        pats = {s["pattern"] for s in cat["step_patterns"]}
        self.assertIn("the user {string} is signed in", pats)
        self.assertIn("^they open the (\\w+) page$", pats)
        self.assertIn("the total is {amount}", pats)

    def test_duplicates_detected_after_normalization(self):
        cat = tac.catalog(self.root)
        norms = [d["normalized"] for d in cat["duplicate_steps"]]
        self.assertIn("the user {} is signed in", norms)

    def test_assets_catalogued(self):
        cat = tac.catalog(self.root)
        self.assertIn("tests/fixtures/user.fixtures.ts", cat["fixtures"])
        self.assertIn("tests/builders/OrderBuilder.ts", cat["fixtures"])
        self.assertIn("tests/pages/LoginPage.ts", cat["page_objects"])

    def test_golden_samples_exclude_skipped_flaky_and_rank_helpers(self):
        flaky = self.root / "flaky.json"
        flaky.write_text(json.dumps({"flaky": [{"test": "tests/flaky.spec.ts::f"}]}), encoding="utf-8")
        cat = tac.catalog(self.root, flaky=str(flaky))
        excluded = {e["file"]: e["reason"] for e in cat["excluded_samples"]}
        self.assertIn("tests/cart.spec.ts", excluded)
        self.assertIn("tests/flaky.spec.ts", excluded)
        ranked = [c["file"] for c in cat["golden_samples"]["*.spec.ts"]]
        self.assertEqual(ranked[0], "tests/login.spec.ts")
        self.assertEqual(ranked[-1], "tests/noassert.spec.ts")  # zero assertions ranks last

    def test_failing_junit_excludes_sample(self):
        junit = self.root / "junit.xml"
        junit.write_text('<testsuite><testcase file="tests/login.spec.ts" name="x"><failure/></testcase>'
                         '</testsuite>', encoding="utf-8")
        cat = tac.catalog(self.root, junit=[str(junit)])
        self.assertIn("tests/login.spec.ts", {e["file"] for e in cat["excluded_samples"]})

    def test_default_output_splits_step_patterns_file(self):
        rc = tac.main([str(self.root)])
        self.assertEqual(rc, 0)
        steps = json.loads((self.root / ".adlc/catalog/step-patterns.json").read_text(encoding="utf-8"))
        full = json.loads((self.root / ".adlc/catalog/test-assets.json").read_text(encoding="utf-8"))
        self.assertIn("fixtures", full)
        # phrases only: no paths, no bodies, no line numbers
        blob = json.dumps(steps)
        self.assertNotIn("step_definitions", blob)
        self.assertNotIn("secret()", blob)
        self.assertEqual(set(steps), {"classification", "source", "step_patterns", "duplicate_steps"})
        for s in steps["step_patterns"]:
            self.assertEqual(set(s), {"keyword", "pattern"})

    def test_out_override(self):
        out = Path(tempfile.mkdtemp()) / "cat"
        self.assertEqual(tac.main([str(self.root), "--out", str(out)]), 0)
        self.assertTrue((out / "step-patterns.json").exists())


if __name__ == "__main__":
    unittest.main()
