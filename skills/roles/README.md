# /roles — agent role definitions

Plan refs: §4.7 (roles), §4.11 (permission table), §5.5 (authority), §8 (author once, generate).

Each role is authored **once**, tool-neutrally, and the Claude Code and GitHub Copilot agent files
are generated from it. Hand-maintaining both copies drifts, because their frontmatter differs.

```
skills/roles/
├── <role>/role.yaml      # tool-neutral spec: scope globs, denied paths, abstract tools, can_set/never_set
├── <role>/ROLE.md        # the agent's instructions (system-prompt body)
├── reference/            # handoff-schema.md (+ handoff.schema.json), conflict-resolution.md, reviewer-diversity.md
├── scripts/generate_agents.py
└── tests/
```

| Role | Phase | Can set | Writes |
|---|---|---|---|
| product-planner | 1 | REVIEWED (decomposition quality) | `plans/**` only, via PR; no shell, no tracker tools |
| developer | 1 | REVIEWED (feasibility/size, refinement only) | repos in Change Set scope |
| qa-derive | 1 | REVIEWED (test design; DoR testability) | `plans/test-designs/**`, `**/*.feature`; **implementation paths denied for read** |
| test-engineer | 1 | REVIEWED (test implementation fidelity) | test code/fixtures/page objects/steps/mocks in test dirs; denied app source, designs, `.feature` |
| qa-diagnose | 1 | REVIEWED (diagnosis; integrity-guard findings) | test files; denied designs and `.feature` |
| code-reviewer | 1 | REVIEWED (code quality, ACCEPT/REJECT) | none |
| security-reviewer | 3 | REVIEWED (security, ACCEPT/REJECT) | none |
| architect | 3 | REVIEWED (design) | architecture docs |
| product-owner | 3 | READY_FOR_APPROVAL | requirements |

No role can set `VERIFIED`, `APPROVED`, `PLAN_APPROVED`, `INTEGRATED`, `RELEASED`, or the story
states `READY`/`DONE`/`ACCEPTED` (derived by CI gates, plan v3.1 §4.12), write control
files, or use `EXTERNAL_MUTATION`/`DEPLOY` operations. The generator refuses to build a spec that
says otherwise.

## role.yaml format

`role.yaml` uses the JSON-compatible subset of YAML (plain JSON, which is valid YAML 1.2). That
keeps the generator stdlib-only. Write it as strict JSON.

- Abstract tools: `read`, `search`, `edit`, `write`, `bash`, `test-run`, `mcp:adlc.<tool>`.
  All MCP tools come from the single `adlc` server (see `docs/authoring-conventions.md`).
- `$changeset:repositories` / `$changeset:scope` are resolved at runtime from the Change Set.
- `$ref:skills/governance/default-permissions/reference/control-file-paths.json` marks control-file
  denial. That denial is enforced org-wide by managed settings, not by the per-role fragment.

## Generating

```sh
python skills/roles/scripts/generate_agents.py          # writes dist/
python skills/roles/scripts/generate_agents.py --check  # CI: exit 1 if dist/ is stale or orphaned
python -m unittest discover -s skills/roles/tests
```

Outputs:

| File | Target |
|---|---|
| `dist/claude/.claude/agents/<role>.md` | Claude Code subagent (`tools` → `Read`, `Grep`, `Glob`, `Edit`, `Write`, `Bash`, `mcp__adlc__<tool>`; `model_tier` → `opus`/`sonnet`/`haiku`) |
| `dist/copilot/.github/agents/<role>.agent.md` | Copilot custom agent (`tools` → `read`, `search`, `edit`, `execute`, `adlc/<tool>`) |
| `dist/claude/settings.roles.json` | Per-role `permissions.deny` fragments (e.g. qa-derive's `Read(src/**)`), applied to that role's session |

**`dist/` is never hand-edited.** Change `role.yaml` or `ROLE.md` and regenerate; `--check` in CI
catches drift. Generated agent files are control files once installed into a repo's `.claude/` or
`.github/`, so installation goes through the human-approved control-file path.
