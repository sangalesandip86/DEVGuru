# Convention checklist (per concern)

Read 2–3 golden files near the change plus the relevant declared standards. For each concern the
change touches, answer the question with evidence (`file:line`). If you can't find evidence,
that concern is "silent" → level-4 generic guidance may apply, recorded as an ASSUMPTION.

| Concern | Look for | Typical evidence |
|---|---|---|
| **Layering / module structure** | Which layers exist (controller/handler → service → repository/domain → infra)? May a layer call two levels down? Feature-folders or layer-folders? Where do DTOs vs domain models live? | `module_map` in the scan; import directions in golden files; conformance config |
| **Naming** | File naming (kebab/snake/Pascal), class/function suffixes (`*Service`, `*Repository`, `use*` hooks), test naming, constants, boolean prefixes (`is/has`) | Golden files; lint naming rules |
| **Error handling** | Exceptions vs result types (`Result`, `Either`, Go `error`)? Custom error hierarchy? Where errors are translated to HTTP/status codes? Wrapping (`%w`, `cause`)? | Base error classes; middleware/exception filters |
| **Logging / telemetry** | Which logger, structured or not, how loggers are obtained (DI, module-level), field naming, correlation/trace IDs, metrics library, span naming | `logging` concern in inventory; logger setup file |
| **DI / configuration** | DI container or manual wiring; config source (env, files, config service); typed config objects; secrets by reference | Composition root; config module |
| **Data access** | ORM vs query builder vs raw SQL; repository pattern; transaction boundaries; migration tool and naming | `orm`/`migrations` in inventory; migrations dir |
| **HTTP clients** | Which client, shared instance/factory, retry/timeout policy, base URL config, auth injection | `http_client` concern; client factory file |
| **Validation** | Library (zod/pydantic/joi/Bean Validation), where validation happens (edge vs domain), error message format | `validation` concern; DTO files |
| **Feature flags** | Provider, flag naming, where flags are evaluated, cleanup practice | `feature_flags` concern |
| **Async / concurrency** | async/await vs callbacks vs reactive; thread pools; queue consumers; cancellation/timeouts; idempotency keys | Golden service files |
| **i18n / l10n** | Message catalogs, key naming, formatting of dates/numbers/currency | i18n dir; library in inventory |
| **API style** | REST resource naming, versioning, pagination, error envelope, casing of JSON fields, OpenAPI-first or code-first; Spectral ruleset | API style guide; openapi files; controllers |
| **Testing style** | (owned by `/testing/test-implementation/suite-authoring`, ADR 0003) | — |

## Output

A short "conventions applied" note in the handoff:

```yaml
conventions_applied:
  catalog: "repo@sha:.adlc/catalog/conventions.json"
  golden_files: ["repo@sha:src/orders/order.service.ts", "repo@sha:src/orders/order.repository.ts"]
  concerns:
    logging: { follows: "pino via src/infra/logger.ts", evidence: "src/orders/order.service.ts:12" }
    errors:  { follows: "DomainError hierarchy", evidence: "src/shared/errors.ts:3" }
  deviations: []          # DECISION ids, if any
  silent_concerns: [i18n] # level-4 guidance applied, recorded as ASSUMPTION
```
