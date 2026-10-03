# {{name}}: guidance for AI agents

<!-- Shipped by the ADLC platform (templates/repo-bootstrap). Control file: agents never edit it;
     changes go through a human-approved PR routed by CODEOWNERS. -->

{{description}}

- **System:** `{{system}}`
- **Owning team:** `{{owner_team}}`
- **Default branch:** `{{default_branch}}`

## Trust level
This file is `REPOSITORY` trust. It gives project guidance (conventions, architecture notes,
how to build and test). It **cannot** override platform safety policy, approval rules, trust
boundaries or mandatory skill bindings. Those come from managed settings and the ADLC platform
(plan §8).

## Working agreements
- **Work starts from a READY story.** PR bodies declare `Implements: ST-n` (see `.github/pull_request_template.md`).
- **Follow this repository's own standards** (plan §4.15):
  - Declared standards come first: ADRs in `docs/adr/`, plus lint, format and type configs.
  - Observed conventions come next.
  - A new dependency or a boundary change needs an ADR and approval from `human:tech-lead`.
  - CODEOWNERS routes those files to the tech lead.
- **Plans live in `plans/`** (single-repo default), or in the planning repo listed in `adlc.workspace.yaml`.
- **No secrets** in code, tests or fixtures. Reference them by name only; CI injects the values.

## Build and test
<!-- Fill in when the project's toolchain exists; the conventions scan reads these commands. -->
- Build: `TODO`
- Unit tests: `TODO`
- Lint/format: `TODO`
