---
name: default-permissions
description: Role-to-tool permission boundaries and the control-file write denial. Use when assigning tools to an agent role, configuring a subagent/custom agent, or checking whether a role may read, modify, deploy, or set a status.
metadata:
  group: governance
  phase: 0
  binding: true
  plan-ref: "§4.11, §5.5, §5.8"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Default Permissions

## Purpose
Define what each agent role may read, modify, deploy, and set — and guarantee that no agent
role can ever set `APPROVED`, `INTEGRATED`, or `RELEASED`, or write a control file.

## When this applies
- Defining or generating a role (`skills/roles/<role>/role.yaml`).
- Wiring a role's MCP credential and tool surface.
- Any time an agent is unsure whether an action is inside its role's scope.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Cross-cutting: this skill has no stage inputs of its own and is loaded alongside whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

- **Inputs:** the role about to run and the resolved repo map.
- **BLOCK:** a role whose session settings fragment isn't loaded doesn't start — permissions are never assumed.
- **Repo roles:** all resolved repos (control-file paths apply in each).

## Procedure
1. Look up the role in [role-tool-permissions.md](reference/role-tool-permissions.md).
2. Grant only the listed tools/paths via the platform's native scoping (subagent `tools`
   frontmatter in Claude Code; `.agent.md` tool config in Copilot; per-role MCP credential).
3. Never grant `EXTERNAL_MUTATION` or `DEPLOY` operation classes to any agent role.
4. Confirm control-file denial is delivered from managed settings, not the repo
   ([control-file-policy.md](reference/control-file-policy.md)).
5. If an action falls outside the role's row, stop and record a `QUESTION` — a permission
   denial is `ESCALATE`, never retried (see `../../grounding/agent-failure-modes/SKILL.md`).

## Outputs
- No ledger entries of its own. A denied action is recorded by the enforcement hooks as a FACT.

## Enforcement
- No agent sets APPROVED/INTEGRATED/RELEASED → MCP server tool surface (no such tool exists for agent callers).
- Control files never agent-writable → managed settings `permissions.deny` +
  `skills/enforcement/hooks/control-file-guard/` (PreToolUse).
- qa-derive implementation-blind → tool permission denial on implementation paths.
- See [`docs/enforcement-map.md`](../../../docs/enforcement-map.md).

## References
- [reference/role-tool-permissions.md](reference/role-tool-permissions.md)
- [reference/control-file-policy.md](reference/control-file-policy.md)
- [reference/control-file-paths.json](reference/control-file-paths.json) — canonical control-file globs
- `../../grounding/trust-boundaries/reference/control-files.md`
- `../permission-scoping/SKILL.md` (fine-grained matrices, Phase 3)
