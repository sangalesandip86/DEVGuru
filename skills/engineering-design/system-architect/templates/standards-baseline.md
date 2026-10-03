# Standards baseline: <system>

<!-- Greenfield ARCHITECTURE stage (plan v3.1 §4.15). ESTABLISHES the declared standards that later
     work must follow. Each row is backed by an ADR. Each tool listed here gets a config file in the
     repo's first TEST_AUTOMATION / INFRASTRUCTURE story. -->

| Concern | Standard (example) | Tool / config | ADR |
|---|---|---|---|
| Language & runtime | TypeScript 5.x on Node 22 LTS | `tsconfig.json` (strict) | ADR-1 |
| Layering | `routes → services → repositories`; domain has no framework imports | dependency-cruiser / import-linter / ArchUnit rules | ADR-2 |
| Error handling | Typed domain errors; RFC 9457 problem+json at the edge | — | ADR-3 |
| Logging & telemetry | Structured JSON logs; OpenTelemetry traces; no PII in logs | logger config | ADR-4 |
| Config & secrets | 12-factor env config; secrets only by reference (vault path) | — | ADR-5 |
| Validation | Schema validation at boundaries (zod / pydantic / Bean Validation) | — | ADR-6 |
| Data access | One ORM/query builder per service; versioned migrations | migration tool | ADR-7 |
| API style | OpenAPI 3.1, contract-first; additive changes only within a major | Spectral ruleset | ADR-8 |
| Testing tiers | Unit / component / contract / E2E (critical journeys only) | runner configs | ADR-9 |
| Lint & format | Enforced in CI | ESLint/ruff + Prettier/black | ADR-10 |
| Dependency policy | A new dependency needs a DECISION + `human:tech-lead` (CODEOWNERS) | dependency-decision-check | ADR-11 |
