# Approval Matrix

The one authoritative human-approval requirement per tier and transition.

| Tier | `PLANNED → PLAN_APPROVED` | `INTEGRATED → RELEASED` |
|---|---|---|
| LOW | None required — `VERIFIED` is sufficient | None required — forge merge + CI deploy is sufficient |
| MEDIUM | None required — `VERIFIED` + code-reviewer `REVIEWED` | `human:tech-lead` |
| HIGH | `human:tech-lead` | `human:security-lead` |
| CRITICAL | `human:security-lead` AND `human:product-owner` | `human:release-manager` |

## Notes
- Human approvers are named by role with a `human:` prefix, to distinguish them from the
  identically-named agent roles (e.g. `developer`, `product-owner`).
- A human `APPROVED` is an authenticated forge event (CODEOWNERS-gated review or environment
  approval) ingested by the server — never a tool an agent can call.
- For HIGH and CRITICAL, the approval rests on `VERIFIED` machine evidence (§5.5).
- Control-file changes are always CRITICAL (`grounding/trust-boundaries/reference/control-files.md`).
- Degraded Mode (§2): if a required **agent** role does not exist yet, a named human stands in as
  that role's handoff target. This does not change the human approvals above.
- Autonomy gating (`governance/autonomy-gating`): a repo in assist mode requires human review
  before every merge regardless of the tier row.
