# DEVGuru Platform Setup Guide

How to install the ADLC platform skills, agents, MCP server, and enforcement artifacts into
Claude Code — either user-level (available everywhere) or project-level (one repo).

---

## Prerequisites

- **Python 3.10+** installed and on PATH
- **Claude Code** CLI installed (`claude` command available)
- **Git** repository where you want to use the platform

---

## 1. Install the MCP Server

From the DEVGuru repo root:

```bash
# Editable install (recommended for development)
pip install -e "skills/mcp-servers/adlc-mcp[mcp]"

# Or set PYTHONPATH instead of installing
# Windows PowerShell:
$env:PYTHONPATH = "C:\path\to\DEVGuru\skills\mcp-servers\adlc-mcp\src"
# Bash/macOS:
export PYTHONPATH="/path/to/DEVGuru/skills/mcp-servers/adlc-mcp/src"
```

Verify:

```bash
python -c "import adlc_mcp; print('OK')"
```

---

## 2. Issue Credentials

Each agent role and each human approver gets a separate credential. Only token **hashes** are
stored in `~/.adlc/credentials.json`; the plaintext is printed once.

```bash
# From the DEVGuru repo root:
SCRIPT=skills/mcp-servers/adlc-mcp/scripts/adlc_credentials.py

# Agent credentials (one per role)
python $SCRIPT issue --actor-type AGENT --actor-id agent:developer      --agent-role developer       --tool claude-code --model-id claude-opus-4-6
python $SCRIPT issue --actor-type AGENT --actor-id agent:architect      --agent-role architect       --tool claude-code --model-id claude-opus-4-6
python $SCRIPT issue --actor-type AGENT --actor-id agent:product-planner --agent-role product-planner --tool claude-code --model-id claude-opus-4-6
python $SCRIPT issue --actor-type AGENT --actor-id agent:code-reviewer   --agent-role code-reviewer   --tool claude-code --model-id claude-opus-4-6
python $SCRIPT issue --actor-type AGENT --actor-id agent:security-reviewer --agent-role security-reviewer --tool claude-code --model-id claude-opus-4-6
python $SCRIPT issue --actor-type AGENT --actor-id agent:test-engineer   --agent-role test-engineer   --tool claude-code --model-id claude-opus-4-6
python $SCRIPT issue --actor-type AGENT --actor-id agent:qa-derive       --agent-role qa-derive       --tool claude-code --model-id claude-opus-4-6
python $SCRIPT issue --actor-type AGENT --actor-id agent:qa-diagnose     --agent-role qa-diagnose     --tool claude-code --model-id claude-opus-4-6
python $SCRIPT issue --actor-type AGENT --actor-id agent:product-owner   --agent-role product-owner   --tool claude-code --model-id claude-opus-4-6

# Human credential (for approvals)
python $SCRIPT issue --actor-type HUMAN --actor-id human:yourname --human-role human:tech-lead

# Verify a token
ADLC_TOKEN=<token> python $SCRIPT whoami
```

Each command outputs JSON like:

```json
{"token": "XX-Hvh...qPlc", "stored_in": "~/.adlc/credentials.json"}
```

Save each token — you need them for the MCP config and env vars.

### Short-lived credentials (recommended for CI)

```bash
python $SCRIPT issue --actor-type AGENT --actor-id agent:ci-developer \
    --agent-role developer --tool claude-code --model-id claude-opus-4-6 \
    --expires-in 8
```

### Revoking a credential

```bash
python $SCRIPT revoke <plaintext-token>
```

---

## 3. Set Environment Variables

Store the tokens as environment variables so the MCP server can resolve them.

### Windows (permanent, user-level)

```powershell
# Point to the DEVGuru repo so skills/scripts resolve from any project
[Environment]::SetEnvironmentVariable("ADLC_SKILLS_ROOT", "C:\path\to\DEVGuru", "User")

[Environment]::SetEnvironmentVariable("ADLC_DEVELOPER_TOKEN", "<token>", "User")
# Repeat for other roles as needed:
# ADLC_ARCHITECT_TOKEN, ADLC_CODE_REVIEWER_TOKEN, etc.
```

### macOS / Linux (add to ~/.bashrc or ~/.zshrc)

```bash
# Point to the DEVGuru repo so skills/scripts resolve from any project
export ADLC_SKILLS_ROOT="/path/to/DEVGuru"

export ADLC_DEVELOPER_TOKEN="<token>"
export ADLC_ARCHITECT_TOKEN="<token>"
# etc.
```

