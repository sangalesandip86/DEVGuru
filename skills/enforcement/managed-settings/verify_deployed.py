#!/usr/bin/env python3
"""Verify that deployed managed settings match the template.

Reads the OS managed-settings path and diffs against the template. Intended to run
as a SessionStart hook writing a FACT (finding A6: drift between template and
deployment is invisible without this check).

Usage:
    python verify_deployed.py [--template PATH] [--deployed PATH]
    python verify_deployed.py --check  # exit 1 if drift detected

OS managed-settings paths (Claude Code):
  macOS:  /Library/Application Support/claude-code/managed-settings.json
  Linux:  /etc/claude-code/managed-settings.json
  Windows: C:\\ProgramData\\claude-code\\managed-settings.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

TEMPLATE = Path(__file__).parent / "templates" / "claude-code-managed-settings.json"

REQUIRED_KEYS = {
    "permissions.deny",
    "permissions.disableBypassPermissionsMode",
    "allowManagedHooksOnly",
    "allowManagedPermissionRulesOnly",
    "allowManagedMcpServersOnly",
    "strictKnownMarketplaces",
    "disableSkillShellExecution",
}


def os_settings_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path("/Library/Application Support/claude-code/managed-settings.json")
    elif system == "Linux":
        return Path("/etc/claude-code/managed-settings.json")
    else:
        return Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "claude-code" / "managed-settings.json"


def _get_nested(data: dict, dotted: str):
    parts = dotted.split(".")
    cur = data
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def verify(template_path: Path, deployed_path: Path) -> dict:
    result = {"ok": True, "template": str(template_path), "deployed": str(deployed_path), "findings": []}

    if not template_path.exists():
        result["ok"] = False
        result["findings"].append({"severity": "ERROR", "message": f"template not found: {template_path}"})
        return result

    if not deployed_path.exists():
        result["ok"] = False
        result["findings"].append({
            "severity": "ERROR",
            "message": f"managed settings not deployed at {deployed_path}",
        })
        return result

    try:
        template = json.loads(template_path.read_text(encoding="utf-8"))
        deployed = json.loads(deployed_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result["ok"] = False
        result["findings"].append({"severity": "ERROR", "message": str(exc)})
        return result

    for key in REQUIRED_KEYS:
        tmpl_val = _get_nested(template, key)
        depl_val = _get_nested(deployed, key)
        if tmpl_val is None:
            continue
        if depl_val is None:
            result["ok"] = False
            result["findings"].append({
                "severity": "CRITICAL",
                "key": key,
                "message": f"key {key!r} present in template but missing in deployed settings (silently ignored)",
            })
        elif depl_val != tmpl_val:
            result["ok"] = False
            result["findings"].append({
                "severity": "HIGH",
                "key": key,
                "message": f"key {key!r} differs: template={tmpl_val!r}, deployed={depl_val!r}",
            })

    tmpl_denies = set(_get_nested(template, "permissions.deny") or [])
    depl_denies = set(_get_nested(deployed, "permissions.deny") or [])
    missing_denies = sorted(tmpl_denies - depl_denies)
    if missing_denies:
        result["ok"] = False
        result["findings"].append({
            "severity": "HIGH",
            "key": "permissions.deny",
            "message": f"{len(missing_denies)} deny rules in template but not deployed",
            "missing": missing_denies[:10],
        })

    return result


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", default=str(TEMPLATE))
    ap.add_argument("--deployed", default=None)
    ap.add_argument("--check", action="store_true", help="exit 1 if drift detected")
    args = ap.parse_args(argv)

    deployed = Path(args.deployed) if args.deployed else os_settings_path()
    result = verify(Path(args.template), deployed)
    print(json.dumps(result, indent=2))
    if args.check:
        return 0 if result["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
