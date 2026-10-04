---
name: stage-preflight
description: Check whether work can start at a stage -- classify inputs as SATISFIED/ADOPT/BACKFILL/ASK/BLOCK. Use at every stage start.
metadata:
  group: workflow
  phase: 1
  binding: true
  plan-ref: "§4.14"
  stage: CROSS_CUTTING
  inputs: []
  outputs: []
  repo_roles: [app, planning]
---

# Stage Preflight

## Purpose
Users can start at any stage. This skill makes sure that starting late **never switches a gate
off**. It checks the start stage's required inputs and returns one outcome per input. Each
outcome comes with exactly what to do next.

## When this applies
- The **Preflight** section of every stage skill. A skill invoked directly, without the conductor,
  still runs this check.
- Every `/adlc` run, before the first stage and between stages.

## Preflight
Resolve the workspace first ([workspace-resolver](../workspace-resolver/SKILL.md)), or pass its JSON with `--workspace`.

## Procedure
1. Run:
   ```
   python skills/workflow/stage-preflight/scripts/stage_preflight.py --start <STAGE> [--end <STAGE>]
       [--story ST-n] [--tier T] [--story-type TYPE] [--mode characterization]
       [--workspace ws.json | --cwd <dir>] [--plans <dir>] [--evidence evidence.json]
       [--adopt KIND=REF …] [--format text]
   ```
   The evidence export is SYSTEM-produced (reviews, approvals, questions, change sets). Never hand-write it.
2. **Act on each input's outcome.** The full decision table is in [reference/outcomes.md](reference/outcomes.md).

   | Outcome | Meaning | Do |
   |---|---|---|
   | `SATISFIED` | The artifact exists and its gate passed, or it is optional | Nothing |
   | `ADOPT` | It exists outside the platform and you supplied it with `--adopt` | [brownfield-adoption](../brownfield-adoption/SKILL.md): import it as DRAFT, then let the gate run |
   | `BACKFILL` | It is missing | Run the named `backfill_stage` (the smallest run), the conventions scan, or an inline story (LOW BUG_FIX/DOCUMENTATION only) |
   | `ASK` | It is ambiguous, or a human must choose | One batched QUESTION with the listed `options` and a proposed default |
   | `BLOCK` | It exists, but a gate failed on existing evidence | Report the `missing` items. Do not proceed. |

3. **Interpret the tier.** `effective_tier` is the maximum of: the declared tier, the story type
   floor, and the path-based tier. **Unknown means HIGH.** Inputs marked `tier>=…` follow it.
   A user saying "it's small" never lowers the tier. It is recorded as an ASSUMPTION.
4. **Brownfield.** When the app repo already has code, ARCHITECTURE, DESIGN and IMPLEMENT require a
   **fresh** conventions catalog (§4.15). It counts as stale when:
   - a declared standard's hash changed or the file was removed;
   - a dependency manifest is newer than the catalog;
   - HEAD differs from a recorded `head_sha`.

   A stale catalog means BACKFILL: re-run `convention_scan.py`, which is cheap and has no side effects.
5. **Characterization mode** is valid only at TEST, and only when the user chose it. The resulting
   tests never count as AC verification.

## Overrides
When the preflight output contains `overrides`, each override relaxes a preflight input.
Record every override as a `RISK` entry via `record_evidence` with `source_type: "agent_analysis"`
and `metadata: {"preflight_override": true, "override": "<the override text>"}`. This makes
overrides auditable in the ledger — a downstream reviewer or gate can query for unacknowledged
preflight risk.

## Outputs
- Preflight JSON (or `--format text`), recorded as FACT by the fact-writer hook.
- QUESTIONs for ASK outcomes, batched per run.
- RISK entries for each override (see above).

## Enforcement
**Enforced** (partial) — see rules below.

- The preflight is a deterministic script, but it **informs**. What actually stops work without its
  input is the downstream CI and server gates:
  - `readiness_gate.py`: no READY means the story cannot be implemented under the DoD;
  - `completion_gate.py`;
  - `ac_coverage.py`, which never counts characterization tests;
  - the test-integrity checks;
  - forge events for INTEGRATE and RELEASE.
- **Judgments** (architecture review, DoR judgments) are satisfied only by REVIEWED/ACCEPT from the
  named role or a human. SYSTEM evidence never counts (§5.5). This is the same rule as the planning gates.

## References
- [scripts/stage_preflight.py](scripts/stage_preflight.py) · [reference/outcomes.md](reference/outcomes.md)
- [../stages.yaml](../stages.yaml) · [../stages.schema.json](../stages.schema.json)
- [planning gates](../../enforcement/ci-checks/planning-gates/README.md) · [project-conventions](../../engineering-design/project-conventions/SKILL.md)
