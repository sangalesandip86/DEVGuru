# Repo-role heuristics

`resolve_workspace.py` scores every candidate repository for each role. An explicit `--repo`
(score 9) or manifest entry (score 8) always beats a heuristic. Within the same source, the
higher score wins. A tie between two candidates of the same source and score is **AMBIGUOUS**
and is never resolved silently.

| Role | Signal | Score |
|---|---|---|
| `planning` | `plans/` directory, no app code or manifest | 3 |
| `planning` | `plans/` alongside app code (single repo) | 2 |
| `planning` | `architecture/` only | 1 |
| `contracts` | `openapi*.y*ml`, `asyncapi*`, `*.proto`, `pacts/`, `contracts/`, no app code | 3 (1 if app code exists) |
| `infra` | `*.tf`, `Chart.yaml`, `helm/`, `k8s/`, `Pulumi.yaml`, `kustomization.yaml`, no app code | 3 (1 if app code exists) |
| `tests` | Only test dirs/configs (`e2e/`, `tests/`, `features/`, `playwright.config.*`), no app code | 2 |
| `app` | Code dirs (`src/`, `app/`, `lib/`, `pkg/`, `cmd/`, `internal/`, `services/`, `web/`) | 3 |
| `app` | A language manifest only | 2 |
| `app` | Nothing recognisable | 1 (weakest; never treated as planning) |

**Source rank, best first:** explicit > manifest > current repo > sibling.

So the repo you are standing in beats a sibling with the same signal. Two siblings with the same
signal are AMBIGUOUS.

**Single-repo default.** If `planning` is required but no repo scores for it, and `app` resolved,
then `planning` resolves to the app repo with `single_repo_default: true` and `plans/` inside it
(§4.14). This is the expected case for most single-service teams.

**References found in `plans/`.** `repo@sha:path` references in `plans/` whose repo name isn't
present locally are listed as `referenced_but_absent` on MISSING roles. This usually means the
repository exists remotely but hasn't been cloned.
