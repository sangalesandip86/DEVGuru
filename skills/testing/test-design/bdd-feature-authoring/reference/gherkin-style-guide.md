# Gherkin style guide

## Structure
- **Feature:** one per business capability. Its description says who benefits and why, in one or two lines.
- **Rule:** use it (Gherkin 6+) to group scenarios under one business rule. It maps naturally to one AC.
- **Scenario titles** state the behaviour, not the test: "Transfer above the daily limit is rejected",
  not "Test 3".
- **Steps per scenario:** aim for 3–7. More than 10 usually means imperative UI scripting, or two
  scenarios merged into one.

## Step grammar
| Keyword | Expresses | Must not |
|---|---|---|
| Given | Context or state, written in the past or present tense | Perform the action under test |
| When | Exactly one actor action or event | Chain several actions with And (split the scenario instead) |
| Then | An observable outcome | Inspect internals such as the DB row, mock calls or logs, unless the AC is about them |

## Parameters
- Prefer cucumber expressions with typed parameters: `{int}`, `{float}`, `{string}`, `{word}`, or custom
  types such as `{amount}` and `{currency}`. Bind those in [bdd-step-binding](../../../test-implementation/bdd-step-binding/SKILL.md).
- Quote free text (`"Savings"`) and leave enumerations bare (`EUR`). Use the existing catalogue's
  style if it differs.
- Put numbers in their domain format (`100.00 EUR`), not as raw cents, unless the AC talks in cents.

## Tags
| Tag | Purpose |
|---|---|
| `@ST-12`, `@ST-12/AC-1`, `@SC-1` | Traceability and CI selection. Required on every scenario. |
| `@characterization` | Characterization-mode tests (ADR 0004 §3). Never counted as AC verification. |
| `@e2e`, `@api`, `@ui` | Tier routing for the runner |
| `@wip`, `@skip`, `@ignore` | **Not allowed on merge.** The integrity guard flags them as `SKIP_ADDED`. |

## Anti-patterns
- **UI selectors in steps** (`When I click "#submit"`): these belong in page objects.
- **Conjunction steps** (`Given I am logged in and have 3 items`): split them, which makes them reusable.
- **Scenario per data row:** use `Scenario Outline` instead.
- **Then steps that restate the When** ("Then I transferred 100"): assert an *outcome* instead
  (the balance, a confirmation, an event).
- **Hidden setup in Background** that only some scenarios need.
- **Real personal data in Examples tables:** use builders' personas and reserved values (the fixture PII scan enforces this).
