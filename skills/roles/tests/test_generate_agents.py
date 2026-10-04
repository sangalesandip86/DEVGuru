import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import generate_agents as ga  # noqa: E402

ROLES_DIR = Path(__file__).resolve().parents[1]


def _write_role(root: Path, spec: dict, body: str = "# Role\n\nSee [gate](../../grounding/evidence-gate/SKILL.md).\n"):
    d = root / spec["name"]
    d.mkdir(parents=True)
    (d / "role.yaml").write_text(json.dumps(spec), encoding="utf-8")
    (d / "ROLE.md").write_text(body, encoding="utf-8")


class RealRolesTest(unittest.TestCase):
    def test_all_roles_load_and_validate(self):
        names = {r["name"] for r in ga.load_roles(ROLES_DIR)}
        self.assertEqual(names, {"product-owner", "product-planner", "architect", "developer", "qa-derive",
                                 "qa-diagnose", "test-engineer", "security-reviewer", "code-reviewer"})

    def test_qa_derive_denies_implementation_reads(self):
        specs = {r["name"]: r for r in ga.load_roles(ROLES_DIR)}
        self.assertIn("src/**", specs["qa-derive"]["denied_paths"]["read"])
        self.assertNotIn("src/**", specs["qa-diagnose"]["denied_paths"].get("read", []))

    def test_readonly_reviewers_have_no_write_tools(self):
        files = ga.build(ROLES_DIR)
        for role in ("code-reviewer", "security-reviewer"):
            fm = files[f"claude/.claude/agents/{role}.md"].split("---")[1]
            tools_line = [l for l in fm.splitlines() if l.startswith("tools:")][0]
            self.assertNotIn("Edit", tools_line)
            self.assertNotIn("Write", tools_line)
            disallowed_line = [l for l in fm.splitlines() if l.startswith("disallowedTools:")][0]
            self.assertIn("Edit", disallowed_line)
            self.assertIn("Write", disallowed_line)

    def test_all_agents_have_max_turns_and_isolation(self):
        files = ga.build(ROLES_DIR)
        for spec in ga.load_roles(ROLES_DIR):
            fm = files[f"claude/.claude/agents/{spec['name']}.md"].split("---")[1]
            expected = ga.MAX_TURNS.get(spec["name"], ga.DEFAULT_MAX_TURNS)
            self.assertIn(f'maxTurns: {expected}', fm, f"{spec['name']} wrong maxTurns")
            self.assertIn('isolation: "worktree"', fm, f"{spec['name']} missing isolation")

    def test_all_mcp_tools_use_single_adlc_server(self):
        for spec in ga.load_roles(ROLES_DIR):
            self.assertEqual(spec["mcp_servers"], ["adlc"])
            for tool in spec["allowed_tools"]:
                if tool.startswith("mcp:"):
                    self.assertTrue(tool.startswith("mcp:adlc."), tool)

    def test_product_planner_writes_plans_only_without_shell(self):
        spec = next(r for r in ga.load_roles(ROLES_DIR) if r["name"] == "product-planner")
        self.assertEqual(spec["can_modify"], ["plans/**"])
        self.assertNotIn("bash", spec["allowed_tools"])
        self.assertEqual(spec["operation_classes"], ["READ", "WORKSPACE_WRITE", "REPO_WRITE"])
        files = ga.build(ROLES_DIR)
        self.assertIn("Rule of Two", files["claude/.claude/agents/product-planner.md"])
        fm = files["claude/.claude/agents/product-planner.md"].split("---")[1]
        self.assertIn("Bash", [l for l in fm.splitlines() if l.startswith("disallowedTools:")][0])

    def test_oracle_binding_split(self):
        specs = {r["name"]: r for r in ga.load_roles(ROLES_DIR)}
        self.assertEqual(specs["qa-derive"]["can_modify"], ["plans/test-designs/**", "**/*.feature"])
        for role in ("test-engineer", "qa-diagnose"):
            self.assertIn("plans/test-designs/**", specs[role]["denied_paths"]["write"])
            self.assertIn("**/*.feature", specs[role]["denied_paths"]["write"])
            self.assertIn("src/**", specs[role]["denied_paths"]["write"])
        self.assertIn(".env", specs["test-engineer"]["denied_paths"]["read"])
        self.assertIn("src/**", specs["qa-derive"]["denied_paths"]["read"])
        self.assertIn(".adlc/catalog/step-patterns.json", specs["qa-derive"]["can_read"])
        self.assertIn("integrity-guard", " ".join(c["scope"] for c in specs["qa-diagnose"]["can_set"]))

    def test_project_conventions_required_for_build_roles(self):
        specs = {r["name"]: r for r in ga.load_roles(ROLES_DIR)}
        for role in ("developer", "architect", "code-reviewer", "test-engineer"):
            self.assertIn("skills/engineering-design/project-conventions", specs[role]["skills_required"], role)

    def test_refinement_judgments(self):
        specs = {r["name"]: r for r in ga.load_roles(ROLES_DIR)}
        scopes = lambda n: " ".join(c["scope"] for c in specs[n]["can_set"])
        self.assertIn("dor-testability", scopes("qa-derive"))
        self.assertIn("feasibility-and-size", scopes("developer"))
        self.assertEqual([c["value"] for c in specs["product-owner"]["can_set"]], ["READY_FOR_APPROVAL"])

    def test_no_role_exposes_privileged_tools(self):
        for spec in ga.load_roles(ROLES_DIR):
            for tool in spec["allowed_tools"]:
                self.assertNotIn(tool, {"mcp:adlc.update_status",
                                        "mcp:adlc.ingest_forge_event",
                                        "mcp:adlc.record_deployment"})


