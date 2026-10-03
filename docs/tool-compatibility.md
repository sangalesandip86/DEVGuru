# Tool Compatibility — Claude Code / GitHub Copilot

Plan §8.

## AGENTS.md — precedence

Claude Code added AGENTS.md support in v2.1.277 (2026-09-18) **only as a fallback**: it is
read when no `CLAUDE.md` / `CLAUDE.local.md` exists at or above the working directory. If a
`CLAUDE.md` exists, AGENTS.md is ignored unless the `CLAUDE.md` imports it (`@AGENTS.md`) or
`instructionFiles` is `claude-md-and-agents-md`. Versions 2.1.277–2.1.279 also loaded
AGENTS.md only with telemetry on (fixed in 2.1.280).

**Platform rule:** AGENTS.md is the source of truth; beside every AGENTS.md sits a one-line
`CLAUDE.md` containing `@AGENTS.md`; CI enforces it
(`skills/enforcement/ci-checks/control-file-policy-check/check_agents_md_shim.py`). The import
also fires an instructions-loaded hook event, giving a log of which instructions were in
effect.

**Trust:** AGENTS.md is a REPOSITORY-trust file. It carries project guidance (coding
standards, architecture notes) and cannot override platform safety policy, approval rules,
trust boundaries, or mandatory skill bindings — those are delivered through managed settings.

## Concept mapping

| Concept | Claude Code | GitHub Copilot |
|---|---|---|
| `skills/*` | Skills — `SKILL.md` + frontmatter | `.github/skills/` with `SKILL.md` structures |
| `skills/roles/*` | Subagents — `.claude/agents/*.md` (generated in `dist/claude/`) | Custom agents — `.github/agents/*.agent.md` (generated in `dist/copilot/`) |
| `grounding/*`, `enforcement/*` | Hooks in **managed settings** (org scope); `PreToolUse`/`PostToolUse`; block via exit 2 or `permissionDecision: deny` | `.github/hooks/hooks.json`; `preToolUse`/`postToolUse`; same `permissionDecision: deny` contract |
| `skill-routing/token-budget-optimizer` | Model per subagent, instructions moved into skills, verbose work delegated to subagents | Path-scoped `.github/instructions/`, per-agent model/MCP scoping |
| `governance/default-permissions` | Subagent `tools:` frontmatter, per-agent MCP scoping, managed-settings deny list | `.agent.md` tool config, per-agent MCP scoping, org rulesets |
| Stateful engines | MCP client → server `adlc` (tools `mcp__adlc__<tool>`) | MCP client → server `adlc` |
| Handoff contracts | `record_handoff` via MCP; subagent delegation is the runtime delivery | `record_handoff` via MCP — **native handoffs are not supported for the Copilot cloud agent on GitHub.com**, so MCP is the durable handoff mechanism there |

## Hook event asymmetry

Copilot's events: `sessionStart`, `sessionEnd`, `userPromptSubmitted`, `preToolUse`,
`postToolUse`, `errorOccurred`. All enforcement logic here targets that common subset. Extra
Claude Code events are enhancements, never dependencies — verify any event name against the
current Claude Code hook reference before building on it.

Stdin shapes differ (`tool_name`/`tool_input`/`tool_response` vs
`toolName`/`toolArgs`/`toolResult`); `skills/enforcement/lib/adlc_enforcement.py::parse_event`
normalises both.

## Packaging

Each top-level `skills/<group>` is a plugin boundary. `skills/enforcement` ships from a
managed / organizational source, never as an editable part of a repo's plugin install.

## Generation

Roles are authored once (`skills/roles/<role>/role.yaml` + `ROLE.md`) and generated into both
formats by `skills/roles/scripts/generate_agents.py`. Hand-maintaining both copies drifts;
`governance/policy-drift-check` diffs regenerated output against `dist/`.
