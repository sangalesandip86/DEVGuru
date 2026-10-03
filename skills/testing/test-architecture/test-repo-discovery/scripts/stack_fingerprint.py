#!/usr/bin/env python3
"""Deterministic stack and test-topology fingerprint for a repository (plan §4.13 step 1).

Reads manifests, runner configs and the test-file layout. Never executes project code and makes
no network calls. The output is JSON that hooks record as FACT entries, cached per snapshot.

Usage:
    stack_fingerprint.py <repo_root> [--max-files N] [--out DIR] [--stdout]

Writes <repo_root>/.adlc/catalog/stack.json by default (override the directory with --out);
--stdout prints the fingerprint instead of writing it.

Exit codes: 0 = fingerprint produced, 2 = bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "target",
    "out", ".dart_tool", "Pods", "vendor", ".gradle", ".idea", ".next", ".nuxt", "coverage",
    ".tox", ".mypy_cache", ".pytest_cache", "bin", "obj",
}

# Directory names that hold tests (matched case-insensitively against any path component).
TEST_DIR_NAMES = {
    "test", "tests", "__tests__", "spec", "specs", "e2e", "integration_test", "integration-tests",
    "features", "androidtest", "uitests", "cypress", "playwright", "test_driver", "maestro", ".maestro",
}

# Test-file naming suffixes -> canonical label.
SUFFIX_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("*.spec.<js|ts>", re.compile(r"\.spec\.(?:[cm]?[jt]sx?)$")),
    ("*.test.<js|ts>", re.compile(r"\.test\.(?:[cm]?[jt]sx?)$")),
    ("*.cy.<js|ts>", re.compile(r"\.cy\.(?:[jt]sx?)$")),
    ("*_test.dart", re.compile(r"_test\.dart$")),
    ("test_*.py", re.compile(r"(?:^|/)test_[^/]*\.py$")),
    ("*_test.py", re.compile(r"_test\.py$")),
    ("*_test.go", re.compile(r"_test\.go$")),
    ("*Test.java", re.compile(r"Tests?\.java$")),
    ("*Test.kt", re.compile(r"Tests?\.kt$")),
    ("*Tests.swift", re.compile(r"(?:Tests?|UITests?)\.swift$")),
    ("*Tests.cs", re.compile(r"Tests?\.cs$")),
    ("*_spec.rb", re.compile(r"_spec\.rb$")),
    ("*.feature", re.compile(r"\.feature$")),
]

RUNNER_CONFIGS: list[tuple[re.Pattern, str, str]] = [
    # (filename regex, category, tool)
    (re.compile(r"^playwright\.config\.[cm]?[jt]s$"), "e2e_driver", "playwright"),
    (re.compile(r"^cypress\.config\.[cm]?[jt]s$|^cypress\.json$"), "e2e_driver", "cypress"),
    (re.compile(r"^wdio\.conf\.[cm]?[jt]s$"), "e2e_driver", "webdriverio"),
    (re.compile(r"^\.detoxrc(\.[a-z]+)?$|^detox\.config\.[cm]?[jt]s$"), "e2e_driver", "detox"),
    (re.compile(r"^vitest\.config\.[cm]?[jt]s$|^vitest\.workspace\.[jt]s$"), "unit_runner", "vitest"),
    (re.compile(r"^jest\.config\.[cm]?[jt]s(on)?$"), "unit_runner", "jest"),
    (re.compile(r"^karma\.conf\.[cm]?[jt]s$"), "unit_runner", "karma"),
    (re.compile(r"^\.mocharc(\.[a-z]+)?$"), "unit_runner", "mocha"),
    (re.compile(r"^cucumber\.(?:[cm]?js|json|ya?ml)$"), "bdd", "cucumber"),
    (re.compile(r"^behave\.ini$"), "bdd", "behave"),
    (re.compile(r"^pytest\.ini$|^conftest\.py$"), "unit_runner", "pytest"),
    (re.compile(r"^specflow\.json$|^reqnroll\.json$"), "bdd", "specflow/reqnroll"),
]

# Dependency name (regex, matched against the full dependency name) -> (category, tool)
DEP_RULES: list[tuple[re.Pattern, str, str]] = [
    # UI paradigms
    (re.compile(r"^react-native$"), "ui", "react-native"),
    (re.compile(r"^(react|react-dom|next)$"), "ui", "react"),
    (re.compile(r"^(vue|nuxt)$"), "ui", "vue"),
    (re.compile(r"^@angular/core$"), "ui", "angular"),
    (re.compile(r"^(svelte|@sveltejs/kit)$"), "ui", "svelte"),
    (re.compile(r"^flutter$"), "ui", "flutter"),
    (re.compile(r"androidx\.compose|compose-ui|ui-test-junit4"), "ui", "jetpack-compose"),
    # unit runners
    (re.compile(r"^(jest|vitest|mocha|jasmine|karma|ava|uvu)$"), "unit_runner", None),
    (re.compile(r"^pytest$"), "unit_runner", "pytest"),
    (re.compile(r"^flutter_test$"), "unit_runner", "flutter_test"),
    (re.compile(r"junit-jupiter|^junit:junit$|^junit$"), "unit_runner", "junit"),
    (re.compile(r"^(org\.)?testng"), "unit_runner", "testng"),
    (re.compile(r"^(xunit|nunit|mstest\.testframework)$", re.I), "unit_runner", None),
    (re.compile(r"^github\.com/stretchr/testify"), "unit_runner", "go-test+testify"),
    # component testing
    (re.compile(r"^@testing-library/"), "component", "testing-library"),
    (re.compile(r"^@vue/test-utils$"), "component", "vue-test-utils"),
    # mocking
    (re.compile(r"^(sinon|msw|nock|jest-mock-extended|vitest-mock-extended|testdouble|axios-mock-adapter)$"), "mock_libs", None),
    (re.compile(r"^(mocktail|mockito|http_mock_adapter|bloc_test|fake_async)$"), "mock_libs", None),
    (re.compile(r"^(pytest-mock|responses|respx|freezegun|time-machine|hypothesis|factory[-_]boy|faker)$", re.I), "mock_libs", None),
    (re.compile(r"mockito|mockk|wiremock", re.I), "mock_libs", None),
    (re.compile(r"^(moq|nsubstitute|fakeiteasy)$", re.I), "mock_libs", None),
    (re.compile(r"^github\.com/golang/mock|^go\.uber\.org/mock|^github\.com/h2non/gock"), "mock_libs", None),
    (re.compile(r"^mockall$"), "mock_libs", "mockall"),
    # BDD
    (re.compile(r"^@cucumber/cucumber$"), "bdd", "cucumber-js"),
    (re.compile(r"io\.cucumber|cucumber-java|cucumber-junit"), "bdd", "cucumber-jvm"),
    (re.compile(r"^(behave|pytest-bdd)$"), "bdd", None),
    (re.compile(r"^(specflow|reqnroll)", re.I), "bdd", "specflow/reqnroll"),
    (re.compile(r"^github\.com/cucumber/godog"), "bdd", "godog"),
    (re.compile(r"^(flutter_gherkin|bdd_widget_test|gherkin)$"), "bdd", None),
    (re.compile(r"^cucumber$"), "bdd", "cucumber-rs"),
    # E2E drivers
    (re.compile(r"^@playwright/test$|^playwright$|^microsoft\.playwright", re.I), "e2e_driver", "playwright"),
    (re.compile(r"^cypress$"), "e2e_driver", "cypress"),
    (re.compile(r"^(webdriverio|@wdio/cli)$"), "e2e_driver", "webdriverio"),
    (re.compile(r"^detox$"), "e2e_driver", "detox"),
    (re.compile(r"^(appium|webdriverio-appium|io\.appium)", re.I), "e2e_driver", "appium"),
    (re.compile(r"selenium", re.I), "e2e_driver", "selenium"),
    (re.compile(r"^integration_test$"), "e2e_driver", "flutter-integration_test"),
    (re.compile(r"^patrol$"), "e2e_driver", "patrol"),
    (re.compile(r"espresso", re.I), "e2e_driver", "espresso"),
    (re.compile(r"rest-assured|restassured", re.I), "api_testing", "rest-assured"),
    (re.compile(r"^supertest$"), "api_testing", "supertest"),
    (re.compile(r"^@pact-foundation/pact$|pact-jvm|au\.com\.dius|^pact-python$", re.I), "contract", "pact"),
]

LANG_BY_MANIFEST = {
    "package.json": "javascript/typescript", "pubspec.yaml": "dart", "pyproject.toml": "python",
    "requirements.txt": "python", "setup.py": "python", "pom.xml": "java/kotlin",
    "build.gradle": "java/kotlin", "build.gradle.kts": "kotlin", "go.mod": "go",
    "Cargo.toml": "rust", "Gemfile": "ruby", "Package.swift": "swift",
}


def iter_files(root: Path, max_files: int):
    count = 0
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in SKIP_DIRS:
                    stack.append(p)
            elif p.is_file():
                yield p
                count += 1
                if count >= max_files:
                    return


def read_text(p: Path, limit: int = 2_000_000) -> str:
    try:
        return p.read_bytes()[:limit].decode("utf-8", errors="replace")
    except OSError:
        return ""


def deps_from_manifest(p: Path) -> list[str]:
    name, text = p.name, read_text(p)
    deps: list[str] = []
    if name == "package.json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            deps.extend((data.get(key) or {}).keys())
    elif name == "pubspec.yaml":
        # top-level keys of dependencies/dev_dependencies blocks (2-space indented names)
        in_block = False
        for line in text.splitlines():
            if re.match(r"^(dependencies|dev_dependencies|dependency_overrides):\s*$", line):
                in_block = True
                continue
            if in_block:
                if line and not line.startswith(" "):
                    in_block = False
                    continue
                m = re.match(r"^  ([A-Za-z0-9_]+):", line)
                if m:
                    deps.append(m.group(1))
    elif name in ("pyproject.toml", "requirements.txt", "setup.py"):
        for m in re.finditer(r"""(?m)^[\s"']*([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*(?:[<>=!~;\[,"']|$)""", text):
            deps.append(m.group(1).lower())
    elif name == "pom.xml":
        for g, a in re.findall(r"<groupId>\s*([^<\s]+)\s*</groupId>\s*<artifactId>\s*([^<\s]+)\s*</artifactId>", text):
            deps.extend([f"{g}:{a}", a])
    elif name in ("build.gradle", "build.gradle.kts"):
        for coord in re.findall(r"""["']([A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+)(?::[^"']*)?["']""", text):
            deps.extend([coord, coord.split(":")[1]])
    elif name == "go.mod":
        deps.extend(re.findall(r"(?m)^\s*(?:require\s+)?([a-z0-9.\-]+\.[a-z]+/[^\s]+)\s+v", text))
    elif name == "Cargo.toml":
        deps.extend(re.findall(r"(?m)^([A-Za-z0-9_\-]+)\s*=", text))
    elif name.endswith(".csproj"):
        deps.extend(re.findall(r'PackageReference\s+Include="([^"]+)"', text))
    return deps


def classify_deps(deps: list[str], found: dict[str, set]):
    for dep in deps:
        for rx, category, tool in DEP_RULES:
            if rx.search(dep):
                found.setdefault(category, set()).add(tool or dep.lower())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo_root")
    ap.add_argument("--max-files", type=int, default=200_000)
    ap.add_argument("--out", help="output directory (default: <repo_root>/.adlc/catalog)")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}), file=sys.stderr)
        return 2
    result = fingerprint(root, args.max_files)
    if args.stdout:
        print(json.dumps(result, indent=2))
        return 0
    out = Path(args.out) if args.out else root / ".adlc" / "catalog"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stack.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"stack": str(out / "stack.json"), "has_tests": result["has_tests"],
                      "layout": result["layout"]}, indent=2))
    return 0


