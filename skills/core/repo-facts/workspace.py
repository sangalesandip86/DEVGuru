#!/usr/bin/env python3
"""Detect monorepo workspace structure and enumerate packages (finding G1/G2).

Supported workspace types:
  npm/yarn/pnpm  — package.json workspaces field, pnpm-workspace.yaml
  Cargo          — Cargo.toml [workspace] members
  Go             — go.work use directives
  Dart/Flutter   — melos.yaml packages globs
  Gradle         — settings.gradle include directives
  Maven          — pom.xml <modules>
  .NET           — *.sln Project references

Usage:
    python workspace.py <repo_root> [--stdout] [--out DIR]

Writes <repo_root>/.adlc/catalog/workspace.json by default.
Exit codes: 0 = produced, 2 = bad input.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path


def _read(p: Path, limit: int = 500_000) -> str:
    try:
        return p.read_bytes()[:limit].decode("utf-8", errors="replace")
    except OSError:
        return ""


def _glob_packages(root: Path, patterns: list[str]) -> list[dict]:
    pkgs: list[dict] = []
    seen: set[str] = set()
    for pattern in patterns:
        pattern = pattern.rstrip("/")
        for d in sorted(root.glob(pattern)):
            if d.is_dir():
                rel = d.relative_to(root).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    pkgs.append({"name": d.name, "path": rel, "manifest": ""})
    return pkgs


def _detect_npm(root: Path) -> dict | None:
    pkg_json = root / "package.json"
    pnpm_ws = root / "pnpm-workspace.yaml"

    patterns: list[str] = []

    if pkg_json.is_file():
        try:
            data = json.loads(_read(pkg_json))
        except json.JSONDecodeError:
            data = {}
        ws = data.get("workspaces")
        if isinstance(ws, list):
            patterns = ws
        elif isinstance(ws, dict) and isinstance(ws.get("packages"), list):
            patterns = ws["packages"]

    if not patterns and pnpm_ws.is_file():
        text = _read(pnpm_ws)
        for line in text.splitlines():
            m = re.match(r"""^\s*-\s+['"]?([^'"#]+?)['"]?\s*$""", line)
            if m:
                patterns.append(m.group(1).strip())

    if not patterns:
        return None

    pkgs: list[dict] = []
    seen: set[str] = set()
    for pattern in patterns:
        pattern = pattern.rstrip("/")
        if "*" in pattern or "?" in pattern:
            for d in sorted(root.glob(pattern)):
                if d.is_dir() and (d / "package.json").is_file():
                    rel = d.relative_to(root).as_posix()
                    if rel not in seen:
                        seen.add(rel)
                        pkgs.append({"name": d.name, "path": rel,
                                     "manifest": f"{rel}/package.json"})
        else:
            d = root / pattern
            if d.is_dir() and (d / "package.json").is_file():
                rel = d.relative_to(root).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    pkgs.append({"name": d.name, "path": rel,
                                 "manifest": f"{rel}/package.json"})

    return {"workspace_type": "npm", "packages": pkgs} if pkgs or patterns else None


def _detect_cargo(root: Path) -> dict | None:
    cargo = root / "Cargo.toml"
    if not cargo.is_file():
        return None
    text = _read(cargo)
    if "[workspace]" not in text:
        return None
    members: list[str] = []
    in_members = False
    for line in text.splitlines():
        if re.match(r"^\s*members\s*=\s*\[", line):
            in_members = True
            for m in re.findall(r'"([^"]+)"', line):
                members.append(m)
            if "]" in line:
                in_members = False
            continue
        if in_members:
            for m in re.findall(r'"([^"]+)"', line):
                members.append(m)
            if "]" in line:
                in_members = False

    if not members:
        return None

    pkgs: list[dict] = []
    seen: set[str] = set()
    for pattern in members:
        if "*" in pattern or "?" in pattern:
            for d in sorted(root.glob(pattern)):
                if d.is_dir() and (d / "Cargo.toml").is_file():
                    rel = d.relative_to(root).as_posix()
                    if rel not in seen:
                        seen.add(rel)
                        pkgs.append({"name": d.name, "path": rel,
                                     "manifest": f"{rel}/Cargo.toml"})
        else:
            d = root / pattern
            if d.is_dir() and (d / "Cargo.toml").is_file():
                rel = d.relative_to(root).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    pkgs.append({"name": d.name, "path": rel,
                                 "manifest": f"{rel}/Cargo.toml"})

    return {"workspace_type": "cargo", "packages": pkgs}


def _detect_go(root: Path) -> dict | None:
    gowork = root / "go.work"
    if not gowork.is_file():
        return None
    text = _read(gowork)
    dirs: list[str] = []
    in_use = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("use ("):
            in_use = True
            continue
        if stripped == "use" and not in_use:
            in_use = True
            continue
        if in_use:
            if stripped == ")":
                in_use = False
                continue
            m = re.match(r"^\s*(\./[^\s]+|[^\s)]+)", stripped)
            if m:
                dirs.append(m.group(1).lstrip("./"))
        elif stripped.startswith("use "):
            d = stripped[4:].strip().lstrip("./")
            if d:
                dirs.append(d)

    pkgs: list[dict] = []
    for d in dirs:
        p = root / d
        if p.is_dir() and (p / "go.mod").is_file():
            rel = p.relative_to(root).as_posix()
            pkgs.append({"name": p.name, "path": rel, "manifest": f"{rel}/go.mod"})

    return {"workspace_type": "go", "packages": pkgs} if dirs else None


def _detect_dart(root: Path) -> dict | None:
    melos = root / "melos.yaml"
    if not melos.is_file():
        return None
    text = _read(melos)
    patterns: list[str] = []
    in_packages = False
    for line in text.splitlines():
        if re.match(r"^packages:\s*$", line):
            in_packages = True
            continue
        if in_packages:
            if line and not line.startswith(" "):
                break
            m = re.match(r"""^\s*-\s+['"]?([^'"#]+?)['"]?\s*$""", line)
            if m:
                patterns.append(m.group(1).strip())

    if not patterns:
        return None

    pkgs: list[dict] = []
    seen: set[str] = set()
    for pattern in patterns:
        pattern = pattern.rstrip("/")
        if "*" in pattern or "?" in pattern:
            for d in sorted(root.glob(pattern)):
                if d.is_dir() and (d / "pubspec.yaml").is_file():
                    rel = d.relative_to(root).as_posix()
                    if rel not in seen:
                        seen.add(rel)
                        pkgs.append({"name": d.name, "path": rel,
                                     "manifest": f"{rel}/pubspec.yaml"})
        else:
            d = root / pattern
            if d.is_dir() and (d / "pubspec.yaml").is_file():
                rel = d.relative_to(root).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    pkgs.append({"name": d.name, "path": rel,
                                 "manifest": f"{rel}/pubspec.yaml"})

    return {"workspace_type": "dart", "packages": pkgs}


def _detect_gradle(root: Path) -> dict | None:
    for name in ("settings.gradle.kts", "settings.gradle"):
        settings = root / name
        if settings.is_file():
            break
    else:
        return None

    text = _read(settings)
    includes: list[str] = []
    for m in re.finditer(r"""include\s*\(\s*["']([^"']+)["']""", text):
        includes.append(m.group(1))
    for m in re.finditer(r"""include\s+['"]([^'"]+)['"]""", text):
        includes.append(m.group(1))

    if not includes:
        return None

    pkgs: list[dict] = []
    seen: set[str] = set()
    for inc in includes:
        path = inc.lstrip(":").replace(":", "/")
        d = root / path
        if d.is_dir():
            rel = d.relative_to(root).as_posix()
            if rel not in seen:
                seen.add(rel)
                manifest = ""
                for gf in ("build.gradle.kts", "build.gradle"):
                    if (d / gf).is_file():
                        manifest = f"{rel}/{gf}"
                        break
                pkgs.append({"name": d.name, "path": rel, "manifest": manifest})

    return {"workspace_type": "gradle", "packages": pkgs}


def _detect_maven(root: Path) -> dict | None:
    pom = root / "pom.xml"
    if not pom.is_file():
        return None
    text = _read(pom)
    modules = re.findall(r"<module>\s*([^<\s]+)\s*</module>", text)
    if not modules:
        return None

    pkgs: list[dict] = []
    for mod in modules:
        d = root / mod
        if d.is_dir() and (d / "pom.xml").is_file():
            rel = d.relative_to(root).as_posix()
            pkgs.append({"name": d.name, "path": rel, "manifest": f"{rel}/pom.xml"})

    return {"workspace_type": "maven", "packages": pkgs}


def _detect_dotnet(root: Path) -> dict | None:
    sln_files = sorted(root.glob("*.sln"))
    if not sln_files:
        return None
    text = _read(sln_files[0])
    csproj_re = re.compile(r'Project\([^)]+\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+\.csproj)"')
    pkgs: list[dict] = []
    seen: set[str] = set()
    for m in csproj_re.finditer(text):
        name = m.group(1)
        csproj_rel = m.group(2).replace("\\", "/")
        d = (root / csproj_rel).parent
        if d.is_dir():
            rel = d.relative_to(root).as_posix()
            if rel not in seen:
                seen.add(rel)
                pkgs.append({"name": name, "path": rel, "manifest": csproj_rel})

    return {"workspace_type": "dotnet", "packages": pkgs} if pkgs else None


DETECTORS = [
    _detect_npm, _detect_cargo, _detect_go, _detect_dart,
    _detect_gradle, _detect_maven, _detect_dotnet,
]


def detect_workspace(root: Path) -> dict:
    for detector in DETECTORS:
        result = detector(root)
        if result is not None:
            return {
                "classification": "FACT",
                "source": "workspace.py",
                "workspace_type": result["workspace_type"],
                "root": root.name,
                "packages": result["packages"],
            }
    return {
        "classification": "FACT",
        "source": "workspace.py",
        "workspace_type": "none",
        "root": root.name,
        "packages": [],
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo_root")
    ap.add_argument("--out", help="output directory (default: <repo_root>/.adlc/catalog)")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}), file=sys.stderr)
        return 2
    result = detect_workspace(root)
    if args.stdout:
        print(json.dumps(result, indent=2))
        return 0
    out = Path(args.out) if args.out else root / ".adlc" / "catalog"
    out.mkdir(parents=True, exist_ok=True)
    (out / "workspace.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"workspace": str(out / "workspace.json"),
                      "workspace_type": result["workspace_type"],
                      "packages": len(result["packages"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
