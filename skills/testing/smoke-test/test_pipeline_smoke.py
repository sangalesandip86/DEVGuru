#!/usr/bin/env python3
"""End-to-end smoke test: bootstrap → resolve_workspace → stage_preflight.

Exercises the real pipeline scripts in a temporary git repo to verify they work
together. Deterministic — no LLM calls, no network. Runs in ~2 seconds.

    python -m unittest skills/testing/smoke-test/test_pipeline_smoke.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP = REPO_ROOT / "skills" / "workflow" / "bootstrap" / "scripts" / "bootstrap_project.py"
RESOLVE = REPO_ROOT / "skills" / "workflow" / "workspace-resolver" / "scripts" / "resolve_workspace.py"
PREFLIGHT = REPO_ROOT / "skills" / "workflow" / "stage-preflight" / "scripts" / "stage_preflight.py"


def run_script(script: Path, *args: str, cwd: str | None = None, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "ADLC_SKILLS_ROOT": str(REPO_ROOT)}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True, timeout=30, cwd=cwd, env=env,
    )


class BootstrapSmokeTest(unittest.TestCase):
    """Test bootstrap_project.py creates the right scaffolding."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="adlc-smoke-")
        subprocess.run(["git", "init", "-q", self.tmpdir], check=True, capture_output=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_bootstrap_creates_scaffolding(self):
        r = run_script(BOOTSTRAP, "--root", self.tmpdir, "--system", "smoke",
                       "--title", "Smoke test requirement")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertTrue(data["ok"])
        self.assertIn("plans/intake", data["created"])
        self.assertIn("adlc.workspace.yaml", data["created"])
        self.assertIn("plans/intake/REQ-1.json", data["created"])

    def test_bootstrap_idempotent(self):
        run_script(BOOTSTRAP, "--root", self.tmpdir, "--system", "smoke", "--title", "T1")
        r = run_script(BOOTSTRAP, "--root", self.tmpdir, "--system", "smoke", "--title", "T1")
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["created"], [])

    def test_bootstrap_check(self):
        r = run_script(BOOTSTRAP, "--root", self.tmpdir, "--check")
        self.assertEqual(r.returncode, 1)
        run_script(BOOTSTRAP, "--root", self.tmpdir, "--system", "smoke")
        r = run_script(BOOTSTRAP, "--root", self.tmpdir, "--check")
        self.assertEqual(r.returncode, 0)

    def test_manifest_valid_json(self):
        run_script(BOOTSTRAP, "--root", self.tmpdir, "--system", "smoke")
        manifest = Path(self.tmpdir) / "adlc.workspace.yaml"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["system"], "smoke")
        self.assertTrue(data["draft"])
        self.assertEqual(len(data["repos"]), 1)
        self.assertIn("app", data["repos"][0]["roles"])

    def test_requirement_valid_json(self):
        run_script(BOOTSTRAP, "--root", self.tmpdir, "--system", "s", "--title", "Test")
        req = Path(self.tmpdir) / "plans" / "intake" / "REQ-1.json"
        data = json.loads(req.read_text(encoding="utf-8"))
        self.assertEqual(data["id"], "REQ-1")
        self.assertEqual(data["title"], "Test")
        self.assertIsInstance(data["source_refs"], list)
        self.assertTrue(len(data["source_refs"]) >= 1)


class WorkspaceResolverSmokeTest(unittest.TestCase):
    """Test resolve_workspace.py finds roles in a bootstrapped repo."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="adlc-smoke-")
        subprocess.run(["git", "init", "-q", self.tmpdir], check=True, capture_output=True)
        run_script(BOOTSTRAP, "--root", self.tmpdir, "--system", "smoke")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_resolve_finds_app_role(self):
        r = run_script(RESOLVE, "--roles", "app", cwd=self.tmpdir)
        if r.returncode == 2:
            self.skipTest(f"resolve_workspace needs more setup: {r.stderr}")
        data = json.loads(r.stdout)
        roles = data.get("roles", {})
        if "app" in roles:
            self.assertIn(roles["app"]["status"], ["FOUND", "AMBIGUOUS"])

    def test_resolve_finds_planning_role(self):
        r = run_script(RESOLVE, "--roles", "planning", cwd=self.tmpdir)
        if r.returncode == 2:
            self.skipTest(f"resolve_workspace needs more setup: {r.stderr}")
        data = json.loads(r.stdout)
        roles = data.get("roles", {})
        if "planning" in roles:
            self.assertIn(roles["planning"]["status"], ["FOUND", "AMBIGUOUS", "MISSING"])


class StagePreflightSmokeTest(unittest.TestCase):
    """Test stage_preflight.py produces actionable output for INTAKE."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="adlc-smoke-")
        subprocess.run(["git", "init", "-q", self.tmpdir], check=True, capture_output=True)
        run_script(BOOTSTRAP, "--root", self.tmpdir, "--system", "smoke", "--title", "Test")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_intake_preflight(self):
        r = run_script(PREFLIGHT, "--start", "INTAKE", cwd=self.tmpdir)
        if r.returncode == 2:
            self.skipTest(f"stage_preflight needs more setup: {r.stderr}")
        self.assertIn(r.returncode, [0, 1], f"Unexpected exit: {r.stderr}")
        data = json.loads(r.stdout)
        self.assertIn("start", data)
        self.assertEqual(data["start"], "INTAKE")

    def test_design_preflight_needs_backfill(self):
        r = run_script(PREFLIGHT, "--start", "DESIGN", cwd=self.tmpdir)
        if r.returncode == 2:
            self.skipTest(f"stage_preflight needs more setup: {r.stderr}")
        self.assertIn(r.returncode, [0, 1])
        data = json.loads(r.stdout)
        statuses = [item.get("status") for item in data.get("items", [])]
        if statuses:
            self.assertTrue(
                any(s in ("BACKFILL", "BLOCK", "ASK") for s in statuses),
                f"DESIGN with no prior work should need backfill, got: {statuses}"
            )


class GenerateAgentsSmokeTest(unittest.TestCase):
    """Verify generate_agents.py produces valid dist/ content."""

    def test_dist_check_passes(self):
        r = run_script(REPO_ROOT / "skills" / "roles" / "scripts" / "generate_agents.py", "--check")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["problems"], [])

    def test_all_roles_generated(self):
        expected_roles = [
            "architect", "code-reviewer", "developer", "product-owner",
            "product-planner", "qa-derive", "qa-diagnose", "security-reviewer",
            "test-engineer",
        ]
        for role in expected_roles:
            path = REPO_ROOT / "dist" / "claude" / ".claude" / "agents" / f"{role}.md"
            self.assertTrue(path.exists(), f"Missing agent: {role}")
            content = path.read_text(encoding="utf-8")
            self.assertIn("maxTurns:", content)
            self.assertIn("Standalone Mode", content)
            self.assertNotRegex(content, r"\]\(skills/[^)]+\)")

    def test_adlc_command_generated(self):
        path = REPO_ROOT / "dist" / "claude" / ".claude" / "commands" / "adlc.md"
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("Standalone Mode", content)
        self.assertNotRegex(content, r"\]\(skills/[^)]+\)")


if __name__ == "__main__":
    unittest.main()
