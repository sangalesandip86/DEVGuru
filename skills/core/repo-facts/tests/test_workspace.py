"""Tests for workspace.py — monorepo workspace detection."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from workspace import detect_workspace  # noqa: E402


class NpmWorkspaceTest(unittest.TestCase):
    def test_array_workspaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "name": "monorepo",
                "workspaces": ["packages/*"]
            }))
            pkg_a = root / "packages" / "pkg-a"
            pkg_a.mkdir(parents=True)
            (pkg_a / "package.json").write_text(json.dumps({"name": "pkg-a"}))
            pkg_b = root / "packages" / "pkg-b"
            pkg_b.mkdir(parents=True)
            (pkg_b / "package.json").write_text(json.dumps({"name": "pkg-b"}))

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "npm")
            self.assertEqual(len(result["packages"]), 2)
            names = [p["name"] for p in result["packages"]]
            self.assertIn("pkg-a", names)
            self.assertIn("pkg-b", names)
            self.assertTrue(result["packages"][0]["manifest"].endswith("package.json"))

    def test_object_workspaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "name": "monorepo",
                "workspaces": {"packages": ["apps/*"]}
            }))
            app = root / "apps" / "web"
            app.mkdir(parents=True)
            (app / "package.json").write_text(json.dumps({"name": "web"}))

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "npm")
            self.assertEqual(len(result["packages"]), 1)
            self.assertEqual(result["packages"][0]["name"], "web")

    def test_pnpm_workspace_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({"name": "root"}))
            (root / "pnpm-workspace.yaml").write_text("packages:\n  - 'libs/*'\n")
            lib = root / "libs" / "core"
            lib.mkdir(parents=True)
            (lib / "package.json").write_text(json.dumps({"name": "core"}))

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "npm")
            self.assertEqual(result["packages"][0]["name"], "core")

    def test_explicit_path_no_glob(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "name": "monorepo",
                "workspaces": ["packages/web"]
            }))
            web = root / "packages" / "web"
            web.mkdir(parents=True)
            (web / "package.json").write_text(json.dumps({"name": "web"}))

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "npm")
            self.assertEqual(len(result["packages"]), 1)


class CargoWorkspaceTest(unittest.TestCase):
    def test_cargo_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Cargo.toml").write_text(
                '[workspace]\nmembers = [\n  "crates/core",\n  "crates/cli"\n]\n'
            )
            for name in ("core", "cli"):
                d = root / "crates" / name
                d.mkdir(parents=True)
                (d / "Cargo.toml").write_text(f'[package]\nname = "{name}"\n')

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "cargo")
            self.assertEqual(len(result["packages"]), 2)

    def test_cargo_glob_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Cargo.toml").write_text(
                '[workspace]\nmembers = ["crates/*"]\n'
            )
            for name in ("alpha", "beta"):
                d = root / "crates" / name
                d.mkdir(parents=True)
                (d / "Cargo.toml").write_text(f'[package]\nname = "{name}"\n')

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "cargo")
            self.assertEqual(len(result["packages"]), 2)


class GoWorkspaceTest(unittest.TestCase):
    def test_go_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "go.work").write_text("go 1.22\n\nuse (\n\t./svc-a\n\t./svc-b\n)\n")
            for name in ("svc-a", "svc-b"):
                d = root / name
                d.mkdir()
                (d / "go.mod").write_text(f"module example.com/{name}\n\ngo 1.22\n")

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "go")
            self.assertEqual(len(result["packages"]), 2)

    def test_go_work_inline_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "go.work").write_text("go 1.22\n\nuse ./svc-a\n")
            d = root / "svc-a"
            d.mkdir()
            (d / "go.mod").write_text("module example.com/svc-a\n\ngo 1.22\n")

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "go")
            self.assertEqual(len(result["packages"]), 1)


class DartWorkspaceTest(unittest.TestCase):
    def test_melos(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "melos.yaml").write_text("name: my_project\npackages:\n  - packages/*\n")
            d = root / "packages" / "core"
            d.mkdir(parents=True)
            (d / "pubspec.yaml").write_text("name: core\n")

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "dart")
            self.assertEqual(len(result["packages"]), 1)


class GradleWorkspaceTest(unittest.TestCase):
    def test_settings_gradle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "settings.gradle").write_text("include ':app'\ninclude ':lib'\n")
            for name in ("app", "lib"):
                d = root / name
                d.mkdir()
                (d / "build.gradle").write_text("")

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "gradle")
            self.assertEqual(len(result["packages"]), 2)

    def test_settings_gradle_kts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "settings.gradle.kts").write_text('include(":app")\ninclude(":core")\n')
            for name in ("app", "core"):
                d = root / name
                d.mkdir()
                (d / "build.gradle.kts").write_text("")

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "gradle")
            self.assertEqual(len(result["packages"]), 2)


class MavenWorkspaceTest(unittest.TestCase):
    def test_pom_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(
                "<project>\n  <modules>\n    <module>api</module>\n    <module>web</module>\n  </modules>\n</project>\n"
            )
            for name in ("api", "web"):
                d = root / name
                d.mkdir()
                (d / "pom.xml").write_text("<project></project>")

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "maven")
            self.assertEqual(len(result["packages"]), 2)


class DotnetWorkspaceTest(unittest.TestCase):
    def test_sln_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sln_content = (
                'Project("{FAE04EC0}") = "MyLib", "src\\MyLib\\MyLib.csproj", "{GUID}"\n'
                'EndProject\n'
            )
            (root / "MyApp.sln").write_text(sln_content)
            d = root / "src" / "MyLib"
            d.mkdir(parents=True)
            (d / "MyLib.csproj").write_text("<Project></Project>")

            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "dotnet")
            self.assertEqual(len(result["packages"]), 1)
            self.assertEqual(result["packages"][0]["name"], "MyLib")


class NoWorkspaceTest(unittest.TestCase):
    def test_single_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({"name": "single"}))
            result = detect_workspace(root)
            self.assertEqual(result["workspace_type"], "none")
            self.assertEqual(result["packages"], [])

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_workspace(Path(tmp))
            self.assertEqual(result["workspace_type"], "none")
            self.assertEqual(result["packages"], [])

    def test_output_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_workspace(Path(tmp))
            self.assertIn("classification", result)
            self.assertEqual(result["classification"], "FACT")
            self.assertEqual(result["source"], "workspace.py")


class StackIntegrationTest(unittest.TestCase):
    def test_stack_with_packages(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from stack import stack_with_packages
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "name": "mono",
                "workspaces": ["packages/*"]
            }))
            pkg = root / "packages" / "api"
            pkg.mkdir(parents=True)
            (pkg / "package.json").write_text(json.dumps({
                "name": "api",
                "dependencies": {"express": "^4.0.0"}
            }))

            result = stack_with_packages(root, max_files=10_000)
            self.assertEqual(result["workspace_type"], "npm")
            self.assertEqual(result["classification"], "FACT")
            self.assertEqual(result["source"], "stack.py")
            self.assertIn("root", result)
            self.assertEqual(len(result["packages"]), 1)
            self.assertEqual(result["packages"][0]["name"], "api")
            self.assertIn("languages", result["packages"][0]["stack"])


if __name__ == "__main__":
    unittest.main()
