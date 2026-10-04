---
name: project-bootstrap
description: "Cold-start scaffolding: creates plans/, workspace manifest, and intake REQ so /adlc works from an empty project."
triggers:
  - /adlc init
  - bootstrap project
  - cold start
  - first time setup
---

# Project Bootstrap

Creates the minimum ADLC scaffolding so that `/adlc` commands work in a fresh project.

## What it creates

| Artifact | Purpose |
|---|---|
| `plans/requirements/` | Approved requirements |
| `plans/epics/` | Epic decomposition |
| `plans/stories/` | Story files |
| `plans/milestones/` | Milestone tracking |
| `plans/test-designs/` | QA test designs |
| `plans/intake/` | Incoming requirements |
| `adlc.workspace.yaml` | Workspace manifest (draft) |
| `plans/intake/REQ-1.json` | Initial requirement (if title given) |
| `.adlc/` | Data directory for MCP server |

## Usage

### From the conductor (`/adlc init`)

```
/adlc init --system acme --title "Add payment processing"
```

### From the command line

```bash
python skills/workflow/bootstrap/scripts/bootstrap_project.py \
    --system acme \
    --title "Add payment processing"
```

### Check if already bootstrapped

```bash
python skills/workflow/bootstrap/scripts/bootstrap_project.py --check
```

## Behavior

- **Idempotent**: skips files that already exist.
- **Draft manifest**: sets `draft: true` — review and set `false` before APPROVAL stage.
- **Minimal REQ**: the generated REQ-1 has placeholder `source_refs` and `business_outcome`. Refine during INTAKE.
- **No control files**: does not write AGENTS.md, CODEOWNERS, CI workflows, or `.claude/` config. Those come from `repo-bootstrap` or managed settings.

## After bootstrap

1. Review `adlc.workspace.yaml` and set `draft: false`.
2. Edit `plans/intake/REQ-1.json` with real source refs and business outcome.
3. Run `/adlc from INTAKE to DESIGN` to begin the workflow.