A reference `.env` file is saved at `~/.adlc/tokens-reference.env` after credential issuance.

> **`ADLC_SKILLS_ROOT`** is the key variable that makes the platform work outside the DEVGuru
> repo. All workflow scripts and enforcement hooks use it to locate `skills/` — without it
> they fall back to relative paths that only work inside the DEVGuru tree.

---

## 4. Install Agent Specs and Commands

Agent specs define the 9 ADLC roles as Claude Code subagents. Commands provide the `/adlc`
slash command.

### User-level (available in all projects — recommended)

```bash
# From the DEVGuru repo root:
# Windows:
xcopy /Y dist\claude\.claude\agents\*.md %USERPROFILE%\.claude\agents\

# Bash / macOS:
mkdir -p ~/.claude/agents ~/.claude/commands
cp dist/claude/.claude/agents/*.md ~/.claude/agents/
cp dist/claude/.claude/commands/adlc.md ~/.claude/commands/
```

This installs:
- 9 agent specs: `architect`, `code-reviewer`, `developer`, `product-owner`,
  `product-planner`, `qa-derive`, `qa-diagnose`, `security-reviewer`, `test-engineer`
- 1 command: `/adlc` — the conductor that runs work through stages

### Project-level (one repo only)

```bash
mkdir -p .claude/agents .claude/commands
cp dist/claude/.claude/agents/*.md .claude/agents/
cp dist/claude/.claude/commands/adlc.md .claude/commands/
```

> **Note:** `dist/` files are generated — never hand-edit them. Regenerate with:
> `python skills/roles/scripts/generate_agents.py`

---

## 5. Configure the MCP Server

### User-level (`~/.claude/.mcp.json`)

Create `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "adlc": {
      "command": "python",
      "args": ["-m", "adlc_mcp"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/DEVGuru/skills/mcp-servers/adlc-mcp/src",
        "ADLC_MODULES": "evidence_ledger,change_management,work_planning,contract_registry",
        "ADLC_TOKEN": "${ADLC_DEVELOPER_TOKEN}",
        "ADLC_DATA_DIR": ".adlc",
        "ADLC_SKILLS_ROOT": "/absolute/path/to/DEVGuru"
      }
    }
  }
}
```

Replace the paths with your actual absolute path to the DEVGuru repo.

### Project-level (`.mcp.json` in repo root)

```json
{
  "mcpServers": {
    "adlc": {
      "command": "python",
      "args": ["-m", "adlc_mcp"],
      "env": {
        "PYTHONPATH": "skills/mcp-servers/adlc-mcp/src",
        "ADLC_MODULES": "evidence_ledger",
        "ADLC_TOKEN": "${ADLC_DEVELOPER_TOKEN}",
        "ADLC_DATA_DIR": ".adlc"
      }
    }
  }
}
```

> `.mcp.json` is a **control file** — in production it ships from managed settings and is
> protected by the control-file guard hook.

### Module choices

| Modules config | What you get |
|---|---|
| `evidence_ledger` | Evidence recording and querying (Phase 0 — start here) |
| `evidence_ledger,change_management` | + change sets, risk tiering, handoffs, snapshots |
| `evidence_ledger,change_management,work_planning` | + story readiness/done gates, work graph |
| `evidence_ledger,change_management,work_planning,contract_registry` | Full platform (all 19 tools) |

---

## 6. Verify the Setup

### Test the MCP server

```bash
# List all tools for your identity
ADLC_TOKEN=<developer-token> \
ADLC_MODULES=evidence_ledger,change_management,work_planning,contract_registry \
python -m adlc_mcp --list-tools
```

Expected output: your identity + 19 tools across 4 modules.

### Test in Claude Code

Start a new Claude Code session in any project:

```
claude
```

You should see:
- The `/adlc` command available (type `/adlc` to invoke the conductor)
- MCP tools available (type "list your MCP tools" to verify `mcp__adlc__*` tools)
- Agent subagents available (the 9 roles show up when using `@agent`)

### Run the test suite

