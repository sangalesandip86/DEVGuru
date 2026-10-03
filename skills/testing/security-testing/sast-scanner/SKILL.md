---
name: sast-scanner
description: Runs and triages static application security testing (Semgrep, CodeQL, language linters like Bandit/gosec) on changed code, with SARIF results ingested as machine evidence. Use for every Change Set at MEDIUM tier and above, and whenever code handling auth, input parsing, crypto, or data access changes.
metadata:
  group: testing
  phase: 1
  binding: false
  plan-ref: "§4.8, §5.5, §9 step 10"
  stage: REVIEW
  inputs: [change-set]
  outputs: [review-verdict]
  repo_roles: [app]
---

# SAST Scanner

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Catch known-dangerous code patterns (injection, unsafe deserialization, path traversal, weak crypto,
SSRF, missing authz checks) deterministically, before review. A clean scan is evidence; it is not proof of security.

## When this applies
- Mandatory in the security gate for HIGH/CRITICAL (plan §5.4), and in CI for every PR on repos with the platform enabled.
- Any change in `auth/`, `payment/`, request parsing, query construction, file handling, or crypto usage.

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`.
2. **Inputs** `[change-set]`. Each resolves to one of:
   - SATISFIED;
   - ADOPT: it exists outside the platform, so import it as DRAFT with its source trust level;
   - BACKFILL: propose the smallest upstream run that produces it;
   - ASK: one batched QUESTION, never empty-handed;
   - BLOCK: a gate failed on existing evidence.
3. **Scanner config.** Semgrep and CodeQL rulesets come from the org-managed platform config, not from the repo. Findings are ingested from CI SARIF; agents triage them but never suppress them.

Never proceed on a missing input silently.

## Procedure
1. **Run in CI, not from the agent's say-so.** Recommended baseline:
   | Tool | Use | Command |
   |---|---|---|
   | Semgrep | Fast, PR-scoped, custom rules | `semgrep scan --config p/default --config p/owasp-top-ten --config .semgrep/ --baseline-commit $BASE_SHA --sarif -o semgrep.sarif` |
   | CodeQL | Deep dataflow/taint, scheduled + PR | `github/codeql-action` with `security-extended` queries |
   | Language-specific | Bandit (Python), gosec (Go), Brakeman (Rails), SpotBugs + FindSecBugs (JVM), eslint-plugin-security | Emit SARIF where supported |
2. **Diff-aware gating**: block on *new* findings at severity ≥ the repo's threshold (default: HIGH blocks,
   MEDIUM blocks at HIGH/CRITICAL tier). Existing findings are tracked debt, not a reason to block unrelated work.
3. **Ingest as machine evidence**: CI uploads SARIF (code scanning) and records the result in the Evidence
   Ledger under the CI system identity (`actor_type: SYSTEM`). The server derives `VERIFIED` from a clean,
   CI-produced result. An agent's statement that "the scan was clean" is not evidence.
4. **Agent triage** (security-reviewer or developer) for each new finding: reachable? attacker-controlled
   input? existing mitigation? Cite `file:line` for source, sink, and any sanitizer. Output is `REVIEWED`
   with ACCEPT (real, must fix) or a false-positive argument.
5. **Suppression is not an agent decision.** A suppression (`# nosemgrep: rule-id`, CodeQL dismissal, baseline
   entry) must carry a reason and is approved by a human reviewer — recommend CODEOWNERS on suppression
   files and `.semgrep/`. Agents may propose suppressions; they never apply them to clear a gate.
6. **Custom rules** for project-specific sinks (internal query builders, template helpers) live in
   `.semgrep/` — those are control-file-adjacent; changes need security-lead review.

## Outputs
- SARIF from CI → `FACT` + server-set `VERIFIED` (clean) or gate failure.
- Triage per finding → `REVIEWED` (ACCEPT/REJECT) with cited evidence; unresolved → `RISK`.
- Proposed suppression → `PROPOSAL` awaiting human approval.

## Enforcement
CI gate on SARIF results (deterministic). VERIFIED is server-set from ingested evidence (plan §5.6 row 1).
Suppression approval is enforced only if suppression files are CODEOWNERS-protected.

## References
- [`../sca-dependency-audit/SKILL.md`](../sca-dependency-audit/SKILL.md), [`../secret-scanning/SKILL.md`](../secret-scanning/SKILL.md)
- [`../../../roles/security-reviewer/`](../../../roles/security-reviewer/)
- [`../../../roles/reference/reviewer-diversity.md`](../../../roles/reference/reviewer-diversity.md) — a deterministic scanner counts as the diverse reviewer at HIGH/CRITICAL
