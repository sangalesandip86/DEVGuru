#!/usr/bin/env python3
"""Resolve the repositories a workflow stage needs: find, ask, or create (plan v3.1 §4.14).

Search order (first match wins per role; ties within the best source → AMBIGUOUS):
  1. explicit   --repo ROLE=PATH (repeatable)
  2. manifest   adlc.workspace.yaml in the cwd or a parent directory
  3. current    the git repository containing the cwd
  4. siblings   git repositories next to the current one (same parent directory)
  5. references repo names cited in plans/ (repo@sha:path) or the manifest that are not present
               locally — reported as hints on MISSING roles

Every candidate repo is classified into roles heuristically (see reference/repo-role-heuristics.md).
Output per required role: FOUND (path, remote, HEAD sha) · AMBIGUOUS (ranked candidates) · MISSING.

The manifest is a MAP, not a permission grant: scope comes only from the Change Set and the agent's
role permissions (schemas/workspace-manifest.schema.json).

Creation:
  --init-local ROLE PATH    WORKSPACE_WRITE (agents may do this): git init + skeleton for the role +
                            draft adlc.workspace.yaml when none exists. Never writes control files
                            (AGENTS.md, CODEOWNERS, CI, .claude/…): those come only from repo-bootstrap.
  --request-remote ROLE     writes repo-request.yaml for a HUMAN or approved CI to execute
                            (EXTERNAL_MUTATION: agents never create remote repos).

    python resolve_workspace.py --stage IMPLEMENT
    python resolve_workspace.py --roles app,planning --repo planning=../acme-plans
    python resolve_workspace.py --init-local planning ../acme-plans --system acme
    python resolve_workspace.py --request-remote app --name payments-svc --org acme \\
        --owner-team payments --codeowners @acme/payments --requested-by agent:architect \\
        --justification "service-map entry svc-payments needs its own repo" --out repo-request.yaml

Exit codes: 0 all required roles FOUND · 1 some AMBIGUOUS/MISSING · 2 bad input / refused.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import workflow_lib as wl  # noqa: E402

MANIFEST = "adlc.workspace.yaml"
SOURCE_RANK = {"explicit": 0, "manifest": 1, "current": 2, "sibling": 3}
APP_MANIFESTS = ["package.json", "pyproject.toml", "setup.py", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod",
                 "Cargo.toml", "pubspec.yaml", "Gemfile", "composer.json", "mix.exs"]
CODE_DIRS = ["src", "app", "lib", "pkg", "cmd", "internal", "services", "web"]
SKELETONS = {
    "app": ["src/.gitkeep", "tests/.gitkeep", "README.md"],
    "planning": ["plans/requirements/.gitkeep", "plans/epics/.gitkeep", "plans/stories/.gitkeep",
                 "plans/milestones/.gitkeep", "plans/test-designs/.gitkeep", "plans/intake/.gitkeep",
                 "architecture/adr/.gitkeep", "README.md"],
    "tests": ["tests/.gitkeep", "README.md"],
    "contracts": ["contracts/.gitkeep", "README.md"],
    "infra": ["infra/.gitkeep", "README.md"],
}
REF_RE = re.compile(r"\b([A-Za-z0-9._-]+)@([0-9a-f]{7,40}|WORKTREE):[^\s'\"]+")


class ResolveError(Exception):
    pass


# --------------------------------------------------------------------------- classification

def _any(root: Path, patterns: list[str], limit: int = 4000) -> bool:
    n = 0
    for pat in patterns:
        for _ in root.glob(pat):
            return True
        n += 1
        if n > limit:
            break
    return False


def classify(repo: Path) -> dict:
    """Return {role: score} for a repo directory. Higher score = stronger signal."""
    scores: dict[str, int] = {}
    has_manifest = any((repo / m).exists() for m in APP_MANIFESTS) or _any(repo, ["*.csproj", "*.sln"])
    has_code = any((repo / d).is_dir() for d in CODE_DIRS)
    if (repo / "plans").is_dir():
        scores["planning"] = 3 if not (has_manifest or has_code) else 2
    if (repo / "architecture").is_dir() and "planning" not in scores:
        scores["planning"] = 1
    if _any(repo, ["openapi*.y*ml", "openapi*.json", "*/openapi*.y*ml", "asyncapi*.y*ml", "pacts/*",
                   "contracts/*", "proto/*.proto", "*.proto"]):
        scores["contracts"] = 3 if not has_code else 1
    if _any(repo, ["*.tf", "*/*.tf", "Chart.yaml", "*/Chart.yaml", "helm/*", "k8s/*", "Pulumi.yaml", "kustomization.yaml"]):
        scores["infra"] = 3 if not has_code else 1
    tests_only = (_any(repo, ["e2e/*", "tests/*", "test/*", "features/*", "playwright.config.*", "cypress.config.*"])
                  and not has_code)
    if tests_only and "planning" not in scores and "contracts" not in scores and "infra" not in scores:
        scores["tests"] = 2
    if has_code or (has_manifest and not tests_only):
        scores["app"] = 3 if has_code else 2
    if not scores:
        scores["app"] = 1  # unknown repo: weakest app signal (never silently treated as planning)
    return scores


# --------------------------------------------------------------------------- discovery

def find_manifest(start: Path, max_up: int = 4) -> Path | None:
    cur = start.resolve()
    for _ in range(max_up + 1):
        p = cur / MANIFEST
        if p.is_file():
            return p
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def load_manifest(path: Path) -> dict:
    data = wl.load_yaml(path)
    errs = wl.validate(data, wl.load_schema("workspace-manifest"))
    if errs:
        raise ResolveError(f"{path}: invalid manifest: {errs[:5]}")
    return data


def current_repo(cwd: Path) -> Path | None:
    top = wl.git_toplevel(cwd)
    if top:
        return top
    cur = cwd.resolve()
    while True:
        if wl.is_git_repo(cur):
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def sibling_repos(repo: Path | None, cwd: Path) -> list[Path]:
    parent = repo.parent if repo else cwd.resolve()
    out = []
    try:
        for d in sorted(parent.iterdir()):
            if d.is_dir() and d != repo and wl.is_git_repo(d):
                out.append(d.resolve())
    except OSError:
        pass
    return out


def referenced_repo_names(paths: list[Path]) -> set[str]:
    names: set[str] = set()
    for root in paths:
        plans = root / "plans"
        if not plans.is_dir():
            continue
        for f in plans.rglob("*.y*ml"):
            try:
                names |= {m.group(1) for m in REF_RE.finditer(f.read_text(encoding="utf-8", errors="replace"))}
            except OSError:
                continue
    return names


def gather(cwd: Path, explicit: dict[str, str], manifest_path: Path | None) -> tuple[list[dict], dict | None]:
    cands: list[dict] = []
    for role, p in explicit.items():
        path = Path(p).resolve()
        cands.append({"path": path, "source": "explicit", "roles": {role: 9}, "exists": path.exists()})
    manifest = None
    if manifest_path:
        manifest = load_manifest(manifest_path)
        for r in manifest["repos"]:
            path = (manifest_path.parent / r["path"]).resolve() if r.get("path") else None
            cands.append({"path": path, "source": "manifest", "roles": {ro: 8 for ro in r["roles"]},
                          "exists": bool(path and path.exists()), "name": r["name"], "url": r.get("url")})
    cur = current_repo(cwd)
    if cur:
        cands.append({"path": cur, "source": "current", "roles": classify(cur), "exists": True})
    for sib in sibling_repos(cur, cwd):
        cands.append({"path": sib, "source": "sibling", "roles": classify(sib), "exists": True})
    # de-duplicate by path, keeping the best source
    seen: dict[str, dict] = {}
    for c in cands:
        key = str(c["path"]) if c["path"] else f"url:{c.get('url') or c.get('name')}"
        if key not in seen or SOURCE_RANK[c["source"]] < SOURCE_RANK[seen[key]["source"]]:
            if key in seen:
                c["roles"] = {**seen[key]["roles"], **c["roles"]}
            seen[key] = c
    return list(seen.values()), manifest


def resolve(required: list[str], cwd: Path, explicit: dict[str, str] | None = None,
            optional: list[str] | None = None) -> dict:
    explicit = explicit or {}
    manifest_path = find_manifest(cwd)
    cands, manifest = gather(cwd, explicit, manifest_path)
    roles_out: dict[str, dict] = {}
    single_app = None
    for role in list(dict.fromkeys((required or []) + (optional or []))):
        matches = [c for c in cands if role in c["roles"]]
        matches.sort(key=lambda c: (SOURCE_RANK[c["source"]], -c["roles"][role], str(c["path"])))
        entry: dict
        if not matches:
            entry = {"status": "MISSING"}
        else:
            best = matches[0]
            rivals = [m for m in matches[1:] if SOURCE_RANK[m["source"]] == SOURCE_RANK[best["source"]]
                      and m["roles"][role] == best["roles"][role]]
            if rivals:
                entry = {"status": "AMBIGUOUS", "candidates": [_describe(m, role) for m in [best, *rivals]]}
            elif not best["exists"]:
                entry = {"status": "MISSING", "hint": f"manifest lists {best.get('name')} "
                                                      f"({best.get('url') or best.get('path')}) but it is not present locally"}
            else:
                entry = {"status": "FOUND", **_describe(best, role)}
        roles_out[role] = entry
        if role == "app" and entry["status"] == "FOUND":
            single_app = entry
    # Single-repo default (§4.14): planning lives in plans/ inside the app repo.
    if "planning" in roles_out and roles_out["planning"]["status"] == "MISSING" and single_app:
        roles_out["planning"] = {**{k: v for k, v in single_app.items() if k != "role_score"},
                                 "status": "FOUND", "single_repo_default": True,
                                 "plans_dir_exists": (Path(single_app["path"]) / "plans").is_dir(),
                                 "note": "single-repo default: plans/ inside the app repo"}
    refs = referenced_repo_names([Path(c["path"]) for c in cands if c.get("path") and c["exists"]])
    local_names = {Path(c["path"]).name for c in cands if c.get("path") and c["exists"]}
    unresolved_refs = sorted(refs - local_names)
    for role, e in roles_out.items():
        if e["status"] == "MISSING":
            e["options"] = ["point to an existing path (--repo ROLE=PATH)",
                            f"create locally (--init-local {role} PATH)",
                            f"request a remote repo (--request-remote {role} …) for a human/CI to create"]
            if unresolved_refs:
                e["referenced_but_absent"] = unresolved_refs
    need = set(required or [])
    ok = all(roles_out[r]["status"] == "FOUND" for r in need)
    return {"ok": ok, "cwd": str(cwd.resolve()), "manifest": str(manifest_path) if manifest_path else None,
            "system": manifest.get("system") if manifest else None, "roles": roles_out,
            "required": sorted(need), "note": "The manifest is a map, not a permission grant."}


def _describe(c: dict, role: str) -> dict:
    d = {"source": c["source"], "role_score": c["roles"][role]}
    if c.get("path") and c["exists"]:
        d.update(wl.repo_info(Path(c["path"])))
    else:
        d.update({"path": str(c["path"]) if c.get("path") else None, "name": c.get("name"), "remote": c.get("url")})
    return d


# --------------------------------------------------------------------------- creation

def _assert_not_control(rel: str, globs: list[str]) -> None:
    hit = wl.path_matches(rel, globs)
    if hit:
        raise ResolveError(f"refusing to write control file {rel!r} (matches {hit!r}); "
                           "control files come only from templates/repo-bootstrap via a human/CI")


def init_local(role: str, path: Path, system: str | None, cwd: Path) -> dict:
    if role not in SKELETONS:
        raise ResolveError(f"unknown role {role!r}; expected one of {wl.REPO_ROLES}")
    path = path.resolve()
    if path.exists() and any(path.iterdir()):
        if wl.is_git_repo(path):
            raise ResolveError(f"{path} is already a git repository; point to it with --repo {role}={path}")
        raise ResolveError(f"{path} exists and is not empty; refusing to initialise over existing files")
    globs = wl.control_file_globs()
    files = list(SKELETONS[role])
    existing_manifest = find_manifest(cwd)
    if not existing_manifest:
        files.append(MANIFEST)
    for rel in files:
        _assert_not_control(rel, globs)
    path.mkdir(parents=True, exist_ok=True)
    for rel in files:
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        if rel == "README.md":
            f.write_text(f"# {path.name}\n\nRepository role: `{role}`. Created locally by the ADLC workspace resolver.\n"
                         "Platform control files (AGENTS.md, CLAUDE.md, CODEOWNERS, CI) are NOT created here; they are\n"
                         "shipped by `templates/repo-bootstrap` when a human or approved CI creates the remote repo.\n",
                         encoding="utf-8")
        elif rel == MANIFEST:
            manifest = {"version": 1, "system": system or path.name, "draft": True,
                        "repos": [{"name": path.name, "roles": [role], "path": "."}],
                        "notes": "Draft created by resolve_workspace.py --init-local. A map, not a permission grant; "
                                 "review and complete via PR."}
            f.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        else:
            f.write_text("", encoding="utf-8")
    git_ok = wl.git(["init", "-q"], path) is not None
    result = {"ok": True, "created": str(path), "role": role, "files": files, "git_initialised": git_ok,
              "operation_class": "WORKSPACE_WRITE"}
    if existing_manifest:
        result["manifest_proposal"] = {
            "file": str(existing_manifest),
            "add_repo": {"name": path.name, "roles": [role],
                         "path": _relpath(path, existing_manifest.parent)},
            "note": "Propose this entry in a PR; the manifest is not edited automatically.",
        }
    if not git_ok:
        result["warning"] = "git not available or init failed; directory skeleton created without a repository"
    return result


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        import os
        return Path(os.path.relpath(path, base)).as_posix()


def request_remote(role: str, args) -> dict:
    req = {
        "version": 1, "org": args.org, "name": args.name, "system": args.system or args.name,
        "description": args.description or f"{role} repository for {args.system or args.name}",
        "owner_team": args.owner_team, "visibility": args.visibility, "roles": [role], "template": "repo-bootstrap",
        "default_branch": args.default_branch,
        "branch_protection": {"required_reviews": 1, "require_codeowners": True,
                              "required_checks": ["adlc-control-file-policy", "dependency-decision-check"],
                              "dismiss_stale_reviews": True},
        "codeowners_owner": args.codeowners, "requested_by": args.requested_by,
        "justification": args.justification,
    }
    if args.source_ref:
        req["source_refs"] = [{"ref": args.source_ref, "trust_level": "REPOSITORY"}]
    errs = wl.validate(req, wl.load_schema("repo-request"))
    if errs:
        raise ResolveError(f"repo request invalid: {errs}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(req, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "written": str(out), "operation_class": "EXTERNAL_MUTATION (requested, not performed)",
            "next": "A human or approved CI runs: python skills/workflow/repo-bootstrap/scripts/create_repo_from_request.py "
                    f"{out} --target <dir>"}


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cwd", default=".", help="directory to resolve from (default: current)")
    ap.add_argument("--stage", help="read required/optional repo roles for this stage from stages.yaml")
    ap.add_argument("--roles", help="comma-separated required roles (overrides --stage required)")
    ap.add_argument("--repo", action="append", default=[], metavar="ROLE=PATH", help="explicit repo for a role")
    ap.add_argument("--init-local", nargs=2, metavar=("ROLE", "PATH"))
    ap.add_argument("--system", help="system name for a new draft manifest / request")
    ap.add_argument("--request-remote", metavar="ROLE")
    ap.add_argument("--name")
    ap.add_argument("--org")
    ap.add_argument("--owner-team")
    ap.add_argument("--codeowners", help="CODEOWNERS owner, e.g. @acme/payments")
    ap.add_argument("--visibility", default="private", choices=["private", "internal", "public"])
    ap.add_argument("--default-branch", default="main")
    ap.add_argument("--description")
    ap.add_argument("--requested-by", default="agent:unknown")
    ap.add_argument("--justification")
    ap.add_argument("--source-ref", help="e.g. planning-repo@sha:architecture/service-map.yaml")
    ap.add_argument("--out", default="repo-request.yaml")
    args = ap.parse_args(argv)
    cwd = Path(args.cwd)
    try:
        if args.init_local:
            res = init_local(args.init_local[0], Path(args.init_local[1]), args.system, cwd)
            print(wl.dump(res))
            return 0
        if args.request_remote:
            missing = [f for f in ("name", "org", "owner_team", "codeowners", "justification") if not getattr(args, f)]
            if missing:
                raise ResolveError(f"--request-remote needs --{', --'.join(m.replace('_', '-') for m in missing)}")
            print(wl.dump(request_remote(args.request_remote, args)))
            return 0
        explicit = {}
        for item in args.repo:
            role, _, p = item.partition("=")
            if role not in wl.REPO_ROLES or not p:
                raise ResolveError(f"--repo expects ROLE=PATH with ROLE in {wl.REPO_ROLES}, got {item!r}")
            explicit[role] = p
        required, optional = [], []
        if args.stage:
            stages = wl.load_stages()
            if args.stage not in stages["stages"]:
                raise ResolveError(f"unknown stage {args.stage!r}")
            rr = stages["stages"][args.stage]["repo_roles"]
            required, optional = list(rr["required"]), list(rr["optional"])
        if args.roles:
            required = [r.strip() for r in args.roles.split(",") if r.strip()]
            bad = set(required) - set(wl.REPO_ROLES)
            if bad:
                raise ResolveError(f"unknown roles {sorted(bad)}")
        if not required and not optional:
            required = ["app"]
        res = resolve(required, cwd, explicit, optional)
    except (ResolveError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    print(wl.dump(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
