# Anti-Patterns Catalog


Each entry: how to detect it, why it costs, the usual fix. Report with `file:line`.
Prefer deterministic tool output (complexity, duplication, dependency-cycle analyzers) as the
FACT source when available; this list covers what tools miss.

## Structural

| Anti-pattern | Detection | Cost | Typical fix |
|---|---|---|---|
| **God object** | One type >500 LOC or >20 public members, imported by most of the module | Every change risks unrelated behavior; merge conflicts | Split along reasons-to-change (SRP) |
| **Feature envy** | Method uses another object's fields more than its own | Logic lives far from data; duplicated invariants | Move method to the data owner |
| **Shotgun surgery** | One requirement forces small edits across many files | High miss rate on future changes | Consolidate the concept into one module |
| **Divergent change** | One file edited for many unrelated requirements (check `git log`) | Hot spot; conflicts | Split by axis of change |
| **Cyclic dependency** | Module A imports B imports A (tool: import-graph) | Cannot test or deploy separately | Extract shared abstraction; invert one edge |
| **Leaky abstraction** | Callers handle details the abstraction claims to hide (e.g., SQL errors from a repository interface) | Abstraction gives no protection | Translate at the boundary |
| **Primitive obsession** | Money as `float`, IDs as bare `string` passed across layers | Unit/currency/ID-mixup bugs | Value types |
| **Boolean parameter trap** | `process(order, true, false)` | Unreadable call sites, combinatorial branches | Separate methods or an options type/enum |

## Behavioral

| Anti-pattern | Detection | Cost | Typical fix |
|---|---|---|---|
| **Swallowed exception** | `catch` with empty body or log-only, then continue | Silent data corruption | Propagate, or handle with a documented fallback |
| **Hidden temporal coupling** | Method B only works if A was called first, undocumented | Order bugs | Make it impossible to call wrongly (builder, constructor) |
| **Shared mutable state** | Module-level mutable globals, singletons with setters | Race conditions, test bleed | Inject state; make immutable |
| **Magic numbers/strings** | Literal thresholds in logic | Inconsistent changes | Named constants/config |
| **Retry without idempotency** | Retries around non-idempotent writes | Duplicate charges/messages | Idempotency keys |

## Process-level (common in AI-generated diffs)

| Anti-pattern | Detection | Cost | Typical fix |
|---|---|---|---|
| **Speculative generality** | Interfaces/factories with a single implementation and no evidenced second one | Indirection with no payoff | Inline until a second case exists |
| **Copy-paste divergence** | Near-duplicate blocks (tool: duplication detector) | Fixes applied to one copy only | Extract shared function |
| **Oversized diff** | Diff exceeds the risk-tiering size cap (§7) | Unreviewable; hides defects | Decompose before review — return to `developer` |
| **Reinvented utility** | New helper duplicating an existing in-repo or stdlib function | Two behaviors for one concept | Use the existing one; cite its location |
| **Test-shaped implementation** | Code branches on test-only values or fixtures | Passes tests, fails production | Remove; report to `qa-diagnose` |