class MappingTest(unittest.TestCase):
    def test_tool_mapping(self):
        tools = ["read", "search", "write", "edit", "bash", "test-run", "mcp:adlc.query_evidence"]
        self.assertEqual(ga.map_tools(tools, "claude"),
                         ["Read", "Grep", "Glob", "Write", "Edit", "Bash", "mcp__adlc__query_evidence"])
        self.assertEqual(ga.map_tools(tools, "copilot"),
                         ["read", "search", "edit", "execute", "adlc/query_evidence"])

    def test_malformed_mcp_tool_rejected(self):
        with self.assertRaises(ga.RoleSpecError):
            ga.map_tools(["mcp:noserver"], "claude")

    def test_link_rewrite(self):
        out = ga.rewrite_links("[a](../../grounding/x.md) [b](https://e.com) [c](#h)", "developer")
        self.assertEqual(out, "[a](skills/grounding/x.md) [b](https://e.com) [c](#h)")


class ValidationTest(unittest.TestCase):
    def setUp(self):
        self.base = json.loads((ROLES_DIR / "code-reviewer" / "role.yaml").read_text(encoding="utf-8"))

    def _load(self, spec):
        with tempfile.TemporaryDirectory() as tmp:
            _write_role(Path(tmp), spec)
            return ga.load_roles(Path(tmp))

    def test_valid_spec_loads(self):
        self.assertEqual(len(self._load(self.base)), 1)

    def test_agent_cannot_set_verified(self):
        spec = copy.deepcopy(self.base)
        spec["can_set"] = [{"value": "VERIFIED", "scope": "x"}]
        with self.assertRaises(ga.RoleSpecError):
            self._load(spec)

    def test_never_set_must_include_story_states(self):
        spec = copy.deepcopy(self.base)
        spec["never_set"] = [v for v in spec["never_set"] if v != "ACCEPTED"]
        with self.assertRaises(ga.RoleSpecError):
            self._load(spec)

    def test_never_set_must_include_approved(self):
        spec = copy.deepcopy(self.base)
        spec["never_set"] = ["RELEASED"]
        with self.assertRaises(ga.RoleSpecError):
            self._load(spec)

    def test_deploy_operation_class_rejected(self):
        spec = copy.deepcopy(self.base)
        spec["operation_classes"] = ["READ", "DEPLOY"]
        with self.assertRaises(ga.RoleSpecError):
            self._load(spec)


