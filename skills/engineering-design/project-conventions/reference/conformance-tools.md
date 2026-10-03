# Architecture-conformance tools

Conformance rules turn observed layering into **declared, CI-enforced** standards (`VERIFIED`).
When a project has none, recommend adding one as a `TECHNICAL_STORY` — don't add it inside a
feature change. Changes to CI config are control-file changes (CRITICAL, human approval).

## Java / Kotlin — ArchUnit

```java
@AnalyzeClasses(packages = "com.acme.orders")
class LayeringTest {
  @ArchTest static final ArchRule layers = layeredArchitecture().consideringAllDependencies()
      .layer("Web").definedBy("..web..")
      .layer("Service").definedBy("..service..")
      .layer("Persistence").definedBy("..persistence..")
      .whereLayer("Web").mayNotBeAccessedByAnyLayer()
      .whereLayer("Service").mayOnlyBeAccessedByLayers("Web")
      .whereLayer("Persistence").mayOnlyBeAccessedByLayers("Service");
}
```

## JS / TS — dependency-cruiser

```js
// .dependency-cruiser.js
module.exports = { forbidden: [
  { name: "no-ui-to-db", severity: "error",
    from: { path: "^src/ui" }, to: { path: "^src/db" } },
  { name: "no-circular", severity: "error", from: {}, to: { circular: true } },
]};
```
Run: `npx depcruise src --config .dependency-cruiser.js`

## JS / TS — eslint-plugin-boundaries

```js
// eslint.config.js (excerpt)
settings: { "boundaries/elements": [
  { type: "controller", pattern: "src/controllers/*" },
  { type: "service", pattern: "src/services/*" },
  { type: "repository", pattern: "src/repositories/*" } ] },
rules: { "boundaries/element-types": [2, { default: "disallow", rules: [
  { from: "controller", allow: ["service"] },
  { from: "service", allow: ["repository"] } ] }] }
```

## Nx — module boundaries

```json
"@nx/enforce-module-boundaries": ["error", { "depConstraints": [
  { "sourceTag": "type:feature", "onlyDependOnLibsWithTags": ["type:ui", "type:data-access", "type:util"] },
  { "sourceTag": "type:util", "onlyDependOnLibsWithTags": ["type:util"] } ] }]
```

## Python — import-linter

```ini
# .importlinter
[importlinter]
root_package = orders

[importlinter:contract:layers]
name = Layered architecture
type = layers
layers =
    orders.api
    orders.service
    orders.repository
```
Run: `lint-imports`

## Go — golangci-lint depguard

```yaml
# .golangci.yml
linters: { enable: [depguard] }
linters-settings:
  depguard:
    rules:
      domain:
        files: ["**/internal/domain/**"]
        deny:
          - pkg: "database/sql"
            desc: "domain must not depend on persistence"
```

## API style — Spectral

```yaml
# .spectral.yaml
extends: ["spectral:oas"]
rules:
  paths-kebab-case:
    given: "$.paths[*]~"
    then: { function: pattern, functionOptions: { match: "^(/[a-z0-9-{}]+)+$" } }
```
Run: `spectral lint openapi.yaml`

## Choosing

| Stack | First choice | Alternative |
|---|---|---|
| Java/Kotlin | ArchUnit | Konsist (Kotlin) |
| TS/JS (single app) | dependency-cruiser | eslint-plugin-boundaries |
| TS/JS (Nx monorepo) | Nx module boundaries | — |
| Python | import-linter | — |
| Go | golangci depguard | go-arch-lint |
| HTTP APIs | Spectral | — |
