#!/usr/bin/env python3
"""One-command ADLC platform installer.

Sets up credentials, MCP config, agent specs, and environment for Claude Code.

Usage:
    python scripts/setup_adlc.py                    # interactive setup
    python scripts/setup_adlc.py --scope user       # user-level install (default)
    python scripts/setup_adlc.py --scope project    # project-level install
    python scripts/setup_adlc.py --check            # verify existing installation
    python scripts/setup_adlc.py --skip-credentials # skip credential issuance
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

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_CLAUDE = REPO_ROOT / "dist" / "claude"
CREDENTIAL_SCRIPT = REPO_ROOT / "skills" / "mcp-servers" / "adlc-mcp" / "scripts" / "adlc_credentials.py"
MCP_SRC = REPO_ROOT / "skills" / "mcp-servers" / "adlc-mcp" / "src"

AGENT_ROLES = [
    "architect", "code-reviewer", "developer", "product-owner",
    "product-planner", "qa-derive", "qa-diagnose", "security-reviewer",
    "test-engineer",
]

TOKEN_ENV_NAMES = {
    "developer": "ADLC_DEVELOPER_TOKEN",
    "architect": "ADLC_ARCHITECT_TOKEN",
    "code-reviewer": "ADLC_CODE_REVIEWER_TOKEN",
    "security-reviewer": "ADLC_SECURITY_REVIEWER_TOKEN",
    "test-engineer": "ADLC_TEST_ENGINEER_TOKEN",
    "product-planner": "ADLC_PRODUCT_PLANNER_TOKEN",
    "product-owner": "ADLC_PRODUCT_OWNER_TOKEN",
    "qa-derive": "ADLC_QA_DERIVE_TOKEN",
    "qa-diagnose": "ADLC_QA_DIAGNOSE_TOKEN",
}


def info(msg: str) -> None:
    print(f"  [OK] {msg}")


def warn(msg: str) -> None:
    print(f"  [!!] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}", file=sys.stderr)


def heading(msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def check_python() -> bool:
    v = sys.version_info
    if v < (3, 10):
        fail(f"Python 3.10+ required, got {v.major}.{v.minor}.{v.micro}")
        return False
    info(f"Python {v.major}.{v.minor}.{v.micro}")
    return True


def check_mcp_importable() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import adlc_mcp; print('OK')"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "PYTHONPATH": str(MCP_SRC)},
        )
        if result.returncode == 0 and "OK" in result.stdout:
            info("adlc_mcp importable")
            return True
    except Exception:
        pass
    fail("adlc_mcp not importable — check PYTHONPATH or pip install")
    return False


def check_dist_generated() -> bool:
    agents_dir = DIST_CLAUDE / ".claude" / "agents"
    if not agents_dir.is_dir():
        fail(f"dist/ not generated — run: python skills/roles/scripts/generate_agents.py")
        return False
    count = len(list(agents_dir.glob("*.md")))
    if count < len(AGENT_ROLES):
        warn(f"Only {count} agent specs in dist/ (expected {len(AGENT_ROLES)})")
        return False
    info(f"{count} agent specs in dist/")
    return True


def issue_credentials() -> dict[str, str]:
    """Issue credentials for all agent roles. Returns {role: token}."""
    tokens: dict[str, str] = {}
    for role in AGENT_ROLES:
        actor_id = f"agent:{role}"
        cmd = [
            sys.executable, str(CREDENTIAL_SCRIPT),
            "issue",
            "--actor-type", "AGENT",
            "--actor-id", actor_id,
            "--agent-role", role,
            "--tool", "claude-code",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                env={**os.environ, "PYTHONPATH": str(MCP_SRC)},
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                tokens[role] = data["token"]
                info(f"Credential issued: {role}")
            else:
                fail(f"Credential issue failed for {role}: {result.stderr.strip()}")
        except Exception as exc:
            fail(f"Credential issue error for {role}: {exc}")
    return tokens


def install_agents(scope: str, project_dir: Path | None = None) -> bool:
    """Copy agent specs and commands to the target location."""
    if scope == "user":
        home = Path.home()
        agents_dst = home / ".claude" / "agents"
        commands_dst = home / ".claude" / "commands"
    else:
        root = project_dir or Path.cwd()
        agents_dst = root / ".claude" / "agents"
        commands_dst = root / ".claude" / "commands"

    agents_dst.mkdir(parents=True, exist_ok=True)
    commands_dst.mkdir(parents=True, exist_ok=True)

    src_agents = DIST_CLAUDE / ".claude" / "agents"
    src_commands = DIST_CLAUDE / ".claude" / "commands"

    copied = 0
    for md in src_agents.glob("*.md"):
        shutil.copy2(md, agents_dst / md.name)
        copied += 1

    if src_commands.is_dir():
        for md in src_commands.glob("*.md"):
            shutil.copy2(md, commands_dst / md.name)
            copied += 1

    info(f"{copied} files copied to {agents_dst.parent}")
    return copied > 0


def write_mcp_config(scope: str, tokens: dict[str, str], project_dir: Path | None = None) -> bool:
    """Write .mcp.json with the ADLC server config."""
    if scope == "user":
        mcp_path = Path.home() / ".claude" / ".mcp.json"
    else:
        mcp_path = (project_dir or Path.cwd()) / ".mcp.json"

    existing: dict = {}
    if mcp_path.exists():
        try:
            existing = json.loads(mcp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warn(f"Existing {mcp_path} is invalid JSON, will overwrite")

    servers = existing.setdefault("mcpServers", {})

    dev_token_ref = "${ADLC_DEVELOPER_TOKEN}"
    env_block: dict[str, str] = {
        "PYTHONPATH": str(MCP_SRC).replace("\\", "/"),
        "ADLC_MODULES": "evidence_ledger,change_management,work_planning,contract_registry",
        "ADLC_TOKEN": dev_token_ref,
        "ADLC_DATA_DIR": ".adlc",
        "ADLC_SKILLS_ROOT": str(REPO_ROOT).replace("\\", "/"),
    }

    servers["adlc"] = {
        "command": "python",
        "args": ["-m", "adlc_mcp"],
        "env": env_block,
    }

    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    info(f"MCP config written to {mcp_path}")
    return True


def write_env_reference(tokens: dict[str, str]) -> Path:
    """Write a reference .env file with all tokens."""
    adlc_dir = Path.home() / ".adlc"
    adlc_dir.mkdir(parents=True, exist_ok=True)
    env_path = adlc_dir / "tokens-reference.env"

    lines = [
        "# ADLC tokens — generated by setup_adlc.py",
        "# Source this file or copy values to your shell profile.",
        f"# Generated: {__import__('datetime').datetime.now().isoformat(timespec='seconds')}",
        "",
        f'ADLC_SKILLS_ROOT="{str(REPO_ROOT)}"',
        "",
    ]
    for role, token in sorted(tokens.items()):
        env_name = TOKEN_ENV_NAMES.get(role, f"ADLC_{role.upper().replace('-', '_')}_TOKEN")
        lines.append(f'{env_name}="{token}"')

    lines.append("")
    env_path.write_text("\n".join(lines), encoding="utf-8")
    info(f"Token reference saved to {env_path}")
    return env_path


def set_env_vars_windows(tokens: dict[str, str]) -> None:
    """Set persistent user-level environment variables on Windows."""
    pairs = {"ADLC_SKILLS_ROOT": str(REPO_ROOT)}
    for role, token in tokens.items():
        env_name = TOKEN_ENV_NAMES.get(role, f"ADLC_{role.upper().replace('-', '_')}_TOKEN")
        pairs[env_name] = token

    for name, value in pairs.items():
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f'[Environment]::SetEnvironmentVariable("{name}", "{value}", "User")'],
                capture_output=True, text=True, timeout=15,
            )
        except Exception:
            warn(f"Could not set {name} via PowerShell")

    info(f"Set {len(pairs)} user-level environment variables")


def print_env_instructions_unix(tokens: dict[str, str]) -> None:
    """Print shell export lines for Unix users."""
    print("\n  Add these to your ~/.bashrc or ~/.zshrc:\n")
    print(f'  export ADLC_SKILLS_ROOT="{REPO_ROOT}"')
    for role, token in sorted(tokens.items()):
        env_name = TOKEN_ENV_NAMES.get(role, f"ADLC_{role.upper().replace('-', '_')}_TOKEN")
        print(f'  export {env_name}="{token}"')
    print()


def run_checks() -> bool:
    """Verify the installation is working."""
    heading("Verification")
    ok = True
    ok = check_python() and ok
    ok = check_mcp_importable() and ok
    ok = check_dist_generated() and ok

    home = Path.home()
    agents_dir = home / ".claude" / "agents"
    if agents_dir.is_dir() and len(list(agents_dir.glob("*.md"))) >= len(AGENT_ROLES):
        info(f"User-level agents installed ({len(list(agents_dir.glob('*.md')))} files)")
    else:
        warn("User-level agents not found — run without --check to install")
        ok = False

    mcp_path = home / ".claude" / ".mcp.json"
    if mcp_path.exists():
        try:
            cfg = json.loads(mcp_path.read_text(encoding="utf-8"))
            if "adlc" in cfg.get("mcpServers", {}):
                info("MCP config has adlc server entry")
            else:
                warn("MCP config missing adlc server entry")
                ok = False
        except json.JSONDecodeError:
            fail("MCP config is invalid JSON")
            ok = False
    else:
        warn(f"No MCP config at {mcp_path}")
        ok = False

    skills_root = os.environ.get("ADLC_SKILLS_ROOT")
    if skills_root:
        info(f"ADLC_SKILLS_ROOT = {skills_root}")
    else:
        warn("ADLC_SKILLS_ROOT not set in current environment")

    dev_token = os.environ.get("ADLC_DEVELOPER_TOKEN")
    if dev_token:
        info("ADLC_DEVELOPER_TOKEN is set")
    else:
        warn("ADLC_DEVELOPER_TOKEN not set in current environment (may need shell restart)")

    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-command ADLC platform installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--scope", choices=["user", "project"], default="user",
                        help="Install scope: user-level (all projects) or project-level (default: user)")
    parser.add_argument("--check", action="store_true",
                        help="Verify existing installation without changing anything")
    parser.add_argument("--skip-credentials", action="store_true",
                        help="Skip credential issuance (use existing tokens)")
    parser.add_argument("--project-dir", type=Path, default=None,
                        help="Target project directory (for --scope project)")
    argv = parser.parse_args(argv)

    if argv.check:
        ok = run_checks()
        print(f"\n{'  All checks passed.' if ok else '  Some checks failed — see above.'}\n")
        return 0 if ok else 1

    print(f"\n  ADLC Platform Installer")
    print(f"  Repo: {REPO_ROOT}")
    print(f"  Scope: {argv.scope}-level")

    heading("Step 1: Prerequisites")
    if not check_python():
        return 1
    if not check_mcp_importable():
        print("\n  Attempting pip install...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e",
             str(REPO_ROOT / "skills" / "mcp-servers" / "adlc-mcp") + "[mcp]"],
            timeout=120,
        )
        if not check_mcp_importable():
            return 1
    if not check_dist_generated():
        print("\n  Regenerating dist/...")
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "skills" / "roles" / "scripts" / "generate_agents.py")],
            timeout=30,
        )
        if not check_dist_generated():
            return 1

    tokens: dict[str, str] = {}
    if not argv.skip_credentials:
        heading("Step 2: Issue Credentials")
        tokens = issue_credentials()
        if not tokens:
            fail("No credentials were issued")
            return 1
        info(f"{len(tokens)}/{len(AGENT_ROLES)} role credentials issued")
    else:
        info("Skipping credential issuance (--skip-credentials)")

    heading("Step 3: Install Agent Specs & Commands")
    if not install_agents(argv.scope, argv.project_dir):
        return 1

    heading("Step 4: Configure MCP Server")
    if not write_mcp_config(argv.scope, tokens, argv.project_dir):
        return 1

    if tokens:
        heading("Step 5: Environment Variables")
        env_path = write_env_reference(tokens)

        if platform.system() == "Windows":
            set_env_vars_windows(tokens)
        else:
            print_env_instructions_unix(tokens)

    heading("Step 6: Verify")
    run_checks()

    heading("Done!")
    print("  The ADLC platform is installed. Start a new Claude Code session to use it.")
    print("  Usage:")
    print("    /adlc from INTAKE to RELEASE    # run full pipeline")
    print("    @developer                       # invoke a role directly")
    print()
    if tokens:
        print(f"  Token reference: {Path.home() / '.adlc' / 'tokens-reference.env'}")
        if platform.system() != "Windows":
            print("  Don't forget to source the exports above in your shell profile.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
