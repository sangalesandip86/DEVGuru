# dependency-decision-check

Plan v3.1 §4.15 / [ADR 0005](../../../../docs/adr/0005-follow-existing-project-standards.md):
on an existing codebase a new dependency (or a major-version bump) is a deviation from the
project's standards. It needs a **DECISION** with a short ADR, architect `REVIEWED`, and
`human:tech-lead` APPROVAL at any tier. This check enforces the machine-checkable part — *"a
dependency-manifest diff that isn't linked to a DECISION is flagged"*. The human APPROVAL is
enforced by CODEOWNERS review on the PR.

## What it detects

| Manifest | Ecosystem | Sections read |
|---|---|---|
| `package.json` | npm | dependencies, devDependencies, peerDependencies, optionalDependencies |
| `pyproject.toml` | pypi | `[project]` deps + optional-deps, `[dependency-groups]`, Poetry deps/groups |
| `requirements*.txt` / `.in` | pypi | requirement lines (skips `-r`, `-e`, URLs) |
| `pom.xml` | maven | every `<dependency>` (`${property}` versions resolved) |
| `build.gradle`, `build.gradle.kts` | maven | `implementation/api/…("g:a:v")` string notation |
| `go.mod` | go | `require` lines and blocks |
| `Cargo.toml` | cargo | dependencies, dev-, build-, workspace and target-specific tables |
| `pubspec.yaml` | pub | dependencies, dev_dependencies, dependency_overrides (SDK entries skipped) |
| `*.csproj` | nuget | `PackageReference` (attribute or child `Version`) |

| Change | Needs a DECISION |
|---|---|
| `added` | yes |
| `major_upgrade` (major increases; for `0.x`, a minor increase) | yes |
| `removed` | no (info) — yes with `--strict-removals` |
| `upgraded` / `downgraded` / `changed` (non-major) | no (info) |
| manifest can't be parsed | fails — unknown is treated as unsafe (§5.3) |

## What counts as a DECISION link
The package name (case-insensitive; Maven `artifactId`, npm unscoped name, Go last path
segment, and Python `-`/`_`/`.` normalisation also accepted) appears in:
- a `DECISION` entry of an Evidence Ledger export passed with `--evidence` (JSON list or
  `{"entries": [...]}`; entries with `lifecycle_state: REJECTED` are ignored), or
- an ADR markdown file added or changed in the same diff (path containing `adr/`, `adrs/`
  or `decisions/`).

## Usage
```sh
# git refs (CI)
python check_dependency_decisions.py --base origin/main --head HEAD [--evidence ledger-export.json]
# two directory trees
python check_dependency_decisions.py --base-dir before/ --head-dir after/
```
Exit codes: `0` pass · `1` dependency change without a DECISION (or unparseable manifest) ·
`2` bad input. JSON report on stdout; a markdown summary is appended to `$GITHUB_STEP_SUMMARY`
on failure.

## Workflow snippet
```yaml
  dependency-decision-check:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/checkout@v4
        with:
          repository: YOUR-ORG/adlc-platform
          ref: PINNED_PLATFORM_RELEASE_SHA
          path: .adlc-platform
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      # Optional: export DECISION entries for this Change Set from the adlc ledger first.
      - name: New dependencies are backed by a DECISION
        run: >
          python .adlc-platform/skills/enforcement/ci-checks/dependency-decision-check/check_dependency_decisions.py
          --base "origin/${{ github.base_ref }}" --head HEAD
```
Make it a required status check. Pair it with a CODEOWNERS entry routing every manifest file
to `human:tech-lead` so the APPROVAL half of the rule is also enforced.

Limits: Gradle version catalogs (`libs.versions.toml`) and `dependencies { implementation(libs.x) }`
aliases aren't resolved yet; lockfiles are deliberately ignored (transitive changes are not
deviations from project standards).
