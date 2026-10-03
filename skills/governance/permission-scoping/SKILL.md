---
name: permission-scoping
description: Fine-grained, per-Change-Set permission matrices that narrow a role's default permissions to exactly the repos, paths, and MCP tools a specific task needs. Use when provisioning an agent session for a task, especially multi-repo or HIGH/CRITICAL work.
metadata:
  group: governance
  phase: 3
  binding: true
  plan-ref: "§2 Phase 3, §4.11, §5.9"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Permission Scoping

<!-- reconstructed: v2 source not provided; review -->

## Purpose
`default-permissions` defines the ceiling per role. Permission scoping narrows each session
below that ceiling to the Change Set's actual scope, and checks the Rule of Two (§5.9).

## When this applies
- Creating an agent session for a task in a Change Set.
- Any session that will read untrusted input (issue text, external docs, MCP responses).

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Cross-cutting: this skill has no stage inputs of its own and is loaded alongside whatever stage is running, so it never BACKFILLs or BLOCKs a stage by itself.

- **Inputs:** role specs and the resolved repo map.
- **Repo roles:** all resolved repos.

## Procedure
1. Start from the role's row in
   `../default-permissions/reference/role-tool-permissions.md`.
2. Intersect with the Change Set's `repositories[]` and the task's declared paths.
3. Remove any MCP tool the task does not need.
4. Rule-of-Two check — count the session's properties:
   (a) reads untrusted input, (b) touches secrets/production data, (c) can mutate external
   state or deploy. If all three, split the session or insert a human checkpoint.
5. Emit the resulting matrix (below) into the session config and as a `DECISION` entry.

### Session matrix shape
```yaml
session: CS-881/TASK-14/developer
role: developer
repos: [repo-a]
read_paths: ["repo-a/**"]
write_paths: ["repo-a/src/billing/**", "repo-a/tests/billing/**"]
deny_paths: ["<control-file-paths.json globs>"]
mcp_tools: [record_evidence, query_evidence, record_incident]
operation_classes: [READ, WORKSPACE_WRITE, REPO_WRITE]
rule_of_two: {untrusted_input: true, secrets: false, external_mutation: false}
```

## Outputs
- `DECISION` (scoped matrix), `RISK` if a scope had to be widened beyond the task's declared paths.

## Enforcement
Per-role tool scoping in subagent/agent frontmatter and per-role MCP credentials; deny
paths delivered via managed settings. A dedicated capability broker is deferred (§2).

## References
- `../default-permissions/SKILL.md`
- `../../grounding/trust-boundaries/SKILL.md`
