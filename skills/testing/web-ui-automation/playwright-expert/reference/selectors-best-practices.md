# Selector Best Practices


Written for Playwright; the ranking holds for Selenium, WebdriverIO, and Cypress too.

## Priority order

| Rank | Locator | Why | Example |
|---|---|---|---|
| 1 | Role + accessible name | Mirrors how users and assistive tech find things; survives restyling | `page.getByRole('button', { name: 'Place order' })` |
| 2 | Label | Form fields are bound to labels | `page.getByLabel('Email address')` |
| 3 | Placeholder / text / alt / title | User-visible, but copy changes more often | `page.getByText('Order confirmed')` |
| 4 | Test id | Stable contract between app and tests; invisible to users | `page.getByTestId('cart-total')` |
| 5 | CSS / XPath | Coupled to DOM structure | `page.locator('.cart > li:nth-child(2)')`. **Not allowed in new tests** (plan §4.13). Legacy uses need a written justification. |

When ranks 1–4 are all unavailable for an element, the fix is in the app, not the test. test-engineer
**proposes** a testability hook (an accessible name, label or `data-testid`) to `developer` through the impact
plan's `testability_requests`. It never edits app source itself, and is write-denied there.

## Rules
- **Scope, then find**: chain from a stable container instead of writing one long selector.
  ```ts
  const row = page.getByRole('row', { name: /INV-1042/ });
  await row.getByRole('button', { name: 'Refund' }).click();
  ```
- **Filter instead of index**: `locator.filter({ hasText: 'Pending' })` beats `.nth(3)`.
- **Strictness is a feature**: Playwright throws when a locator matches several elements. Fix the
  locator; don't reach for `.first()` unless "the first one" is the actual requirement.
- **Exact matching for short names**: `{ name: 'Save', exact: true }` avoids matching "Save draft".
- **Test ids**: one naming scheme (`data-testid="<area>-<element>"`), configured via
  `testIdAttribute` if the app uses another attribute. Add test ids only where role and label are
  ambiguous, not on every element.
- **Never** select on generated class names (CSS-module hashes, utility-class soup),
  auto-incremented ids, or absolute XPath copied from devtools.
- **i18n**: when running against several locales, prefer role + test id, or read expected strings
  from the same translation catalog the app uses.

## Review checklist
- [ ] Every CSS/XPath locator has a comment saying why ranks 1–4 were impossible.
- [ ] No `.nth()` / `.first()` without a requirement that justifies ordering.
- [ ] Locators are defined once (page object or fixture), not duplicated across specs.
- [ ] Accessibility gaps found while writing locators (button without a name, input without a label)
      are reported to the developer as a `RISK` — they are product bugs, not test problems.
