"""Tests for enforcement hooks and CI checks. Run:
    python -m unittest discover -s skills/enforcement/tests -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENF / "lib"))
sys.path.insert(0, str(ENF / "hooks" / "control-file-guard"))
sys.path.insert(0, str(ENF / "hooks" / "fact-writer-hooks"))
sys.path.insert(0, str(ENF / "ci-checks" / "control-file-policy-check"))
sys.path.insert(0, str(ENF / "managed-settings"))

import adlc_enforcement as ae  # noqa: E402
import check_agents_md_shim  # noqa: E402
import check_control_file_policy  # noqa: E402
import control_file_guard  # noqa: E402
import fact_writer  # noqa: E402
import generate_deny_list  # noqa: E402

GLOBS = ae.load_control_globs()
GUARD = ENF / "hooks" / "control-file-guard" / "control_file_guard.py"


def claude(tool: str, tool_input: dict, cwd: str = "/repo") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
            "session_id": "s1", "cwd": cwd}


def copilot(tool: str, args: dict, cwd: str = "/repo") -> dict:
    return {"toolName": tool, "toolArgs": json.dumps(args), "cwd": cwd}


class GlobTests(unittest.TestCase):
    def test_matches(self):
        for path in [".claude/settings.json", "AGENTS.md", "svc/api/AGENTS.md", "CLAUDE.md",
                     ".github/workflows/ci.yml", "CODEOWNERS", ".github/CODEOWNERS", ".mcp.json",
                     "skills/core/evidence-ledger/SKILL.md", ".github/agents/dev.agent.md",
                     ".github/hooks/hooks.json"]:
            self.assertIsNotNone(ae.match_control_path(path, GLOBS), path)

    def test_non_matches(self):
        for path in ["src/app.py", "README.md", "docs/guide.md", "src/skills_util.py",
                     "tests/test_agents.py", ".github/ISSUE_TEMPLATE/bug.md"]:
            self.assertIsNone(ae.match_control_path(path, GLOBS), path)

    def test_absolute_inside_and_outside_repo(self):
        root = os.path.abspath("repo-root")
        self.assertIsNotNone(ae.match_control_path(os.path.join(root, ".claude", "x.json"), GLOBS, root))
        self.assertIsNone(ae.match_control_path(os.path.join(root, "src", "skills", "a.py"), GLOBS, root))
        # Outside the repo: suffix match still protects user-level config.
        self.assertIsNotNone(ae.match_control_path("~/.claude/settings.json", GLOBS, root))

    def test_windows_separators(self):
        self.assertIsNotNone(ae.match_control_path(r".github\workflows\ci.yml", GLOBS))


class GuardTests(unittest.TestCase):
    def eval(self, payload):
        ev = ae.parse_event(payload)
        return control_file_guard.evaluate(ev, GLOBS, ev.cwd)

    def test_claude_write_denied(self):
        self.assertIsNotNone(self.eval(claude("Write", {"file_path": ".claude/settings.json"})))
        self.assertIsNotNone(self.eval(claude("Edit", {"file_path": "CODEOWNERS"})))
        self.assertIsNotNone(self.eval(claude("NotebookEdit", {"notebook_path": "skills/x.ipynb"})))
        self.assertIsNotNone(self.eval(claude("MultiEdit", {"file_path": "svc/AGENTS.md", "edits": []})))

    def test_claude_normal_write_allowed(self):
        self.assertIsNone(self.eval(claude("Write", {"file_path": "src/main.py"})))

    def test_read_never_blocked(self):
        self.assertIsNone(self.eval(claude("Read", {"file_path": ".claude/settings.json"})))

    def test_copilot_shape(self):
        self.assertIsNotNone(self.eval(copilot("edit", {"path": ".github/workflows/ci.yml"})))
        self.assertIsNone(self.eval(copilot("edit", {"path": "src/a.ts"})))
        self.assertIsNotNone(self.eval(copilot("create", {"path": ".github/agents/x.agent.md"})))

    def test_bash_writes_denied(self):
        for cmd in ["echo '{}' > .claude/settings.json",
                    "cat x | tee AGENTS.md",
                    "sed -i 's/a/b/' .github/workflows/ci.yml",
                    "cp /tmp/evil.json .mcp.json",
                    "rm -rf .claude/hooks",
                    "git checkout -- CODEOWNERS",
                    "python -c \"open('.claude/settings.local.json','w').write('{}')\""]:
            self.assertIsNotNone(self.eval(claude("Bash", {"command": cmd})), cmd)

    def test_powershell_write_denied(self):
        self.assertIsNotNone(self.eval(claude("PowerShell", {"command": "Set-Content -Path CLAUDE.md -Value x"})))

    def test_bash_reads_allowed(self):
        for cmd in ["cat .claude/settings.json", "git status", "ls .github/workflows",
                    "grep -r foo skills/", "echo hi > out.txt", "cat AGENTS.md > /tmp/out.txt",
                    "git checkout main"]:
            self.assertIsNone(self.eval(claude("Bash", {"command": cmd})), cmd)

    def test_deny_payload_shapes(self):
        c = control_file_guard.deny_payload(ae.parse_event(claude("Write", {})), "r")
        self.assertEqual(c["hookSpecificOutput"]["permissionDecision"], "deny")
        p = control_file_guard.deny_payload(ae.parse_event(copilot("edit", {})), "r")
        self.assertEqual(p["permissionDecision"], "deny")

    def run_hook(self, stdin: str, cwd: str):
        return subprocess.run([sys.executable, str(GUARD)], input=stdin, capture_output=True,
                              text=True, cwd=cwd, env={**os.environ, "CLAUDE_PROJECT_DIR": cwd})

    def test_subprocess_deny_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            out = self.run_hook(json.dumps(claude("Write", {"file_path": "CLAUDE.md"}, cwd=d)), d)
            self.assertEqual(out.returncode, 0)
            self.assertEqual(json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertTrue((Path(d) / ".adlc" / "control-file-guard.log").exists())
            ok = self.run_hook(json.dumps(claude("Write", {"file_path": "src/a.py"}, cwd=d)), d)
            self.assertEqual((ok.returncode, ok.stdout), (0, ""))
            bad = self.run_hook("{not json", d)
            self.assertEqual(bad.returncode, 2)


class FactWriterTests(unittest.TestCase):
    def test_read_and_bash_entries(self):
        ev = ae.parse_event({"hook_event_name": "PostToolUse", "tool_name": "Read",
                             "tool_input": {"file_path": "src/a.py"}, "tool_response": "print(1)",
                             "session_id": "run-1", "cwd": "."})
        e = fact_writer.build_entry(ev)
        self.assertEqual((e["source_type"], e["source"], e["run_id"], e["tool"]),
                         ("file_read", "src/a.py", "run-1", "claude-code"))
        self.assertNotIn("trust_level", e)  # never caller-supplied
        ev = ae.parse_event({"toolName": "bash", "toolArgs": json.dumps({"command": "pytest"}),
                             "toolResult": {"textResultForLlm": "3 passed"}, "cwd": "."})
        e = fact_writer.build_entry(ev)
        self.assertEqual((e["source_type"], e["tool"]), ("command_output", "copilot"))
        self.assertIn("3 passed", e["content"])

    def test_writes_not_facts(self):
        ev = ae.parse_event(claude("Write", {"file_path": "a.py"}))
        self.assertIsNone(fact_writer.build_entry(ev))

    def test_fail_open_when_cli_missing(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "ADLC_LEDGER_CLI": str(Path(d) / "missing.py"), "CLAUDE_PROJECT_DIR": d}
            payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                       "tool_input": {"command": "ls"}, "tool_response": "a", "cwd": d}
            out = subprocess.run([sys.executable, str(ENF / "hooks" / "fact-writer-hooks" / "fact_writer.py")],
                                 input=json.dumps(payload), capture_output=True, text=True, env=env)
            self.assertEqual(out.returncode, 0)
            self.assertIn("ledger CLI not found", (Path(d) / ".adlc" / "hook-errors.log").read_text())


class PolicyCheckTests(unittest.TestCase):
    def test_generated_template_passes(self):
        self.assertEqual(check_control_file_policy.check(generate_deny_list.build(), GLOBS), [])

    def test_missing_rule_and_bad_allow_fail(self):
        s = generate_deny_list.build()
        s["permissions"]["deny"].remove("Edit(.mcp.json)")
        s["permissions"]["allow"] = ["Edit(.claude/**)", "Edit(src/**)"]
        s["allowManagedHooksOnly"] = False
        problems = check_control_file_policy.check(s, GLOBS)
        self.assertIn("missing deny rule Edit(.mcp.json)", problems)
        self.assertIn("allowManagedHooksOnly is not true", problems)
        self.assertIn("allow rule re-allows a control path: Edit(.claude/**)", problems)
        self.assertFalse(any("src/**" in p for p in problems))

    def test_committed_template_is_current(self):
        rendered = json.dumps(generate_deny_list.build(), indent=2) + "\n"
        self.assertEqual(generate_deny_list.TEMPLATE.read_text(encoding="utf-8"), rendered)


class ShimCheckTests(unittest.TestCase):
    def test_shim(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "svc").mkdir()
            (root / "AGENTS.md").write_text("# root")
            (root / "CLAUDE.md").write_text("@AGENTS.md\n")
            self.assertEqual(check_agents_md_shim.check(root), [])
            (root / "svc" / "AGENTS.md").write_text("# svc")
            self.assertEqual(len(check_agents_md_shim.check(root)), 1)
            (root / "svc" / "CLAUDE.md").write_text("# other\n")
            self.assertIn("does not import", check_agents_md_shim.check(root)[0])
            (root / "svc" / "CLAUDE.md").write_text("@AGENTS.md\nextra\n")
            self.assertEqual(check_agents_md_shim.check(root), [])
            self.assertEqual(len(check_agents_md_shim.check(root, strict=True)), 1)


if __name__ == "__main__":
    unittest.main()
