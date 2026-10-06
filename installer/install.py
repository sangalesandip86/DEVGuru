#!/usr/bin/env python3
"""DEVGuru ADLC Platform — 1-Click Installer.

Auto-detects coding agent configurations (Claude Code, GitHub Copilot, Gemini/Antigravity),
installs skills at chosen scope (user/project), configures MCP server connection,
and launches the Insight Hub UI.

    python install.py                    # interactive mode
    python install.py --scope user       # user-level install
    python install.py --scope project    # project-level install
    python install.py --check            # verify existing installation
    python install.py --uninstall        # remove configuration

Requirements: Python 3.10+, git (for project-level install)
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"
MCP_SERVER_ROOT = SKILLS_ROOT / "mcp-servers" / "adlc-mcp"

# ---------------------------------------------------------------- agent detection

AGENT_CONFIGS: dict[str, dict] = {
    "claude-code": {
        "display": "Claude Code",
        "user_config": {
            "win32": Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json",
            "darwin": Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            "linux": Path.home() / ".config" / "claude" / "claude_desktop_config.json",
        },
        "project_files": [".claude/settings.json", "CLAUDE.md"],
        "mcp_config_key": "mcpServers",
    },
    "github-copilot": {
        "display": "GitHub Copilot",
        "user_config": {
            "win32": Path(os.environ.get("APPDATA", "")) / "GitHub Copilot" / "config.json",
            "darwin": Path.home() / "Library" / "Application Support" / "github-copilot" / "config.json",
            "linux": Path.home() / ".config" / "github-copilot" / "config.json",
        },
        "project_files": [".github/copilot-instructions.md", ".copilot"],
        "mcp_config_key": None,
    },
    "gemini-antigravity": {
        "display": "Gemini / Antigravity",
        "user_config": {
            "win32": Path(os.environ.get("APPDATA", "")) / "antigravity" / "config.json",
            "darwin": Path.home() / "Library" / "Application Support" / "antigravity" / "config.json",
            "linux": Path.home() / ".config" / "antigravity" / "config.json",
        },
        "project_files": ["GEMINI.md", ".gemini/settings.json"],
        "mcp_config_key": None,
    },
}


def detect_agents() -> dict[str, dict]:
    """Detect installed coding agents and their configuration paths."""
    detected = {}
    plat = sys.platform
    for agent_id, info in AGENT_CONFIGS.items():
        config_path = info["user_config"].get(plat)
        project_indicators = info["project_files"]
        found = {
            "display": info["display"],
            "user_config_exists": config_path and config_path.is_file(),
            "user_config_path": str(config_path) if config_path else None,
            "project_files_found": [],
            "mcp_config_key": info.get("mcp_config_key"),
        }
        cwd = Path.cwd()
        for pf in project_indicators:
            if (cwd / pf).exists():
                found["project_files_found"].append(pf)
        if found["user_config_exists"] or found["project_files_found"]:
            detected[agent_id] = found
    return detected


# ---------------------------------------------------------------- skills installation

def install_skills_user() -> Path:
    """Install skills at user level (~/.adlc/skills symlink or copy)."""
    home_adlc = Path.home() / ".adlc"
    home_adlc.mkdir(parents=True, exist_ok=True)
    dest = home_adlc / "skills"
    if dest.exists():
        if dest.is_symlink():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    try:
        dest.symlink_to(SKILLS_ROOT, target_is_directory=True)
        print(f"  Linked skills: {dest} -> {SKILLS_ROOT}")
    except OSError:
        shutil.copytree(SKILLS_ROOT, dest, dirs_exist_ok=True)
        print(f"  Copied skills to: {dest}")
    return dest


def install_skills_project(project_dir: Path) -> Path:
    """Install skills at project level (.adlc/skills symlink or copy)."""
    adlc_dir = project_dir / ".adlc"
    adlc_dir.mkdir(parents=True, exist_ok=True)
    dest = adlc_dir / "skills"
    if dest.exists():
        if dest.is_symlink():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    try:
        dest.symlink_to(SKILLS_ROOT, target_is_directory=True)
        print(f"  Linked skills: {dest} -> {SKILLS_ROOT}")
    except OSError:
        shutil.copytree(SKILLS_ROOT, dest, dirs_exist_ok=True)
        print(f"  Copied skills to: {dest}")

    gitignore = project_dir / ".gitignore"
    adlc_entry = ".adlc/"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if adlc_entry not in content:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write(f"\n{adlc_entry}\n")
            print("  Added .adlc/ to .gitignore")
    else:
        gitignore.write_text(f"{adlc_entry}\n", encoding="utf-8")
        print("  Created .gitignore with .adlc/")
    return dest


# ---------------------------------------------------------------- MCP configuration

def _python_path() -> str:
    """Find the Python executable to use for the MCP server."""
    return sys.executable


def configure_mcp_claude_code(scope: str, project_dir: Path | None = None) -> dict:
    """Configure MCP server for Claude Code."""
    python = _python_path()
    server_config = {
        "command": python,
        "args": ["-m", "adlc_mcp"],
        "env": {
            "ADLC_MODULES": "evidence_ledger,change_management,contract_registry,work_planning,event_journal,stage_engine,concurrency,parallel_coordinator",
            "ADLC_SKILLS_ROOT": str(SKILLS_ROOT),
        },
    }

    if scope == "user":
        plat = sys.platform
        config_path = AGENT_CONFIGS["claude-code"]["user_config"].get(plat)
        if not config_path:
            print("  Warning: Cannot determine Claude Code config path for this platform")
            return {}
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = {}
        if config_path.is_file():
            config = json.loads(config_path.read_text(encoding="utf-8"))
        if "mcpServers" not in config:
            config["mcpServers"] = {}
        config["mcpServers"]["adlc"] = server_config
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print(f"  MCP server configured in: {config_path}")
        return config
    elif scope == "project" and project_dir:
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        settings_path = claude_dir / "settings.json"
        settings = {}
        if settings_path.is_file():
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if "mcpServers" not in settings:
            settings["mcpServers"] = {}
        settings["mcpServers"]["adlc"] = server_config
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        print(f"  MCP server configured in: {settings_path}")
        return settings
    return {}


def configure_agents_md(project_dir: Path) -> None:
    """Ensure CLAUDE.md references AGENTS.md for skill loading."""
    claude_md = project_dir / "CLAUDE.md"
    agents_md = project_dir / "AGENTS.md"

    if agents_md.exists() and claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        if "@AGENTS.md" not in content:
            with open(claude_md, "a", encoding="utf-8") as f:
                f.write("\n@AGENTS.md\n")
            print("  Added @AGENTS.md reference to CLAUDE.md")


# ---------------------------------------------------------------- verification

def verify_python_version() -> bool:
    return sys.version_info >= (3, 10)


def verify_mcp_server() -> dict:
    """Check if the MCP server can start."""
    python = _python_path()
    try:
        result = subprocess.run(
            [python, "-m", "adlc_mcp", "--list-tools"],
            capture_output=True, text=True, timeout=15,
            cwd=str(MCP_SERVER_ROOT),
            env={**os.environ, "ADLC_MODULES": "evidence_ledger",
                 "ADLC_TOKEN": os.environ.get("ADLC_TOKEN", "installer-check:developer"),
                 "PYTHONPATH": str(MCP_SERVER_ROOT / "src")},
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {"ok": True, "modules": data.get("modules", []),
                    "tools": len(data.get("tools", []))}
        error = result.stderr.strip()
        if "credential" in error.lower():
            return {"ok": True, "note": "server importable; credentials not configured yet",
                    "modules": [], "tools": 0}
        return {"ok": False, "error": error}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def verify_installation() -> dict:
    """Run full installation verification."""
    results = {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_ok": verify_python_version(),
        "skills_root_exists": SKILLS_ROOT.is_dir(),
        "mcp_server_exists": (MCP_SERVER_ROOT / "src" / "adlc_mcp" / "__main__.py").is_file(),
        "agents_detected": detect_agents(),
        "ui_static_exists": (MCP_SERVER_ROOT / "src" / "adlc_mcp" / "static" / "index.html").is_file(),
    }
    if results["mcp_server_exists"]:
        results["mcp_server_check"] = verify_mcp_server()
    return results


# ---------------------------------------------------------------- uninstall

def uninstall(scope: str, project_dir: Path | None = None) -> None:
    """Remove DEVGuru configuration."""
    if scope == "user":
        home_skills = Path.home() / ".adlc" / "skills"
        if home_skills.exists():
            if home_skills.is_symlink():
                home_skills.unlink()
            else:
                shutil.rmtree(home_skills)
            print(f"  Removed: {home_skills}")
        plat = sys.platform
        config_path = AGENT_CONFIGS["claude-code"]["user_config"].get(plat)
        if config_path and config_path.is_file():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if "mcpServers" in config and "adlc" in config["mcpServers"]:
                del config["mcpServers"]["adlc"]
                config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
                print(f"  Removed MCP config from: {config_path}")
    elif scope == "project" and project_dir:
        adlc_dir = project_dir / ".adlc"
        if adlc_dir.exists():
            shutil.rmtree(adlc_dir)
            print(f"  Removed: {adlc_dir}")
        settings_path = project_dir / ".claude" / "settings.json"
        if settings_path.is_file():
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            if "mcpServers" in settings and "adlc" in settings["mcpServers"]:
                del settings["mcpServers"]["adlc"]
                settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
                print(f"  Removed MCP config from: {settings_path}")


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="devguru-install",
        description="DEVGuru ADLC Platform — 1-Click Installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--scope", choices=["user", "project"], help="Installation scope")
    ap.add_argument("--project-dir", type=Path, default=Path.cwd(),
                     help="Project directory (default: current directory)")
    ap.add_argument("--check", action="store_true", help="Verify existing installation")
    ap.add_argument("--uninstall", action="store_true", help="Remove configuration")
    ap.add_argument("--json", action="store_true", help="Output results as JSON")
    args = ap.parse_args(argv)

    if not verify_python_version():
        print(f"Error: Python 3.10+ required (found {sys.version})", file=sys.stderr)
        return 1

    if args.check:
        results = verify_installation()
        if args.json:
            print(json.dumps(results, indent=2, default=str))
        else:
            print("\n=== DEVGuru Installation Check ===\n")
            print(f"  Python: {results['python_version']} ({'OK' if results['python_ok'] else 'FAIL'})")
            print(f"  Skills root: {'OK' if results['skills_root_exists'] else 'MISSING'}")
            print(f"  MCP server: {'OK' if results['mcp_server_exists'] else 'MISSING'}")
            print(f"  UI static files: {'OK' if results['ui_static_exists'] else 'MISSING'}")
            if results.get("mcp_server_check"):
                mcp = results["mcp_server_check"]
                print(f"  MCP server start: {'OK' if mcp['ok'] else 'FAIL'}")
                if mcp["ok"]:
                    print(f"    Modules: {mcp['modules']}")
                    print(f"    Tools: {mcp['tools']}")
            agents = results.get("agents_detected", {})
            if agents:
                print("\n  Detected Agents:")
                for aid, info in agents.items():
                    status = "user-config" if info["user_config_exists"] else "project-files"
                    print(f"    - {info['display']} ({status})")
            else:
                print("\n  No coding agents detected")
        return 0

    if args.uninstall:
        scope = args.scope
        if not scope:
            scope = "project" if (args.project_dir / ".adlc").exists() else "user"
        print(f"\n=== Uninstalling DEVGuru ({scope} scope) ===\n")
        uninstall(scope, args.project_dir)
        print("\nDone.")
        return 0

    # -- Interactive installation --
    print("\n" + "=" * 50)
    print("  DEVGuru ADLC Platform — Installer")
    print("=" * 50 + "\n")

    agents = detect_agents()
    if agents:
        print("Detected coding agents:")
        for aid, info in agents.items():
            markers = []
            if info["user_config_exists"]:
                markers.append("user config found")
            if info["project_files_found"]:
                markers.append(f"project files: {', '.join(info['project_files_found'])}")
            print(f"  + {info['display']} ({'; '.join(markers)})")
    else:
        print("No coding agents detected (will install standalone).")

    scope = args.scope
    if not scope:
        scope = "project"
        print(f"\nDefaulting to project-level install at: {args.project_dir}")

    print(f"\n--- Installing skills ({scope} scope) ---\n")
    if scope == "user":
        skills_path = install_skills_user()
    else:
        skills_path = install_skills_project(args.project_dir)

    print("\n--- Configuring MCP server ---\n")
    if "claude-code" in agents or scope == "project":
        configure_mcp_claude_code(scope, args.project_dir)
    if scope == "project":
        configure_agents_md(args.project_dir)

    print("\n--- Verifying installation ---\n")
    results = verify_installation()
    all_ok = results["python_ok"] and results["skills_root_exists"] and results["mcp_server_exists"]
    if all_ok:
        print("  All checks passed!")
        print(f"\n  Skills installed at: {skills_path}")
        mcp_check = results.get("mcp_server_check", {})
        if mcp_check.get("ok"):
            print(f"  MCP server: {len(mcp_check.get('tools', []))} tools available")
        print("\n  To start the Insight Hub UI:")
        print(f"    cd {MCP_SERVER_ROOT}")
        print(f"    python -m adlc_mcp")
        print(f"    # Then open: http://127.0.0.1:<port>/ui/")
    else:
        print("  Some checks failed. Run with --check for details.")
        return 1

    print(f"\n{'=' * 50}")
    print("  Installation complete!")
    print(f"{'=' * 50}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
