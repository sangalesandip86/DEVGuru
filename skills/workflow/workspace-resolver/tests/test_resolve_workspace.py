import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resolve_workspace as rw  # noqa: E402

GIT = rw.wl.git_available()


def mkrepo(root: Path, name: str, files: dict[str, str]) -> Path:
    d = root / name
    d.mkdir(parents=True)
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if GIT:
        rw.wl.git(["init", "-q"], d)
    else:
        (d / ".git").mkdir()
    return d


def run(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = rw.main(args)
    return code, json.loads(buf.getvalue())


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_role_heuristics(self):
        app = mkrepo(self.root, "svc", {"package.json": "{}", "src/index.ts": ""})
        plans = mkrepo(self.root, "plans-repo", {"plans/requirements/REQ-1.yaml": "id: REQ-1"})
        contracts = mkrepo(self.root, "api-contracts", {"openapi.yaml": "openapi: 3.1.0"})
        infra = mkrepo(self.root, "infra", {"main.tf": ""})
        e2e = mkrepo(self.root, "e2e", {"playwright.config.ts": "", "tests/a.spec.ts": ""})
        self.assertEqual(max(rw.classify(app), key=rw.classify(app).get), "app")
        self.assertEqual(max(rw.classify(plans), key=rw.classify(plans).get), "planning")
        self.assertEqual(max(rw.classify(contracts), key=rw.classify(contracts).get), "contracts")
        self.assertEqual(max(rw.classify(infra), key=rw.classify(infra).get), "infra")
        self.assertEqual(max(rw.classify(e2e), key=rw.classify(e2e).get), "tests")


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_single_repo_default_puts_planning_in_app_repo(self):
        app = mkrepo(self.root, "svc", {"pyproject.toml": "", "src/x.py": ""})
        res = rw.resolve(["app", "planning"], app)
        self.assertEqual(res["roles"]["app"]["status"], "FOUND")
        self.assertEqual(res["roles"]["planning"]["status"], "FOUND")
        self.assertTrue(res["roles"]["planning"]["single_repo_default"])
        self.assertFalse(res["roles"]["planning"]["plans_dir_exists"])
        self.assertTrue(res["ok"])

    def test_current_repo_beats_sibling_and_sibling_found(self):
        app = mkrepo(self.root, "svc", {"go.mod": "", "cmd/main.go": ""})
        mkrepo(self.root, "other-svc", {"go.mod": "", "cmd/main.go": ""})
        mkrepo(self.root, "acme-plans", {"plans/stories/ST-1.yaml": "id: ST-1"})
        res = rw.resolve(["app", "planning"], app)
        self.assertEqual(Path(res["roles"]["app"]["path"]).name, "svc")
        self.assertEqual(Path(res["roles"]["planning"]["path"]).name, "acme-plans")
        self.assertEqual(res["roles"]["planning"]["source"], "sibling")

    def test_ambiguous_siblings(self):
        app = mkrepo(self.root, "svc", {"go.mod": "", "cmd/main.go": ""})
        mkrepo(self.root, "plans-a", {"plans/x.yaml": ""})
        mkrepo(self.root, "plans-b", {"plans/x.yaml": ""})
        res = rw.resolve(["planning"], app)
        self.assertEqual(res["roles"]["planning"]["status"], "AMBIGUOUS")
        self.assertEqual(len(res["roles"]["planning"]["candidates"]), 2)
        self.assertFalse(res["ok"])

    def test_missing_role_offers_three_options_and_references(self):
        app = mkrepo(self.root, "svc", {"package.json": "{}", "src/a.ts": "",
                                         "plans/stories/ST-1.yaml": "affected: payments-api@abc1234:src/x.ts\n"})
        res = rw.resolve(["contracts"], app)
        e = res["roles"]["contracts"]
        self.assertEqual(e["status"], "MISSING")
        self.assertEqual(len(e["options"]), 3)
        self.assertIn("payments-api", e["referenced_but_absent"])

    def test_explicit_and_manifest_precedence(self):
        ws = self.root / "ws"
        ws.mkdir()
        app = mkrepo(ws, "svc", {"package.json": "{}", "src/a.ts": ""})
        other = mkrepo(ws, "plans-manifest", {"plans/x.yaml": ""})
        explicit = mkrepo(ws, "plans-explicit", {"plans/x.yaml": ""})
        (ws / "adlc.workspace.yaml").write_text(json.dumps({
            "version": 1, "system": "acme",
            "repos": [{"name": "plans-manifest", "roles": ["planning"], "path": "plans-manifest"},
                      {"name": "svc", "roles": ["app"], "path": "svc"}]}), encoding="utf-8")
        res = rw.resolve(["planning", "app"], app)
        self.assertEqual(res["system"], "acme")
        self.assertEqual(Path(res["roles"]["planning"]["path"]).name, "plans-manifest")
        self.assertEqual(res["roles"]["planning"]["source"], "manifest")
        res = rw.resolve(["planning"], app, {"planning": str(explicit)})
        self.assertEqual(Path(res["roles"]["planning"]["path"]).name, "plans-explicit")
        self.assertTrue(other.exists())

    def test_manifest_listing_absent_repo_is_missing_with_hint(self):
        ws = self.root / "ws"
        ws.mkdir()
        app = mkrepo(ws, "svc", {"package.json": "{}", "src/a.ts": ""})
        (ws / "adlc.workspace.yaml").write_text(json.dumps({
            "version": 1, "system": "acme",
            "repos": [{"name": "acme-infra", "roles": ["infra"], "url": "https://github.com/acme/acme-infra"}]}),
            encoding="utf-8")
        res = rw.resolve(["infra"], app)
        self.assertEqual(res["roles"]["infra"]["status"], "MISSING")
        self.assertIn("acme-infra", res["roles"]["infra"]["hint"])

    def test_invalid_manifest_is_an_error(self):
        app = mkrepo(self.root, "svc", {"package.json": "{}"})
        (app / "adlc.workspace.yaml").write_text(json.dumps({"version": 1, "system": "x", "repos": [
            {"name": "svc", "roles": ["admin"]}]}), encoding="utf-8")
        code, res = run(["--cwd", str(app), "--roles", "app"])
        self.assertEqual(code, 2)
        self.assertIn("invalid manifest", res["error"])


class CreateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_local_planning_writes_skeleton_and_draft_manifest_but_no_control_files(self):
        target = self.root / "acme-plans"
        code, res = run(["--cwd", str(self.root), "--init-local", "planning", str(target), "--system", "acme"])
        self.assertEqual(code, 0)
        self.assertTrue((target / "plans/stories").is_dir())
        self.assertTrue((target / "architecture/adr").is_dir())
        manifest = json.loads((target / "adlc.workspace.yaml").read_text(encoding="utf-8"))
        self.assertTrue(manifest["draft"])
        self.assertEqual(rw.wl.validate(manifest, rw.wl.load_schema("workspace-manifest")), [])
        for cf in ("AGENTS.md", "CLAUDE.md", "CODEOWNERS", ".github"):
            self.assertFalse((target / cf).exists(), cf)
        self.assertEqual(res["operation_class"], "WORKSPACE_WRITE")

    def test_init_local_refuses_existing_repo_and_nonempty_dir(self):
        app = mkrepo(self.root, "svc", {"package.json": "{}"})
        code, res = run(["--init-local", "app", str(app)])
        self.assertEqual(code, 2)
        self.assertIn("already a git repository", res["error"])
        d = self.root / "notempty"
        d.mkdir()
        (d / "x.txt").write_text("x")
        code, res = run(["--init-local", "app", str(d)])
        self.assertEqual(code, 2)

    def test_control_file_guard(self):
        with self.assertRaises(rw.ResolveError):
            rw._assert_not_control("AGENTS.md", rw.wl.control_file_globs())
        with self.assertRaises(rw.ResolveError):
            rw._assert_not_control(".github/workflows/ci.yml", rw.wl.control_file_globs())
        rw._assert_not_control("plans/stories/.gitkeep", rw.wl.control_file_globs())

    def test_request_remote_writes_valid_request(self):
        out = self.root / "repo-request.yaml"
        code, res = run(["--request-remote", "app", "--name", "payments-svc", "--org", "acme",
                         "--owner-team", "payments", "--codeowners", "@acme/payments",
                         "--requested-by", "agent:architect",
                         "--justification", "service-map entry svc-payments needs its own repo",
                         "--out", str(out)])
        self.assertEqual(code, 0)
        req = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(rw.wl.validate(req, rw.wl.load_schema("repo-request")), [])
        self.assertIn("not performed", res["operation_class"])
        code, res = run(["--request-remote", "app", "--name", "x"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