```bash
# From the DEVGuru repo root:

# Enforcement tests (43 tests)
python -m unittest discover -s skills/enforcement/tests -v

# Planning gate tests (46 tests)
python -m unittest discover -s skills/enforcement/ci-checks/planning-gates/tests -v

# MCP server + adversarial tests (142 tests)
cd skills/mcp-servers/adlc-mcp && python -m unittest discover -s tests -t . -v && cd ../../..

# Layer A — Skill Output Evals (42 tests)
python -m unittest skills/testing/eval-harness/test_evals.py -v

# Layer B — Handoff Contract Tests (21 tests)
python -m unittest skills/testing/pipeline-tests/test_handoff_contracts.py -v

# Layer E — Property/Invariant Tests (23 tests)
python -m unittest skills/testing/invariant-tests/test_invariants.py -v

# Layer F — Composition Tests (29 tests)
python -m unittest skills/testing/composition-tests/test_composition.py -v

# Skill contracts check (83 skills)
python docs/tools/check_skill_contracts.py --json

# All mandatory CI checks
python skills/enforcement/managed-settings/generate_deny_list.py --check
python skills/enforcement/ci-checks/control-file-policy-check/check_control_file_policy.py
python skills/enforcement/ci-checks/control-file-policy-check/check_agents_md_shim.py --root .
python skills/roles/scripts/generate_agents.py --check
```

---

## 7. Hooks (Optional)

The platform includes enforcement hooks for Claude Code:

- **control-file-guard** — blocks agent writes to control files
- **config-change-logger** — logs config change attempts
- **fact-writer** — writes FACT entries from command output to the ledger

To install hooks, add them to `.claude/hooks/` (see `skills/enforcement/hooks/` for sources).

Example: writing a FACT entry from a hook:

```bash
echo '{"run_id":"r1","tool":"claude-code","source_type":"command_output","content":"12 passed","source":"cmd:pytest"}' \
  | ADLC_HOOK_NAME=fact-writer python skills/mcp-servers/adlc-mcp/scripts/ledger_cli.py append-fact
```

Verify hash chain integrity:

```bash
python skills/mcp-servers/adlc-mcp/scripts/ledger_cli.py verify
```

---

## 8. Updating

When skills, roles, or enforcement artifacts change upstream:

```bash
# Pull latest
git pull

# Regenerate dist/ (never hand-edit these)
python skills/roles/scripts/generate_agents.py

# Re-copy agents to user level
cp dist/claude/.claude/agents/*.md ~/.claude/agents/
cp dist/claude/.claude/commands/adlc.md ~/.claude/commands/

# If managed settings changed:
python skills/enforcement/managed-settings/generate_deny_list.py

# Run checks
python -m unittest discover -s skills/enforcement/tests -v
python skills/enforcement/managed-settings/generate_deny_list.py --check
```

---

## Environment Variables Reference

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `ADLC_SKILLS_ROOT` | — | For cross-project | Absolute path to the DEVGuru repo root — enables scripts outside the repo |
| `ADLC_TOKEN` | — | Yes | Bearer token for the current role session |
| `ADLC_DEVELOPER_TOKEN` | — | For `.mcp.json` | Developer role token (referenced via `${...}`) |
| `ADLC_CREDENTIALS` | `~/.adlc/credentials.json` | No | Token-hash → identity map path |
| `ADLC_MODULES` | `evidence_ledger` | No | Comma-separated modules to enable |
| `ADLC_DATA_DIR` | `.adlc` | No | Directory for SQLite databases |
| `ADLC_LEDGER_DB` | — | No | Override evidence ledger file path |
| `ADLC_PLATFORM_RELEASE_SHA` | `unversioned` | No | Stamped on every ledger entry |
| `ADLC_PATH_TIERS` | `skills/.../path-tiers.json` | No | Path → risk tier table |
| `ADLC_MAX_DIFF_LINES` | `400` | No | Change-size cap; above → `decompose_required` |
| `ADLC_EVIDENCE_RETENTION_DAYS` | `90` | No | Local evidence payload retention |
| `ADLC_LIVE_MODE` | — | No | Set to `1` to enable live composition tests |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `no credential presented` | Set `ADLC_TOKEN` env var or ensure `ADLC_DEVELOPER_TOKEN` is set |
| `credential not recognised` | Re-issue with `adlc_credentials.py issue ...` |
| `credential expired` | Re-issue (optionally with `--expires-in` for longer validity) |
| `ModuleNotFoundError: adlc_mcp` | Run `pip install -e "skills/mcp-servers/adlc-mcp[mcp]"` or set `PYTHONPATH` |
| MCP server not connecting | Check `~/.claude/.mcp.json` has correct absolute `PYTHONPATH` |
| Agent not found | Verify `~/.claude/agents/` has the `.md` files |
| `/adlc` command not available | Verify `~/.claude/commands/adlc.md` exists |
| `pip: command not found` | Use `python -m pip` instead |
