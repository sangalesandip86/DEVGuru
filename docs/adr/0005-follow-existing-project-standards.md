# ADR 0005: Follow the existing project's standards on brownfield work

- **Status:** Proposed. Requires human approval.
- **Date:** 2026-10-03
- **Normative spec:** [plan v3.1 §4.15](../ai-sdlc-platform-plan-v3.1.md#415-existing-project-standards-brownfield-conformance)

## Context
The platform's skills contain generic best practice: SOLID, decomposition patterns, data-store matrices, idiomatic stack choices. When an agent changes an existing codebase, applying that advice directly causes three problems:
- **Style drift:** a different error-handling pattern or naming scheme in each PR.
- **Silent architecture change:** a new library, layer or data store introduced inside a feature story.
- **Out-of-scope "improvements":** refactors that reviewers never asked for.

All three make AI-authored changes harder to review, which is the instability §7 warns about. ADR 0003 already says that for tests, repo conventions govern style and platform rules override them. This ADR applies the same rule to architecture and implementation.

## Decision

### 1. Precedence (highest first)
1. **Platform safety and governance rules.** Control files, trust boundaries, the Rule of Two, authority levels, no secrets. Nothing below can override these.
2. **The project's declared standards**, written down by the project:
   - ADRs;
   - `AGENTS.md` / `CONTRIBUTING.md` / style guides;
   - lint, format, type-check and compiler configs;
   - architecture-conformance rules (ArchUnit, dependency-cruiser, import-linter, Nx module boundaries, `.golangci` depguard);
   - API style guides and Spectral rulesets.
3. **The project's observed conventions**, inferred from the code itself:
   - layering and module structure;
   - naming;
   - error handling;
   - logging and telemetry;
   - DI and configuration patterns;
   - data access;
   - test style;
   - the libraries already used for each concern.
4. **Generic guidance from platform skills.** Used only where levels 2–3 are silent, or for greenfield work.

Declared standards outrank observed ones. If the code contradicts its own declared standard, the declared standard wins, and the drift is recorded as a RISK. The agent does not copy the drift.

### 2. Consistency over preference
On existing code, agents extend the patterns already in use. **A deviation is a DECISION**, never a silent choice. Deviations include:
- a new dependency or framework;
- a new architectural pattern or layer;
- a different data store or messaging technology;
- a different error-handling or logging approach;
- a new top-level module.

Every deviation requires:
- a short ADR (MADR) stating the existing approach, why it doesn't fit, the alternatives considered, and the migration impact;
- architect REVIEWED;
- **`human:tech-lead` APPROVAL** when the deviation adds a dependency or changes an architectural boundary, at every risk tier.

Dependency manifests are already an always-overlap path class (§4.5). A manifest change that is not linked to a DECISION entry is flagged.

### 3. Bad existing patterns are reported, not fixed in passing
If an existing convention is a known anti-pattern or a security problem, the agent handles it like this:
- **Within the story:** follow the convention unless doing so creates a security or correctness defect. In that case, that one instance deviates as a DECISION.
- **Record the problem:** a RISK entry with evidence, plus a proposed `REFACTOR` or `TECHNICAL_STORY`.
- **Never** fix it across the codebase inside an unrelated change. That would be a scope violation (§4.1).

### 4. Discovery is deterministic, like test discovery
`convention_scan.py` produces `.adlc/catalog/conventions.json`. It records:
- **Declared standards:** where each one lives (doc, config or rules file), with a content hash.
- **Toolchain:** linters, formatters, type-checkers and architecture-conformance tools, with the exact commands to run them.
- **Dependency inventory per concern:** HTTP client, ORM, logging, DI, validation, feature flags, and so on.
- **Existing layout:** layering and module map.
- **Ranked code samples per area:** "golden files" for each layer the change touches, chosen as recent, passing CI, and most imported.

Hooks write the result as FACT entries. A change to config or manifest files invalidates the cached result.

The model then reads the declared standards and two or three golden files near the change. It does not invent conventions from memory.

### 5. Enforcement
| Rule | Enforced by |
|---|---|
| Code matches the project's lint, format and type rules | The project's own toolchain, run in CI. The result is VERIFIED. |
| Architecture boundaries are respected | The project's conformance rules in CI, where they exist (VERIFIED). Where they don't, `architecture-package` recommends adding them as a TECHNICAL_STORY. |
| No silent new dependency or pattern | The CI flag for manifest diffs without a DECISION, plus code-reviewer REVIEWED for convention conformance |
| Conventions are followed in style and structure | code-reviewer REVIEWED against `conventions.json` and the golden files. This is a judgment call and is never VERIFIED. |

## Consequences
- New skill: `/engineering-design/project-conventions` (with `convention_scan.py`). It is required for every ARCHITECTURE, DESIGN and IMPLEMENT task on an existing repo.
- `architect`, `developer` and `code-reviewer` roles, and the system-architect, architecture-package, code-design-reviewer, data-store-selector, messaging-selector, llm-integration-architect and rag-pipeline-expert skills, apply the precedence above. Their generic advice applies only where the project is silent.
- Greenfield repos (created through repo-bootstrap) have no conventions yet. The ARCHITECTURE stage *establishes* them as ADRs, plus lint and conformance configs, so later work has declared standards to follow.
