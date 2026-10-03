# Current-state architecture: <system>

<!-- Brownfield ARCHITECTURE stage (plan v3.1 §4.14, §4.15). Records the system AS IT IS. These are
     INPUTS, not proposals. Every line cites a source: repo@sha:path, doc:<id>@<hash>#<anchor>,
     or a conventions-catalog entry. Edit only to add missing facts; changes to the system go in
     the delta section of architecture/README.md. -->

## Sources
| Source | Ref | Trust |
|---|---|---|
| Existing ADRs | `<repo>@<sha>:docs/adr/` | REPOSITORY |
| Conventions catalog | `<repo>@<sha>:.adlc/catalog/conventions.json` | SYSTEM (scan output) |
| Architecture docs/diagrams | `doc:<id>@<hash>#<anchor>` | REPOSITORY / EXTERNAL_UNSTRUCTURED |

## Existing decisions (binding until superseded)
| ADR | Decision | Status | Ref |
|---|---|---|---|
| ADR-3 | PostgreSQL is the system of record for payments | accepted | `payments-svc@a1b2c3d:docs/adr/0003-postgres.md` |

Changing any of these needs a NEW ADR with `Supersedes: ADR-n` plus `human:tech-lead` APPROVAL, at any tier.

## Services and repositories
| Service | Repo | Owner | Runtime / framework (from conventions) | Data stores | Exposes |
|---|---|---|---|---|---|

## Layering and conventions (from `conventions.json`)
- Module/layer map, e.g. `routes → services → repositories` (`module_map`)
- Library per concern: `web_framework`, `validation`, `logging`, `orm`, `http_client` (`dependencies`)
- Declared standards: lint, format, type, arch-conformance configs (`declared_standards`)
- Drift notes (`notes`, e.g. `mixed_conventions`), recorded as RISK, not fixed

## Integrations
| From | To | Protocol | Contract | Failure mode |
|---|---|---|---|---|

## Known problems (RISK, not redesigned here)
| RISK entry | Pattern | Proposed REFACTOR / TECHNICAL_STORY |
|---|---|---|
