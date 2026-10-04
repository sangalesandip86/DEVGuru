#!/usr/bin/env python3
"""Create a repository from a reviewed repo-request.yaml (plan v3.1 §4.14, ADR 0004).

Creating a remote repository is EXTERNAL_MUTATION. Agents never do it. This script:

  default (any caller)   validate the request; list the files the template would render and
                         print the exact commands a human/CI must run. Writes nothing.
  ADLC_ACTOR=human|ci    additionally RENDER templates/repo-bootstrap into --target. The template
                         contains control files (AGENTS.md, CODEOWNERS, CI), which only a human or
                         CI may produce.
  --execute              additionally RUN the git / gh commands (network). Requires ADLC_ACTOR=human|ci,
                         a rendered target, and no unfilled @<…> owner placeholders.

ADLC_ACTOR is a safety interlock, not a security boundary. The real controls are: agent sessions
hold no org-admin token, managed settings deny agents control-file writes, and the
control-file-guard hook (skills/enforcement/hooks/control-file-guard).

    python create_repo_from_request.py repo-request.yaml --target ../payments-svc            # plan only
    ADLC_ACTOR=human python create_repo_from_request.py repo-request.yaml --target ../payments-svc
    ADLC_ACTOR=ci python create_repo_from_request.py repo-request.yaml --target out/ --execute \\
        --platform-repo acme/adlc-platform --platform-sha 3f9c2ab…

Exit codes: 0 ok · 2 invalid request / refused · 3 a command failed during --execute.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "lib"))
import workflow_lib as wl  # noqa: E402

TEMPLATE = wl.REPO_ROOT / "templates" / "repo-bootstrap"
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")  # no spaces: leaves GitHub's ${{ expr }} alone
ALLOWED_ACTORS = {"human", "ci"}
UNFILLED = {"tech_lead_owner": "@<tech-lead-team>", "platform_owner": "@<platform-team>"}


class BootstrapError(Exception):
    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


def load_request(path: Path) -> dict:
    if not path.is_file():
        raise BootstrapError(f"{path}: not a file")
    req = wl.load_yaml(path)
    errs = wl.validate(req, wl.load_schema("repo-request"))
    if errs:
        raise BootstrapError(f"invalid repo request: {errs}")
    return req


def values(req: dict, platform_repo: str, platform_sha: str) -> dict:
    v = {k: req.get(k, "") for k in ("org", "name", "owner_team", "default_branch", "codeowners_owner")}
    v["system"] = req.get("system") or req["name"]
    v["description"] = req.get("description") or f"{req['name']} ({', '.join(req['roles'])})"
    v["tech_lead_owner"] = req.get("tech_lead_owner") or UNFILLED["tech_lead_owner"]
    v["platform_owner"] = req.get("platform_owner") or UNFILLED["platform_owner"]
    v["roles_json"] = json.dumps(req["roles"])
    v["platform_repo"] = platform_repo
    v["platform_sha"] = platform_sha
    return v


def render_text(text: str, vals: dict) -> tuple[str, set[str]]:
    unknown: set[str] = set()

    def sub(m):
        key = m.group(1)
        if key not in vals:
            unknown.add(key)
            return m.group(0)
        return str(vals[key])
    return PLACEHOLDER.sub(sub, text), unknown


def template_files(template: Path) -> list[Path]:
    return sorted(p for p in template.rglob("*") if p.is_file())


def plan_render(template: Path, vals: dict) -> tuple[dict[str, str], set[str]]:
    files, unknown = {}, set()
    for p in template_files(template):
        rel = p.relative_to(template).as_posix()
        text, u = render_text(p.read_text(encoding="utf-8"), vals)
        files[rel] = text
        unknown |= u
    return files, unknown


def protection(req: dict) -> dict:
    bp = req["branch_protection"]
    return {
        "required_status_checks": {"strict": True, "contexts": bp["required_checks"]},
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "required_approving_review_count": bp["required_reviews"],
            "require_code_owner_reviews": True,
            "dismiss_stale_reviews": bp.get("dismiss_stale_reviews", True),
        },
        "restrictions": None,
    }


def commands(req: dict, target: Path) -> list[list[str]]:
    full = f"{req['org']}/{req['name']}"
    t = str(target)
    return [
        ["git", "-C", t, "init", "-b", req["default_branch"]],
        ["git", "-C", t, "add", "-A"],
        ["git", "-C", t, "commit", "-m", "chore: bootstrap from ADLC templates/repo-bootstrap"],
        ["gh", "repo", "create", full, f"--{req['visibility']}", "--description",
         req.get("description") or req["name"], "--source", t, "--remote", "origin", "--push"],
        ["gh", "api", "-X", "PUT", f"repos/{full}/branches/{req['default_branch']}/protection",
         "--input", str(target / ".adlc" / "branch-protection.json")],
    ]


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("request", help="repo-request.yaml")
    ap.add_argument("--target", required=True, help="directory to render the new repository into")
    ap.add_argument("--platform-repo", default="YOUR-ORG/adlc-platform")
    ap.add_argument("--platform-sha", default="PINNED_PLATFORM_RELEASE_SHA")
    ap.add_argument("--execute", action="store_true", help="run git/gh (network); human/CI only")
    ap.add_argument("--template", default=str(TEMPLATE))
    args = ap.parse_args(argv)
    actor = os.environ.get("ADLC_ACTOR", "").strip().lower()
    target = Path(args.target).resolve()
    try:
        req = load_request(Path(args.request))
        vals = values(req, args.platform_repo, args.platform_sha)
        files, unknown = plan_render(Path(args.template), vals)
        if unknown:
            raise BootstrapError(f"template uses unknown placeholders: {sorted(unknown)}")
        unfilled = [k for k, ph in UNFILLED.items() if vals[k] == ph]
        cmds = commands(req, target)
        result = {
            "ok": True, "request": req["name"], "actor": actor or None, "target": str(target),
            "files": sorted(files), "unfilled_owner_placeholders": unfilled,
            "commands": [" ".join(shlex.quote(c) for c in cmd) for cmd in cmds],
            "rendered": False, "executed": False,
        }
        if actor not in ALLOWED_ACTORS:
            if args.execute:
                raise BootstrapError("--execute requires ADLC_ACTOR=human or ADLC_ACTOR=ci; agents never create "
                                     "remote repositories (EXTERNAL_MUTATION)")
            result["note"] = ("Plan only. A human or approved CI sets ADLC_ACTOR=human|ci to render the template "
                              "(it contains control files) and runs the commands above.")
            print(wl.dump(result))
            return 0
        if target.exists() and any(target.iterdir()):
            raise BootstrapError(f"{target} exists and is not empty")
        for rel, text in files.items():
            p = target / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        bp = target / ".adlc" / "branch-protection.json"
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_text(json.dumps(protection(req), indent=2) + "\n", encoding="utf-8")
        result["rendered"] = True
        if args.execute:
            if unfilled:
                raise BootstrapError(f"fill the CODEOWNERS owners first ({unfilled}): set them in the request")
            if "PINNED_PLATFORM_RELEASE_SHA" in args.platform_sha or "YOUR-ORG" in args.platform_repo:
                raise BootstrapError("--execute needs real --platform-repo and --platform-sha (never 'latest')")
            for cmd in cmds:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0:
                    raise BootstrapError(f"command failed: {' '.join(cmd)}: {res.stderr.strip()[:500]}", code=3)
            result["executed"] = True
        print(wl.dump(result))
        return 0
    except BootstrapError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