class EntryPointTest(unittest.TestCase):
    def test_real_build_emits_adlc_entry_points(self):
        files = ga.build(ROLES_DIR)
        claude = files["claude/.claude/commands/adlc.md"]
        copilot = files["copilot/.github/prompts/adlc.prompt.md"]
        self.assertIn("$ARGUMENTS", claude)
        self.assertIn("argument-hint:", claude.split("---")[1])
        self.assertIn("${input:request", copilot)
        self.assertIn('agent: "agent"', copilot.split("---")[1])
        for text in (claude, copilot):
            self.assertIn("ADLC Conductor", text)
            # skills/ links are stripped to plain text in generated output
            self.assertNotIn("](skills/", text)
            self.assertNotIn("](../", text)

    def test_entry_points_follow_conductor_and_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            roles, wf, dist = root / "roles", root / "workflow", root / "dist"
            _write_role(roles, json.loads((ROLES_DIR / "code-reviewer" / "role.yaml").read_text(encoding="utf-8")))
            (wf / "adlc-conductor").mkdir(parents=True)
            (wf / "adlc-conductor" / "SKILL.md").write_text(
                "---\nname: adlc-conductor\ndescription: x\n---\n\n# ADLC Conductor\n\nSee [p](../stage-preflight/SKILL.md).\n",
                encoding="utf-8")
            self.assertEqual(ga.main(["--roles-dir", str(roles), "--dist", str(dist)]), 0)
            self.assertTrue((dist / "claude/.claude/commands/adlc.md").is_file())
            self.assertEqual(ga.main(["--roles-dir", str(roles), "--dist", str(dist), "--check"]), 0)
            (wf / "adlc-conductor" / "SKILL.md").write_text(
                "---\nname: adlc-conductor\ndescription: x\n---\n\n# ADLC Conductor v2\n", encoding="utf-8")
            self.assertIn("stale: copilot/.github/prompts/adlc.prompt.md", ga.check(ga.build(roles), dist))
            (wf / "adlc-conductor" / "SKILL.md").unlink()
            self.assertIn("orphaned: claude/.claude/commands/adlc.md", ga.check(ga.build(roles), dist))


class CheckModeTest(unittest.TestCase):
    def test_check_detects_stale_missing_and_orphaned(self):
        with tempfile.TemporaryDirectory() as tmp:
            roles, dist = Path(tmp) / "roles", Path(tmp) / "dist"
            base = json.loads((ROLES_DIR / "code-reviewer" / "role.yaml").read_text(encoding="utf-8"))
            _write_role(roles, base)
            self.assertEqual(ga.main(["--roles-dir", str(roles), "--dist", str(dist)]), 0)
            self.assertEqual(ga.main(["--roles-dir", str(roles), "--dist", str(dist), "--check"]), 0)

            (dist / "claude/.claude/agents/code-reviewer.md").write_text("edited", encoding="utf-8")
            (dist / "copilot/.github/agents/ghost.agent.md").write_text("x", encoding="utf-8")
            problems = ga.check(ga.build(roles), dist)
            self.assertIn("stale: claude/.claude/agents/code-reviewer.md", problems)
            self.assertIn("orphaned: copilot/.github/agents/ghost.agent.md", problems)
            self.assertEqual(ga.main(["--roles-dir", str(roles), "--dist", str(dist), "--check"]), 1)

            ga.main(["--roles-dir", str(roles), "--dist", str(dist)])
            self.assertFalse((dist / "copilot/.github/agents/ghost.agent.md").exists())
            self.assertEqual(ga.check(ga.build(roles), dist), [])


if __name__ == "__main__":
    unittest.main()
