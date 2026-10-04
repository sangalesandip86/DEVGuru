"""Shared helpers for the /workflow scripts (plan v3.1 §4.14).

Stdlib only. Reuses the planning gates' YAML-subset loader and JSON-Schema subset validator
(skills/enforcement/ci-checks/planning-gates/) instead of duplicating them.

Path resolution: all paths are resolved from ADLC_SKILLS_ROOT (env var) when set,
falling back to the directory structure relative to this file's location. This allows
the platform scripts to run from any project directory, not just the DEVGuru repo.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

def _resolve_skills_root() -> Path:
    """Resolve the skills tree root from ADLC_SKILLS_ROOT or by walking up from this file."""
    env = os.environ.get("ADLC_SKILLS_ROOT")
    if env:
        root = Path(env).resolve()
        skills = root / "skills"
        if skills.is_dir():
            return skills
        if (root / "workflow").is_dir():
            return root
    return HERE.parent.parent

SKILLS = _resolve_skills_root()
REPO_ROOT = SKILLS.parent
WORKFLOW = SKILLS / "workflow"
PLANNING_GATES = SKILLS / "enforcement" / "ci-checks" / "planning-gates"
SCHEMAS = WORKFLOW / "schemas"
STAGES_FILE = WORKFLOW / "stages.yaml"
CONTROL_FILE_PATHS = SKILLS / "governance" / "default-permissions" / "reference" / "control-file-paths.json"

if str(PLANNING_GATES) not in sys.path:
    sys.path.insert(0, str(PLANNING_GATES))

import minyaml  # noqa: E402

STAGES = ["INTAKE", "ARCHITECTURE", "PLAN", "DESIGN", "IMPLEMENT", "TEST", "REVIEW",
          "INTEGRATE", "RELEASE", "LEARN"]
TIERS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
REPO_ROLES = ["app", "planning", "tests", "contracts", "infra"]

# Embedded fallback, used only if the canonical control-file list is unavailable.
_FALLBACK_CONTROL_GLOBS = [
    ".claude/**", ".github/agents/**", ".github/skills/**", ".github/instructions/**",
    ".github/hooks/**", ".github/workflows/**", ".github/rulesets/**", ".github/CODEOWNERS",
    ".github/copilot-instructions.md", "CODEOWNERS", "docs/CODEOWNERS", ".mcp.json", "**/.mcp.json",
    "AGENTS.md", "**/AGENTS.md", "CLAUDE.md", "**/CLAUDE.md", "CLAUDE.local.md", "**/CLAUDE.local.md",
]


def load_yaml(path: Path) -> Any:
    return minyaml.load(path)


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_stages(path: Path | None = None) -> dict:
    return load_yaml(path or STAGES_FILE)


def load_schema(name: str) -> dict:
    return load_json(SCHEMAS / f"{name}.schema.json")


def validate(instance: Any, schema: dict) -> list[str]:
    """JSON-Schema subset validation shared with the planning gates."""
    import planning_lib  # local import: heavy module, only needed here
    return planning_lib.validate(instance, schema)


def tier_index(tier: str | None) -> int:
    return TIERS.index(tier) if tier in TIERS else TIERS.index("HIGH")  # unknown → HIGH (fail-safe)


def tier_at_least(tier: str | None, floor: str) -> bool:
    return tier_index(tier) >= TIERS.index(floor)


# --------------------------------------------------------------------------- globs / control files

def glob_to_regex(glob: str) -> re.Pattern:
    """Translate a repo-relative glob with '**' (any depth, incl. zero dirs) into a regex."""
    i, out = 0, []
    while i < len(glob):
        c = glob[i]
        if glob.startswith("**/", i):
            out.append(r"(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(r".*")
            i += 2
        elif c == "*":
            out.append(r"[^/]*")
            i += 1
        elif c == "?":
            out.append(r"[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def path_matches(rel_path: str, globs: list[str]) -> str | None:
    rel = rel_path.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    for g in globs:
        if glob_to_regex(g).match(rel) or fnmatch.fnmatch(rel, g):
            return g
    return None


def control_file_globs() -> list[str]:
    try:
        data = load_json(CONTROL_FILE_PATHS)
        globs: list[str] = []
        for items in data.get("categories", {}).values():
            globs.extend(items)
        # skills/** and dist/** protect the PLATFORM repo; a product repo created from a template
        # has no skills/ tree of its own, so they are irrelevant (and harmless) here.
        return globs or list(_FALLBACK_CONTROL_GLOBS)
    except (OSError, ValueError):
        return list(_FALLBACK_CONTROL_GLOBS)


# --------------------------------------------------------------------------- git (local only)

def git_available() -> bool:
    return shutil.which("git") is not None


def git(args: list[str], cwd: Path) -> str | None:
    if not git_available():
        return None
    try:
        res = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def git_toplevel(path: Path) -> Path | None:
    out = git(["rev-parse", "--show-toplevel"], path)
    return Path(out).resolve() if out else None


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def repo_info(path: Path) -> dict:
    info = {"path": str(path.resolve()), "name": path.resolve().name}
    head = git(["rev-parse", "HEAD"], path)
    info["head_sha"] = head
    info["branch"] = git(["rev-parse", "--abbrev-ref", "HEAD"], path) if head else None
    info["remote"] = git(["config", "--get", "remote.origin.url"], path)
    status = git(["status", "--porcelain"], path)
    info["dirty"] = bool(status) if status is not None else None
    return info


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False)
