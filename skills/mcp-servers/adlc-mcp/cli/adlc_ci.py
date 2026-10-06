#!/usr/bin/env python3
"""CI command discovery for ADLC projects.

Reads .adlc/catalog/ci-commands.json if present, otherwise scans for
common CI config files and reports discovered commands.

Usage:
    python adlc_ci.py
    python adlc_ci.py --root /path/to/project
    python adlc_ci.py --pretty
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCAN_FILES = {
    "Makefile": "make",
    "package.json": "npm/yarn",
    "pyproject.toml": "python",
    "Cargo.toml": "cargo",
    "go.mod": "go",
    "Gemfile": "bundler",
    ".github/workflows": "github-actions",
    ".gitlab-ci.yml": "gitlab-ci",
    "Jenkinsfile": "jenkins",
}


def _scan_makefile(path: Path) -> list[dict]:
    targets = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line and not line.startswith(("\t", " ", "#", ".")) and ":" in line:
                name = line.split(":")[0].strip()
                if name and not name.startswith("."):
                    targets.append({"command": f"make {name}", "source": "Makefile"})
    except OSError:
        pass
    return targets[:20]


def _scan_package_json(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        return [{"command": f"npm run {k}", "source": "package.json"} for k in scripts]
    except (OSError, json.JSONDecodeError):
        return []


def _scan_pyproject(path: Path) -> list[dict]:
    commands = []
    try:
        text = path.read_text(encoding="utf-8")
        if "[tool.pytest" in text:
            commands.append({"command": "pytest", "source": "pyproject.toml"})
        if "[tool.ruff" in text:
            commands.append({"command": "ruff check .", "source": "pyproject.toml"})
        if "[tool.mypy" in text:
            commands.append({"command": "mypy .", "source": "pyproject.toml"})
    except OSError:
        pass
    return commands


def discover(root: str) -> dict:
    root_path = Path(root)
    catalog = root_path / ".adlc" / "catalog" / "ci-commands.json"
    if catalog.is_file():
        try:
            data = json.loads(catalog.read_text(encoding="utf-8"))
            return {"source": "catalog", "commands": data}
        except (OSError, json.JSONDecodeError):
            pass

    found: list[dict] = []
    detected: list[str] = []
    for filename, tool in SCAN_FILES.items():
        target = root_path / filename
        if target.exists():
            detected.append(tool)
            if filename == "Makefile":
                found.extend(_scan_makefile(target))
            elif filename == "package.json":
                found.extend(_scan_package_json(target))
            elif filename == "pyproject.toml":
                found.extend(_scan_pyproject(target))

    return {"source": "scan", "detected_tools": detected, "commands": found}


def main() -> None:
    parser = argparse.ArgumentParser(description="ADLC CI command discovery")
    parser.add_argument("--root", default=".", help="Project root directory")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    args = parser.parse_args()

    data = discover(args.root)
    if args.pretty:
        print(f"Source: {data['source']}")
        if data.get("detected_tools"):
            print(f"Detected: {', '.join(data['detected_tools'])}")
        print(f"\nCommands ({len(data['commands'])}):")
        for cmd in data["commands"]:
            print(f"  {cmd['command']:40s} [{cmd.get('source', '')}]")
        if not data["commands"]:
            print("  (none found)")
    else:
        json.dump(data, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
