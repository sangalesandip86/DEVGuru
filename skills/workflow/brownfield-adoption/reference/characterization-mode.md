# Characterization mode

**What it is:** tests that pin the *current* behaviour of code that has no specification, so it
can be changed safely later. It follows Michael Feathers' characterization tests.

**What it is not:** verification that the code is correct. ADR 0003 makes the platform's core
QA rule that the code is never the oracle. Characterization mode is the one sanctioned
exception, and only because it is labelled honestly.

## Preconditions
- The run starts at TEST, and preflight returned `ASK` for `test-design`: there is no story or AC.
- The user explicitly chose characterization over writing AC first.

## Rules
1. **Record the assumption.** Write an ASSUMPTION entry: "behaviour of `<repo>@<sha>` (paths …)
   is intended". Give it `impact` (MEDIUM by default) and `expires_at` (90 days by default).
2. **Tag every test** with the stack's tag mechanism:

   | Stack | Tag |
   |---|---|
   | Jest/Vitest | `describe("[characterization] …")`, or a `characterization` folder |
   | pytest | `@pytest.mark.characterization` |
   | JUnit 5 | `@Tag("characterization")` |
   | Cucumber | `@characterization` on the feature |
   | Go | a `TestCharacterization…` prefix, or a `//go:build characterization` tag |
   | Flutter | `group('characterization', …)` |

3. **Never add `ST-n/AC-n` tags** to a characterization test. `ac_coverage.py` counts only those
   tags, so these tests can never satisfy a story's DoD.
4. **Snapshot or golden-master style is fine here,** but only as a separate category. The
   integrity guard still applies to later edits. A mass snapshot update counts as weakening.
5. **Graduation.** When a story with AC later covers the same behaviour, qa-derive designs tests
   from the AC.
   - If a characterization test asserts the same behaviour, test-engineer re-tags it with the AC
     ID and removes `characterization`.
   - If the AC disagrees with the current behaviour, the characterization test is now wrong. That
     is a **defect or a requirement change**, decided by a human, and never a silent edit to the test.
6. **Expiry.** When the ASSUMPTION expires, self-improvement raises a signal: legacy behaviour has
   been pinned for N days with no AC. A human then decides whether to write AC or renew the assumption.
