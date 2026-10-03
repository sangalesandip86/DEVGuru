# Discovery output contract

Both scripts are standard-library Python, make no network calls, never execute project code,
and are deterministic for a given tree. The `--git` option adds local `git log` recency only.

## `.adlc/catalog/stack.json` (`stack_fingerprint.py`)
| Field | Meaning | How it's derived |
|---|---|---|
| `languages` | Languages in use | Manifests found, plus file extensions seen at least 3 times |
| `manifests`, `runner_configs` | Paths that were read | `package.json`, `pubspec.yaml`, `pyproject.toml`/`requirements.txt`, `pom.xml`, `build.gradle(.kts)`, `go.mod`, `Cargo.toml`, `*.csproj`; `playwright/cypress/vitest/jest/karma/wdio/detox/cucumber/behave/pytest/specflow` configs |
| `ui_paradigm` | react, vue, angular, svelte, flutter, react-native, jetpack-compose | Dependency rules. `react` is dropped when `react-native` is present. |
| `unit_runner`, `component_testing`, `mock_libs`, `bdd`, `e2e_driver`, `api_testing`, `contract_testing` | Tool sets | Dependency rules and config files. Directory signals: `*UITests` → xcuitest, `androidTest` → espresso, `integration_test` with flutter → flutter-integration_test, `.maestro/` → maestro |
| `layout` | `co-located`, `mirrored`, `mixed` or `none` | At least 70% of test files inside or outside dedicated test dirs |
| `naming_suffixes` | Ordered by frequency | `*.spec.<js|ts>`, `*_test.dart`, `test_*.py`, `*Test.java`, and so on |
| `test_dirs` | Top-level test directories | Path components such as `test/`, `__tests__/`, `e2e/`, `features/`, `integration_test/`, `androidTest/`, `*UITests/` |
| `has_tests` | Any test files at all | `false` routes the next skill to Mode C |

## `.adlc/catalog/test-assets.json` (`test_asset_catalog.py`)
| Field | Meaning |
|---|---|
| `fixtures` | Files in `fixtures/ factories/ builders/ testdata/ mocks/ seeds/`, or named `*Builder.*`, `*Factory.*`, `*.fixtures.*`, `conftest.py`, `*_builder.dart` |
| `page_objects` | Files in `pages/ robots/ screens/ page-objects/`, or named `*Page.*`, `*Robot.*`, `*_page.*`, `*.page.ts` (test files excluded) |
| `step_patterns` | `{framework, keyword, pattern, file, line}` for cucumber-js (strings and regex literals), cucumber-jvm, behave/pytest-bdd, SpecFlow/Reqnroll, Dart gherkin, godog |
| `duplicate_steps` | Patterns equal after normalization (cucumber `{type}`, regex groups and `<param>` become `{}`; case and whitespace folded) |
| `golden_samples` | Per suffix group, the top N by score: +3 passing in the supplied JUnit, +1 per shared helper referenced (max 5), +1 if it has assertions (−5 if none). Ties are broken by git recency, then path. |
| `excluded_samples` | Excluded with a reason: skip/xfail markers, failing in the supplied JUnit, or flaky per flaky-detector |

## `.adlc/catalog/step-patterns.json` (phrases only)
```json
{"classification": "FACT", "source": "...",
 "step_patterns": [{"keyword": "Given", "pattern": "the user {string} is signed in"}],
 "duplicate_steps": [{"normalized": "the user {} is signed in", "count": 2}]}
```
It contains no file paths, line numbers or step bodies, so it reveals nothing about the
implementation. That is why it is the one catalogue file qa-derive may read.

## Known limits
- Dependency detection is name-based. A vendored or monorepo-internal runner can be missed. The
  config-file signals usually catch these cases.
- Step extraction is regex-based. Steps registered dynamically (built in loops, or with computed
  patterns) are not seen. `cucumber --dry-run` in CI is the authoritative check.
- Golden-sample ranking without JUnit or flaky input relies only on static signals. The output
  records which evidence was used (`evidence_used`).