def fingerprint(root: Path, max_files: int = 200_000) -> dict:
    found: dict[str, set] = {}
    languages: set[str] = set()
    manifests: list[str] = []
    configs: list[str] = []
    suffix_counts: Counter = Counter()
    test_dirs: set[str] = set()
    colocated = mirrored = 0
    ext_lang = Counter()
    EXT = {".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
           ".dart": "dart", ".py": "python", ".java": "java", ".kt": "kotlin", ".go": "go",
           ".rs": "rust", ".swift": "swift", ".cs": "csharp", ".rb": "ruby"}

    for p in iter_files(root, max_files):
        rel = p.relative_to(root).as_posix()
        parts_lower = [s.lower() for s in rel.split("/")[:-1]]
        name = p.name
        if name in LANG_BY_MANIFEST or name.endswith(".csproj"):
            manifests.append(rel)
            languages.add(LANG_BY_MANIFEST.get(name, "csharp"))
            classify_deps(deps_from_manifest(p), found)
        for rx, category, tool in RUNNER_CONFIGS:
            if rx.match(name):
                configs.append(rel)
                found.setdefault(category, set()).add(tool)
        if p.suffix in EXT:
            ext_lang[EXT[p.suffix]] += 1
        # test dirs
        for i, comp in enumerate(parts_lower):
            if comp in TEST_DIR_NAMES or comp.endswith("uitests") or comp == "androidtest":
                test_dirs.add("/".join(rel.split("/")[: i + 1]))
                break
        if "/.maestro/" in f"/{rel}" or rel.startswith(".maestro/"):
            found.setdefault("e2e_driver", set()).add("maestro")
        for label, rx in SUFFIX_PATTERNS:
            if rx.search(rel):
                suffix_counts[label] += 1
                if label == "*.feature":
                    break
                in_test_dir = any(c in TEST_DIR_NAMES or c.endswith("uitests") or c == "androidtest"
                                  for c in parts_lower) or "src/test" in rel or "/test/" in f"/{rel}"
                if in_test_dir:
                    mirrored += 1
                else:
                    colocated += 1
                break

    if any(d.lower().endswith("uitests") for d in test_dirs):
        found.setdefault("e2e_driver", set()).add("xcuitest")
    if any(d.lower().endswith("androidtest") for d in test_dirs):
        found.setdefault("e2e_driver", set()).add("espresso")
    if any(d.split("/")[-1] == "integration_test" for d in test_dirs) and "flutter" in found.get("ui", set()):
        found.setdefault("e2e_driver", set()).add("flutter-integration_test")
    if "go" in languages:
        found.setdefault("unit_runner", set()).add("go-test")
    if "rust" in languages:
        found.setdefault("unit_runner", set()).add("cargo-test")

    total = colocated + mirrored
    if total == 0:
        layout = "none"
    elif colocated / total >= 0.7:
        layout = "co-located"
    elif mirrored / total >= 0.7:
        layout = "mirrored"
    else:
        layout = "mixed"

    ui = sorted(found.get("ui", set()))
    if "react-native" in ui:
        ui = [u for u in ui if u != "react"]  # RN apps also depend on react
    return {
        "classification": "FACT",
        "source": "stack_fingerprint.py",
        "repo_root": root.name,
        "languages": sorted(languages | {l for l, n in ext_lang.items() if n >= 3}),
        "manifests": sorted(manifests),
        "runner_configs": sorted(configs),
        "ui_paradigm": ui,
        "unit_runner": sorted(found.get("unit_runner", set())),
        "component_testing": sorted(found.get("component", set())),
        "mock_libs": sorted(found.get("mock_libs", set())),
        "bdd": sorted(found.get("bdd", set())),
        "e2e_driver": sorted(found.get("e2e_driver", set())),
        "api_testing": sorted(found.get("api_testing", set())),
        "contract_testing": sorted(found.get("contract", set())),
        "layout": layout,
        "layout_counts": {"co-located": colocated, "mirrored": mirrored},
        "naming_suffixes": [s for s, _ in suffix_counts.most_common()],
        "naming_suffix_counts": dict(suffix_counts.most_common()),
        "test_dirs": sorted(test_dirs),
        "has_tests": total > 0 or suffix_counts.get("*.feature", 0) > 0,
    }


if __name__ == "__main__":
    sys.exit(main())
