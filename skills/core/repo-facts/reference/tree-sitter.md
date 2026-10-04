# tree-sitter in repo-facts (optional second pass)

The stdlib-only first pass (regex in `stack_fingerprint.py`, `convention_scan.py`,
`scan-imports.py`) covers 90%+ of use cases. tree-sitter adds precision for:

- **Symbol resolution**: cross-file references, re-exports, barrel files.
- **Call-graph extraction**: which function calls which, enabling impact analysis.
- **Type hierarchy**: interface implementations, class inheritance.
- **Dead-code detection**: exported but never imported symbols.

## When to use

Use tree-sitter only when the stdlib first pass produces ambiguous results (e.g. multiple
candidate modules for an import alias) and a project build is available. Never require
tree-sitter as a precondition — the platform must degrade gracefully to regex.

## Integration contract

A tree-sitter second pass:

1. Accepts the first-pass output (`stack.json`, `conventions.json`) as input.
2. Produces a `symbols.json` (same `.adlc/catalog/` location) with per-file symbol lists.
3. Records the result as a `FACT` entry via the evidence ledger.
4. Falls back to the first-pass result if tree-sitter is not installed.

## Supported languages (initial)

| Language | Grammar package | Notes |
|---|---|---|
| Python | `tree-sitter-python` | Import resolution, class hierarchy |
| TypeScript/JavaScript | `tree-sitter-typescript` | Re-exports, barrel files |
| Go | `tree-sitter-go` | Interface satisfaction |
| Java/Kotlin | `tree-sitter-java` | Annotation scanning |
| Rust | `tree-sitter-rust` | Trait implementations |

## Design constraints

- tree-sitter is an **optional** dependency, never bundled.
- Parsing is capped at 10 seconds per file, 5 minutes total.
- The grammar version is pinned in `requirements-optional.txt`.
- SCIP is never a precondition — tree-sitter replaces SCIP's role here.
