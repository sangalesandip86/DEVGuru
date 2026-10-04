# SOLID Principles — Review Checklist


Use SOLID as a diagnostic for *change cost*, not as a style rulebook. A violation only matters
if you can name the change it makes harder. Cite `file:line` and the concrete consequence.

## S — Single Responsibility

**Question:** does this unit have more than one reason to change?

| Signal | How to check | Example finding |
|---|---|---|
| Class mixes I/O and domain logic | Look for HTTP/DB/file calls next to business rules | `InvoiceService.java:40-120` computes tax *and* writes PDFs — a template change forces a retest of tax logic |
| Name needs "And"/"Manager"/"Util" | Read the type name and its public methods | `UserManagerUtils` with 23 static methods across 4 domains |
| Diff touches unrelated methods in one class for one requirement | Compare diff hunks to the requirement | Requirement is "add currency"; diff edits logging, retry, and formatting in the same class |
| >1 team owns callers | CODEOWNERS of callers | Shared module edited by payments and onboarding |

**Not a violation:** a small class with several cohesive methods operating on the same data.

## O — Open/Closed

**Question:** does adding the next *expected* variant require editing existing, tested code?

- Look for `switch`/`if-else` chains on a type code that the requirement or roadmap says will grow.
- A single `if` is fine. Three or more branches on the same discriminator, duplicated in two or
  more places, is a finding.
- Only raise when the growth is evidenced (requirement, ticket, roadmap). Speculative
  extensibility is itself an anti-pattern (see `anti-patterns.md` → Speculative Generality).

## L — Liskov Substitution

**Question:** can every subtype be used wherever its base is, without callers checking which one it is?

- `instanceof`/type checks in callers of an abstraction.
- Overrides that throw `UnsupportedOperationException` / `NotImplementedError`.
- Subtypes that strengthen preconditions (reject inputs the base accepts) or weaken
  postconditions (return null where base never does).

## I — Interface Segregation

**Question:** do implementers or callers depend on methods they never use?

- Interfaces with >7–10 methods where most implementers stub half of them.
- Test doubles that must implement many irrelevant methods to compile.

## D — Dependency Inversion

**Question:** does high-level policy depend directly on low-level detail?

- Domain code constructing concrete clients (`new S3Client()`, `requests.post`) instead of
  receiving an abstraction.
- Hard-coded configuration (URLs, credentials paths) inside domain logic.
- Impossible to unit-test without network/disk → cite the test that had to mock a module global.

## Severity guidance

| Situation | Severity |
|---|---|
| Violation makes a change *in this Change Set's requirement* error-prone | MAJOR |
| Violation will block a documented upcoming change | MAJOR |
| Violation with no identifiable change cost | MINOR |
| Violation causing a demonstrable bug | BLOCKER |
