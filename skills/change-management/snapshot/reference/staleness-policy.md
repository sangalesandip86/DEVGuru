# Staleness Policy

A snapshot is **stale** when the base it pinned has moved in a way that could invalidate the
Change Set's analysis or verification.

## Check 1 — file-path overlap
For each repository: compute files changed on the base branch between `pinned_sha` and current HEAD.
If any intersect the Change Set's changed files (or files it read for analysis), the snapshot is stale.

## Check 2 — always-overlap path classes
These path classes **always count as overlapping**, regardless of exact path match. Any upstream
change to one of them makes the snapshot stale:

| Class | Example globs |
|---|---|
| Lockfiles | `**/package-lock.json`, `**/yarn.lock`, `**/pnpm-lock.yaml`, `**/poetry.lock`, `**/go.sum`, `**/Cargo.lock`, `**/Gemfile.lock` |
| Dependency manifests | `**/package.json`, `**/requirements*.txt`, `**/pyproject.toml`, `**/go.mod`, `**/pom.xml`, `**/build.gradle*`, `**/Cargo.toml` |
| IaC | `**/*.tf`, `**/helm/**`, `**/k8s/**`, `**/Dockerfile*`, `**/docker-compose*.yml` |
| Migrations | `**/migrations/**`, `**/db/migrate/**`, `**/*.sql` |
| Schemas | `**/*.proto`, `**/*.avsc`, `**/*.graphql`, `**/openapi*`, `**/*.schema.json` |
| CI config | `.github/workflows/**`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `Jenkinsfile` |
| Feature flags | `**/feature-flags/**`, `**/flags/**`, `**/*.flags.*` |
| Test runner configs (v3.1 §4.13) | `**/playwright.config.*`, `**/jest.config.*`, `**/vitest.config.*`, `**/cypress.config.*`, `**/karma.conf.*`, `**/pytest.ini`, `**/conftest.py`, `**/tox.ini`, `**/.mocharc*`, `**/cucumber.js`, `**/cucumber.yml`, `**/behave.ini`, `**/.detoxrc*`, `**/detox.config.*`, `**/wdio.conf.*`, `**/testng.xml`, `**/dart_test.yaml` |
| Step-definition directories (v3.1 §4.13) | `**/step_definitions/**`, `**/step-definitions/**`, `**/steps/**` (BDD repos only) |

Runner configs belong here because one setting (timeouts, retries, base URL, projects, setup files)
changes the outcome of every test, and a change to one also invalidates the cached
`stack_fingerprint.py` / `test_asset_catalog.py` FACT entries. Step-definition directories count only
in repos where the fingerprint reports a BDD runner. Steps are shared by phrase across feature files,
so an upstream step change can change any scenario's behavior without touching its file.
Individual spec files and page objects are **not** in this list; ordinary path overlap covers them.

This catches shared-library bumps and base-image changes that a literal path-overlap check misses,
without needing a full semantic dependency graph (deferred, §2).

## Check 3 — contracts and environments (Phase 3)
Stale if a pinned contract has a newer registered version, or if the deployed version of any
consumer/provider in scope changed since the snapshot.

## Outcomes

| Result | Action |
|---|---|
| Current | Proceed |
| Stale, no overlap with tasks in progress | Re-pin; re-run dependency scan + tier; re-verify before `INTEGRATED` |
| Stale, overlaps in-progress task files or an always-overlap class | Re-pin; rebase task worktrees; re-run analysis; tasks re-enter verification |
| Cannot determine (git/registry error) | Treat as **stale** (§5.3) |

Staleness never silently passes: every check writes a `FACT` entry with the compared SHAs.
