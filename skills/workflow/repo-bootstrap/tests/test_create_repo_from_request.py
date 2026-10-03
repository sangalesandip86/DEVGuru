import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import create_repo_from_request as crr  # noqa: E402

REQUEST = {
    "version": 1, "org": "acme", "name": "payments-svc", "system": "payments", "description": "Payments API",
    "owner_team": "payments", "visibility": "private", "roles": ["app", "planning"], "template": "repo-bootstrap",
    "default_branch": "main",
    "branch_protection": {"required_reviews": 2, "require_codeowners": True,
                          "required_checks": ["adlc-control-file-policy", "dependency-decision-check"]},
    "codeowners_owner": "@acme/payments", "tech_lead_owner": "@acme/payments-leads",
    "platform_owner": "@acme/platform", "requested_by": "agent:architect",
    "justification": "service-map entry svc-payments needs its own repo",
}


def run(args, actor=None):
    env = {k: v for k, v in os.environ.items() if k != "ADLC_ACTOR"}
    if actor:
        env["ADLC_ACTOR"] = actor
    buf = io.StringIO()
    with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(buf):
        code = crr.main(args)
    return code, json.loads(buf.getvalue())


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.req = self.d / "repo-request.yaml"
        self.req.write_text(json.dumps(REQUEST), encoding="utf-8")
        self.target = self.d / "payments-svc"

    def tearDown(self):
        self.tmp.cleanup()

    def test_agent_gets_plan_only_and_nothing_is_written(self):
        code, res = run([str(self.req), "--target", str(self.target)])
        self.assertEqual(code, 0)
        self.assertFalse(res["rendered"])
        self.assertFalse(self.target.exists())
        self.assertIn("AGENTS.md", res["files"])
        self.assertIn("CODEOWNERS", res["files"])
        self.assertTrue(any(c.startswith("gh repo create acme/payments-svc --private") for c in res["commands"]))

    def test_agent_cannot_execute(self):
        code, res = run([str(self.req), "--target", str(self.target), "--execute"])
        self.assertEqual(code, 2)
        self.assertIn("ADLC_ACTOR", res["error"])
        code, res = run([str(self.req), "--target", str(self.target), "--execute"], actor="agent")
        self.assertEqual(code, 2)

    def test_human_renders_template_with_values(self):
        code, res = run([str(self.req), "--target", str(self.target)], actor="human")
        self.assertEqual(code, 0)
        self.assertTrue(res["rendered"])
        self.assertEqual((self.target / "CLAUDE.md").read_text(encoding="utf-8").strip(), "@AGENTS.md")
        owners = (self.target / "CODEOWNERS").read_text(encoding="utf-8")
        self.assertIn("package.json              @acme/payments-leads", owners)
        self.assertIn("/docs/adr/                @acme/payments-leads", owners)
        self.assertIn("/AGENTS.md                @acme/platform", owners)
        self.assertNotIn("{{", owners)
        wf = (self.target / ".github/workflows/adlc-gates.yml").read_text(encoding="utf-8")
        self.assertIn("${{ github.base_ref }}", wf)  # GitHub expressions untouched
        self.assertIn("dependency-decision-check", wf)
        self.assertIn("ref: PINNED_PLATFORM_RELEASE_SHA", wf)
        ws = json.loads((self.target / "adlc.workspace.yaml").read_text(encoding="utf-8"))
        self.assertEqual(ws["repos"][0]["roles"], ["app", "planning"])
        self.assertEqual(crr.wl.validate(ws, crr.wl.load_schema("workspace-manifest")), [])
        bp = json.loads((self.target / ".adlc/branch-protection.json").read_text(encoding="utf-8"))
        self.assertTrue(bp["required_pull_request_reviews"]["require_code_owner_reviews"])
        self.assertEqual(bp["required_pull_request_reviews"]["required_approving_review_count"], 2)

    def test_execute_refuses_unfilled_owners_and_unpinned_platform(self):
        req = dict(REQUEST)
        del req["tech_lead_owner"]
        self.req.write_text(json.dumps(req), encoding="utf-8")
        code, res = run([str(self.req), "--target", str(self.target), "--execute"], actor="ci")
        self.assertEqual(code, 2)
        self.assertIn("tech_lead_owner", res["error"])
        self.assertIn("@<tech-lead-team>", (self.target / "CODEOWNERS").read_text(encoding="utf-8"))
        self.req.write_text(json.dumps(REQUEST), encoding="utf-8")
        code, res = run([str(self.req), "--target", str(self.d / "t2"), "--execute"], actor="ci")
        self.assertEqual(code, 2)
        self.assertIn("platform-sha", res["error"])

    def test_invalid_request_and_nonempty_target(self):
        bad = dict(REQUEST, visibility="secret")
        self.req.write_text(json.dumps(bad), encoding="utf-8")
        self.assertEqual(run([str(self.req), "--target", str(self.target)])[0], 2)
        self.req.write_text(json.dumps(REQUEST), encoding="utf-8")
        self.target.mkdir()
        (self.target / "x").write_text("x")
        code, res = run([str(self.req), "--target", str(self.target)], actor="human")
        self.assertEqual(code, 2)

    def test_rendered_template_has_agents_md_shim(self):
        run([str(self.req), "--target", str(self.target)], actor="human")
        self.assertTrue((self.target / "AGENTS.md").is_file())
        self.assertIn("REPOSITORY", (self.target / "AGENTS.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
