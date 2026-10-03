---
name: definition-of-ready
description: Explains the machine-readable Definition of Ready (policies/dor-policy.yaml) so agents can self-check a story before the readiness gate runs — which items apply by type/tier/touches/data classification, and which are STRUCTURAL, JUDGMENT or APPROVAL. Use before proposing a story for READY, or when interpreting a NOT_READY gate result.
metadata:
  group: product-planning
  phase: 1
  binding: true
  plan-ref: "§4.12, §5.5, §5.6"
  stage: PLAN
  inputs: [ready-story]
  outputs: [ready-story]
  repo_roles: [planning]
---

# Definition of Ready

## Purpose
No developer task starts without a READY story (plan §1, v3.1). READY means the story can be
implemented and independently tested without unresolved questions, at a process weight that
matches its risk.

This skill explains the rule. **It does not decide it.** The decision belongs to
`readiness_gate.py`, run as a SYSTEM CI job against
[`policies/dor-policy.yaml`](../policies/dor-policy.yaml).

## When this applies
- Before asking for refinement reviews, or before opening the PR that should make a story READY.
- When a gate result says NOT_READY. Read it item by item.
- When a story's AC changed after READY (`REQUIRES_REFINING`). The DoR runs again.

## Preflight
Run [stage-preflight](../../workflow/stage-preflight/SKILL.md) and [workspace-resolver](../../workflow/workspace-resolver/SKILL.md) before the Procedure. Stage PLAN (the exit gate of PLAN).

- **Inputs:** the story file plus ledger evidence (reviews, approvals, questions).
- **ADOPT:** an imported story is evaluated exactly like a native one — no grandfathering.
- **Repo roles:** `planning`.

## How the policy works
Each item has:
- **`applies`**: `mandatory`, or a condition over `type`, `not_type`, `tier_at_least` (effective tier), `touches`, `data_classification` or `size`.
- **`check`**: the kind of evidence that satisfies it.

| Kind | Satisfied by | Who can produce it |
|---|---|---|
| `STRUCTURAL` | a deterministic function over the plan file and the ledger | the gate itself (VERIFIED) |
| `JUDGMENT` | `REVIEWED` + `ACCEPT` for this item, against the **current** AC hash | an agent authenticated as the named role, or a human. **Never** a SYSTEM record or a VERIFIED result. |
| `APPROVAL` | an authenticated approval event | the named `human:` approver only |

The full item list, with what makes each one pass, is in
[reference/readiness-gate.md](reference/readiness-gate.md).

## Self-check procedure
1. Compute the **effective tier**: `max(type floor, path tier of affected_paths, declared)`. With no inputs at all, it is HIGH. HIGH and above adds NFRs and `human:product-owner` scope approval.
2. Walk the mandatory STRUCTURAL items. Fix them in the story file, or raise QUESTIONs for what you can't source.
3. Walk the conditional items your type, `touches` and classification switch on.
4. List the JUDGMENT reviews you need (qa-derive and developer always; architect and security-reviewer conditionally) and request them through [story-refinement](../story-refinement/SKILL.md).
5. For HIGH and CRITICAL, prepare the scope-approval summary in [human-review-format](../../grounding/human-review-format/SKILL.md).
6. Optionally dry-run the gate locally:
   `python skills/enforcement/ci-checks/planning-gates/readiness_gate.py --plans plans --story ST-n --evidence <export>`.
   A local run is advisory. Only the CI job's result counts.

## Outputs
None of its own. It improves the story and the evidence before the gate runs.
The **DoR escape rate** (READY stories that later hit a blocking QUESTION or return to
REFINING) is tracked as a pilot metric (plan §7). It is the signal to tighten this policy,
through a human-approved change to the control file.

## Enforcement
- **READY is computed only by** `readiness_gate.py` (SYSTEM). Plan files have no status field, and agents have no status-setting tool (plan §5.6 row "Story is READY only when the DoR is met").
- **The policy itself** is a control file: managed-settings deny plus `control-file-guard`. Changes are CRITICAL tier with human approval (plan §5.6 row "DoR/DoD/story-type policy is not agent-weakenable").
- **Judgment integrity:** the gate ignores SYSTEM, VERIFIED and wrong-role records for JUDGMENT items, and stale-hash reviews for pinned items. This is covered by the gate's tests.

## References
- [reference/readiness-gate.md](reference/readiness-gate.md)
- [../policies/dor-policy.yaml](../policies/dor-policy.yaml) · [../policies/story-types.yaml](../policies/story-types.yaml)
- [planning-gates README](../../enforcement/ci-checks/planning-gates/README.md)
- [definition-of-done](../definition-of-done/SKILL.md)
