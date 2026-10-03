# plans/

Plan-as-code (plan v3.1 §4.12). Agents write these files through a PR, and humans merge them.
A CI job running as SYSTEM projects them to the tracker.

| Directory | Contents |
|---|---|
| `intake/` | Source register, NFR catalog, glossary, personas, constraints, traceability matrix (§4.14) |
| `requirements/` | `REQ-n.yaml` |
| `epics/` | `EPIC-n.yaml` |
| `stories/` | `ST-n.yaml`, with acceptance criteria `ST-n/AC-n` |
| `milestones/` | `MS-n.yaml` |
| `test-designs/` | `ST-n.yaml`: qa-derive's frozen test design (§4.13) |
| `inbox/` | Tracker items staged by brownfield adoption. Drafts only; gates never run on them. |

Plan files have **no status field**. A story's status (READY, DONE, …) is derived by the planning
gates and recorded in the Evidence Ledger.
