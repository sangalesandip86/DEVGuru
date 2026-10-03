"""Tests for ci-checks/dependency-decision-check. Run:
    python -m unittest discover -s skills/enforcement/tests -v
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENF / "ci-checks" / "dependency-decision-check"))
import check_dependency_decisions as cdd  # noqa: E402


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


class ParserTests(unittest.TestCase):
    def test_npm(self):
        d = cdd.parse_npm(json.dumps({"dependencies": {"react": "^18.2.0"}, "devDependencies": {"@types/node": "20.1.0"}}))
        self.assertEqual(d, {"react": "^18.2.0", "@types/node": "20.1.0"})

    def test_requirements(self):
        d = cdd.parse_requirements("# c\nRequests[socks]>=2.31 ; python_version>'3'\n-r base.txt\nflask==3.0.0\ngit+https://x/y\n")
        self.assertEqual(d, {"requests": ">=2.31", "flask": "==3.0.0"})

    def test_pyproject(self):
        d = cdd.parse_pyproject('[project]\ndependencies=["httpx>=0.27","Pydantic_Core==2.0"]\n'
                                '[project.optional-dependencies]\ndev=["pytest>=8"]\n'
                                '[tool.poetry.dependencies]\npython="^3.11"\nrich={version="^13.0"}\n')
        self.assertEqual(d, {"httpx": ">=0.27", "pydantic-core": "==2.0", "pytest": ">=8", "rich": "^13.0"})

    def test_pom(self):
        pom = """<project xmlns="http://maven.apache.org/POM/4.0.0"><properties><jackson.version>2.17.0</jackson.version></properties>
        <dependencies><dependency><groupId>com.fasterxml.jackson.core</groupId><artifactId>jackson-databind</artifactId>
        <version>${jackson.version}</version></dependency></dependencies></project>"""
        self.assertEqual(cdd.parse_pom(pom), {"com.fasterxml.jackson.core:jackson-databind": "2.17.0"})

    def test_gradle(self):
        g = 'dependencies {\n implementation("io.ktor:ktor-server-core:2.3.0")\n testImplementation \'junit:junit:4.13.2\'\n api(platform("org.springframework.boot:spring-boot-dependencies:3.2.0"))\n}'
        self.assertEqual(cdd.parse_gradle(g), {"io.ktor:ktor-server-core": "2.3.0", "junit:junit": "4.13.2",
                                               "org.springframework.boot:spring-boot-dependencies": "3.2.0"})

    def test_gomod(self):
        g = "module x\n\ngo 1.22\n\nrequire github.com/a/b v1.2.0\nrequire (\n\tgithub.com/c/d/v2 v2.0.1 // indirect\n)\n"
        self.assertEqual(cdd.parse_gomod(g), {"github.com/a/b": "v1.2.0", "github.com/c/d/v2": "v2.0.1"})

    def test_cargo(self):
        c = '[dependencies]\nserde = { version = "1.0", features=["derive"] }\ntokio = "1.37"\n[dev-dependencies]\nproptest = "1"\n'
        self.assertEqual(cdd.parse_cargo(c), {"serde": "1.0", "tokio": "1.37", "proptest": "1"})

    def test_pubspec(self):
        p = ("name: app\ndependencies:\n  flutter:\n    sdk: flutter\n  http: ^1.2.0\n  provider:\n    version: ^6.1.0\n"
             "dev_dependencies:\n  mocktail: ^1.0.0\nflutter:\n  uses-material-design: true\n")
        self.assertEqual(cdd.parse_pubspec(p), {"http": "^1.2.0", "provider": "^6.1.0", "mocktail": "^1.0.0"})

    def test_csproj(self):
        c = ('<Project Sdk="Microsoft.NET.Sdk"><ItemGroup><PackageReference Include="Serilog" Version="3.1.1" />'
             '<PackageReference Include="Polly"><Version>8.0.0</Version></PackageReference></ItemGroup></Project>')
        self.assertEqual(cdd.parse_csproj(c), {"Serilog": "3.1.1", "Polly": "8.0.0"})

    def test_manifest_kind(self):
        self.assertEqual(cdd.manifest_kind("svc/requirements-dev.txt"), "pypi-requirements")
        self.assertEqual(cdd.manifest_kind("app/build.gradle.kts"), "gradle")
        self.assertEqual(cdd.manifest_kind("src/Api/Api.csproj"), "nuget")
        self.assertIsNone(cdd.manifest_kind("package-lock.json"))


class DiffTests(unittest.TestCase):
    def test_major_detection(self):
        self.assertTrue(cdd.is_major_bump("^17.0.2", "^18.0.0"))
        self.assertTrue(cdd.is_major_bump("0.26.0", "0.27.0"))
        self.assertFalse(cdd.is_major_bump("1.2.0", "1.9.0"))
        self.assertFalse(cdd.is_major_bump(None, "2.0"))

    def test_diff_classification(self):
        base = json.dumps({"dependencies": {"react": "^17.0.0", "lodash": "4.17.0", "moment": "2.0.0"}})
        head = json.dumps({"dependencies": {"react": "^18.0.0", "lodash": "4.17.21", "zod": "3.0.0"}})
        got = {c.package: (c.change, c.requires_decision) for c in cdd.diff_manifest("package.json", "npm", base, head)}
        self.assertEqual(got, {"react": ("major_upgrade", True), "lodash": ("upgraded", False),
                               "moment": ("removed", False), "zod": ("added", True)})

    def test_mentions(self):
        self.assertTrue(cdd.mentions("We adopt zod for validation", "zod"))
        self.assertFalse(cdd.mentions("react-dom is fine", "react"))
        self.assertTrue(cdd.mentions("use pydantic_core", "pydantic-core"))


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base, self.head = self.tmp / "base", self.tmp / "head"
        write(self.base, {"package.json": json.dumps({"dependencies": {"react": "^17.0.0"}}),
                          "requirements.txt": "flask==2.0.0\n", "README.md": "x"})
        write(self.head, {"package.json": json.dumps({"dependencies": {"react": "^18.0.0", "zod": "^3.22.0"}}),
                          "requirements.txt": "flask==2.3.0\n", "README.md": "x"})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, *extra: str) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, str(Path(cdd.__file__)), "--base-dir", str(self.base),
                               "--head-dir", str(self.head), *extra], capture_output=True, text=True)
        return proc.returncode, json.loads(proc.stdout)

    def test_fails_without_decision(self):
        code, rep = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual({f["package"] for f in rep["findings"] if f["status"] == "missing_decision"}, {"react", "zod"})
        flask = next(f for f in rep["findings"] if f["package"] == "flask")
        self.assertEqual(flask["status"], "info")

    def test_passes_with_adr_and_ledger(self):
        write(self.head, {"docs/adr/0007-validation-library.md": "# Use zod for request validation\n"})
        ev = self.tmp / "evidence.json"
        ev.write_text(json.dumps({"entries": [
            {"entry_id": "E-1", "classification": "DECISION", "content": "Upgrade react to 18", "lifecycle_state": "APPROVED"},
        ]}))
        code, rep = self.run_check("--evidence", str(ev))
        self.assertEqual(code, 0, rep)
        refs = {f["package"]: f["decision_refs"] for f in rep["findings"]}
        self.assertEqual(refs["zod"], ["adr:docs/adr/0007-validation-library.md"])
        self.assertEqual(refs["react"], ["ledger:E-1"])

    def test_rejected_or_non_decision_entries_ignored(self):
        ev = self.tmp / "evidence.json"
        ev.write_text(json.dumps([
            {"entry_id": "E-2", "classification": "DECISION", "content": "react zod", "lifecycle_state": "REJECTED"},
            {"entry_id": "E-3", "classification": "PROPOSAL", "content": "react zod"},
        ]))
        code, _ = self.run_check("--evidence", str(ev))
        self.assertEqual(code, 1)

    def test_strict_removals(self):
        write(self.head, {"requirements.txt": ""})
        _, rep = self.run_check()
        self.assertEqual(next(f for f in rep["findings"] if f["package"] == "flask")["status"], "info")
        _, rep = self.run_check("--strict-removals")
        self.assertEqual(next(f for f in rep["findings"] if f["package"] == "flask")["status"], "missing_decision")

    def test_unparseable_manifest_fails_safe(self):
        write(self.head, {"package.json": "{not json"})
        code, rep = self.run_check()
        self.assertEqual(code, 1)
        self.assertTrue(rep["errors"])

    def test_bad_args(self):
        proc = subprocess.run([sys.executable, str(Path(cdd.__file__))], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)


@unittest.skipUnless(shutil.which("git"), "git not installed")
class GitModeTests(unittest.TestCase):
    def test_git_refs(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            git = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)  # noqa: E731
            git("init", "-q")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            write(repo, {"go.mod": "module x\n\nrequire github.com/a/b v1.0.0\n"})
            git("add", ".")
            git("commit", "-qm", "base")
            write(repo, {"go.mod": "module x\n\nrequire (\n\tgithub.com/a/b v1.0.0\n\tgithub.com/spf13/cobra v1.8.0\n)\n",
                         "docs/decisions/0001-cli.md": "Adopt cobra for the CLI.\n"})
            git("add", ".")
            git("commit", "-qm", "head")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = cdd.main(["--repo", d, "--base", "HEAD~1", "--head", "HEAD"])
            self.assertEqual(json.loads(out.getvalue())["findings"][0]["package"], "github.com/spf13/cobra")
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
