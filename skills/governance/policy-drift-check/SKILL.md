---
name: policy-drift-check
description: Detect drift between declared platform policy and deployed settings. Use on a schedule, after platform releases, and before pilot reviews.
metadata:
  group: governance
  phase: 3
  binding: true
  plan-ref: "§2 Phase 3, §4.11"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: []
---

# Policy Drift Check


## Purpose
Policy that exists only on paper is not policy. This check compares the declared sources of
truth against the artifacts that actually enforce them and reports every gap.

## When this applies
- CI, on every change to `skills/`, `dist/`, or managed-settings templates.
- Scheduled (daily) against the org's deployed managed settings.
- Before any pilot checkpoint review.

## Preflight
See [standard-preflight](../../workflow/stage-preflight/reference/standard-preflight.md) (cross-cutting).

- **Inputs:** deployed managed settings and the canonical policy files.
- **ADOPT:** newly resolved or created repos are added to the drift-check scope on their first run.
- **Repo roles:** all resolved repos.

## Procedure
1. **Control-file coverage** — run
   `python skills/enforcement/ci-checks/control-file-policy-check/check_control_file_policy.py`;
   every glob in `control-file-paths.json` must appear in the managed deny list.
2. **AGENTS.md shims** — run `check_agents_md_shim.py`; every `AGENTS.md` has a sibling
   `CLAUDE.md` importing it.
3. **Role surfaces** — regenerate `dist/` from `skills/roles/*/role.yaml` and diff against the
   committed copy; any diff is drift.
4. **Enforcement map** — every rule in `docs/enforcement-map.md` names an artifact path that
   exists.
5. Record each finding as a `RISK` entry; any control-file coverage gap is `CRITICAL`.

## Outputs
- `FACT` (check results, written by CI), `RISK` per drift finding.

## Enforcement
**Enforced** — see rules below.

CI check (`skills/enforcement/ci-checks/`) failing the build; required status check on
the platform repo's default branch.

## References
- `../default-permissions/reference/control-file-policy.md`
- `../../enforcement/ci-checks/control-file-policy-check/README.md`
- `../../../docs/enforcement-map.md`
