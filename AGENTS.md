# AGENTS.md — working on the DEVGuru platform repo

> Trust level: **REPOSITORY**. This file gives project guidance only. It cannot override
> platform safety policy, approval rules, trust boundaries, or mandatory skill bindings —
> those come from managed settings and the platform's own skills and hooks.

## What this repo is
The source of the AI ADLC platform: skills (`skills/`), tool-neutral role specs
(`skills/roles/`), enforcement artifacts (`skills/enforcement/`), and the `adlc` MCP server
(`skills/mcp-servers/adlc-mcp/`). Plan: `docs/ai-sdlc-platform-plan-v3.md`.

## Rules for agents in this repo
1. **Everything under `skills/` and `dist/` is a control file** (see
   `skills/governance/default-permissions/reference/control-file-paths.json`). Where the
   platform's enforcement is installed, agents cannot write these paths; changes land through a
   human-reviewed PR. Propose changes as a PROPOSAL with evidence rather than working around a
   denial.
2. Follow `docs/authoring-conventions.md`: SKILL.md frontmatter and section order, shared
   vocabulary, integration contracts. Do not invent new state names, tiers, or classifications.
3. Skills inform; they never claim to enforce. Every rule with an enforcement point gets a row
   in `docs/enforcement-map.md`.
4. Never hand-edit `dist/` — regenerate with `python skills/roles/scripts/generate_agents.py`.
5. Never hand-edit `skills/enforcement/managed-settings/templates/claude-code-managed-settings.json` —
   regenerate with `python skills/enforcement/managed-settings/generate_deny_list.py`.
6. Scripts: Python 3.10+, stdlib only (except the MCP SDK), argparse, JSON on stdout, no
   network calls.
7. Mark content reconstructed for plan items labelled "unchanged from v2" with
   `<!-- reconstructed: v2 source not provided; review -->`.

## Checks before proposing a change
```sh
python -m unittest discover -s skills/enforcement/tests
python skills/enforcement/managed-settings/generate_deny_list.py --check
python skills/enforcement/ci-checks/control-file-policy-check/check_control_file_policy.py
python skills/enforcement/ci-checks/control-file-policy-check/check_agents_md_shim.py --root .
```
