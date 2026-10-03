---
name: secret-scanning
description: Detects committed credentials and tokens with gitleaks, TruffleHog, and forge push protection, and drives rotation — not just removal — when a secret leaks. Use on every commit/PR and whenever a scan, log, or agent output may contain a credential.
metadata:
  group: testing
  phase: 1
  binding: false
  plan-ref: "§4.8, §5.9"
  stage: REVIEW
  inputs: [change-set]
  outputs: [review-verdict]
  repo_roles: [app, tests]
---

# Secret Scanning

<!-- reconstructed: v2 source not provided; review -->

## Purpose
Keep credentials out of repositories, logs, and agent context. Touching secrets is one leg of the Rule
of Two (plan §5.9): a leaked secret in a repo puts it in front of every agent session that reads that repo.

## When this applies
- Every push and PR (pre-commit locally, push protection on the forge, CI as backstop).
- Scheduled full-history scans; after any incident.

## Preflight
Run the standard preflight before any step below: [`stage-preflight`](../../../workflow/stage-preflight/SKILL.md) and [`workspace-resolver`](../../../workflow/workspace-resolver/SKILL.md).
1. **Workspace.** Resolve repo roles `[app, tests]`. If found, record it as FACT `repo@sha`. If ambiguous, raise one QUESTION with ranked candidates. If missing, workspace-resolver offers local creation or a `repo-request.yaml`.
2. **Inputs** `[change-set]`. Each resolves to one of:
   - SATISFIED;
   - ADOPT: it exists outside the platform, so import it as DRAFT with its source trust level;
   - BACKFILL: propose the smallest upstream run that produces it;
   - ASK: one batched QUESTION, never empty-handed;
   - BLOCK: a gate failed on existing evidence.
3. **History scope.** Scan the full diff range, not just HEAD. Allow-lists come from the reviewed org config, never from inline comments added in this Change Set.

Never proceed on a missing input silently.

## Procedure
1. **Layers**:
   | Layer | Tool | Notes |
   |---|---|---|
   | Pre-commit | `gitleaks git --staged` (pre-commit hook) | Fast feedback; bypassable, so not the control |
   | Forge | GitHub secret scanning + push protection | Blocks known token formats at push |
   | CI | `gitleaks git --log-opts="$BASE_SHA..$HEAD_SHA" --report-format sarif --report-path gitleaks.sarif` | Deterministic gate on the PR range |
   | Deep / verified | `trufflehog git file://. --since-commit $BASE_SHA --only-verified` | Checks whether a found credential is live |
2. **A detected live secret is an incident, not a lint error.** Rotate/revoke first, then remove. Removing it
   from HEAD doesn't remove it from history, forks, or caches. Rotation is an `EXTERNAL_MUTATION` — agents
   cannot do it; they escalate to a human immediately (ESCALATE, never RETRY).
3. **Agents must not echo secrets**: when a finding is reported, cite file, line, and rule id — never paste the
   value into a handoff, ledger entry, PR comment, or chat.
4. **False positives** (test fixtures, example keys): allow-list by path and a fake-looking format in
   `.gitleaks.toml`, reviewed by a human. Agents don't edit allow-lists to pass a gate.
5. **Ingest**: CI records the SARIF result under its system identity; clean → server sets `VERIFIED`.

## Outputs
- Scan results → `FACT` / `VERIFIED` (clean). Live-secret finding → `RISK` (CRITICAL) + human escalation.
- False-positive argument → `REVIEWED` + `PROPOSAL` for the allow-list change.

## Enforcement
Forge push protection and the CI gate are deterministic. "Never echo secrets" is guideline only; fact-writer
hooks should redact matches of known secret patterns before writing ledger entries.

## References
- [`../../../grounding/agent-failure-modes/reference/failure-catalog.md`](../../../grounding/agent-failure-modes/reference/failure-catalog.md)
- [`../../test-maintenance/test-data-management/SKILL.md`](../../test-maintenance/test-data-management/SKILL.md)
- [`../../../enforcement/hooks/fact-writer-hooks/`](../../../enforcement/hooks/fact-writer-hooks/)
