# Control Files

Platform control files are a named **trust category**. They configure what agents can do, so
an agent that can write them can grant itself anything.

## The category
| Class | Examples |
|---|---|
| Hook configuration | `.claude/hooks/**`, `.claude/settings*.json`, `.github/hooks/**`, `hooks.json` |
| Agent / skill definitions | `.claude/agents/**`, `.claude/skills/**`, `.github/agents/**`, `.github/skills/**`, `skills/**` (this platform) |
| MCP configuration | `.mcp.json`, `.vscode/mcp.json`, Copilot MCP config |
| Instruction files | `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md` (any depth), `.github/copilot-instructions.md`, `.github/instructions/**` |
| Ownership and rules | `CODEOWNERS` (root, `.github/`, `docs/`), repository rulesets |
| CI workflows | `.github/workflows/**`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `Jenkinsfile` |

The machine-readable list is the single source of truth:
`governance/default-permissions/reference/control-file-paths.json`. This page explains it; the
JSON is what hooks, managed settings, and CI read.

## Rules for any write to a control file
1. **Always `CRITICAL` risk tier**, regardless of what else is in the Change Set.
2. **Always requires human approval** — never satisfied by `VERIFIED` alone.
3. **Denied to agents at the managed-settings level** (org-controlled, not repo-editable). A
   project-local setting can be rewritten by anyone with repo write access, or by an injected
   agent with shell access — that is a suggestion, not a control.
4. **Logged via a `ConfigChange`-class hook** regardless of outcome (allowed, denied, or
   attempted by a compromised session).

## What an agent does instead
Produce a PROPOSAL entry with the full intended diff and rationale. A human applies it via a
CODEOWNERS-gated PR. Self-improvement revisions to skills follow the same path
(`self-improvement/improvement-review/reference/human-approval-gate.md`).

## Why this is day one
A real, exploited vulnerability class exists: prompt injection induces an agent to write a
permissive setting into a repo-local config file, which the tool then trusts. Enforcement, not
scanning, is the point — this is not a later hardening pass.

## Shell bypass
Path-based tool denial alone does not cover shell writes (for example a redirect into
`CLAUDE.md`). The `PreToolUse` control-file-guard also inspects shell commands for redirections
and file-mutating commands targeting control paths, and the CI check
(`enforcement/ci-checks/control-file-policy-check`) fails any PR that changes a control path
without the required human approval. Defense in depth: managed settings, hook, CI.
