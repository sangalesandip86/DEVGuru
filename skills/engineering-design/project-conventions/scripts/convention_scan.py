#!/usr/bin/env python3
"""Deterministic convention discovery for brownfield repos (plan §4.15, ADR 0005).

Scans a repository and emits a JSON conventions catalog:
  declared_standards  ADR dirs, AGENTS/CONTRIBUTING/STYLEGUIDE, lint/format/type and
                      architecture-conformance configs, each with a sha256
  toolchain           runnable commands (package.json scripts, Makefile targets,
                      pyproject tool sections, gradle/maven plugins)
  dependencies        declared dependencies classified by concern
  module_map          top-level source dirs and recognised layer dirs
  golden_files        ranked sample files near --target (tests/generated/vendor excluded)
  notes               drift notes, e.g. mixed_conventions

Stdlib only. Never executes repository code; reads files and (optionally) `git log`.
Exit codes: 0 success, 2 bad input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", "target", ".venv", "venv",
    "__pycache__", ".next", ".nuxt", ".gradle", ".idea", ".vscode", "coverage", ".dart_tool",
    "bin", "obj", ".adlc", "generated", "gen", "__generated__",
}
SOURCE_EXTS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".java", ".kt", ".kts", ".go",
    ".dart", ".cs", ".rs", ".rb", ".php", ".swift", ".scala", ".vue", ".svelte",
}
TEST_PATTERNS = [
    re.compile(p) for p in (
        r"(^|/)(tests?|__tests__|spec|specs|e2e|integration_test|testdata|fixtures)(/|$)",
        r"\.(test|spec)\.[^/]+$", r"(^|/)test_[^/]+\.py$", r"_test\.(py|go|dart)$",
        r"Tests?\.(java|kt|cs)$", r"\.d\.ts$", r"\.min\.js$", r"\.generated\.",
        r"(^|/)migrations?(/|$)",
    )
]

# --- declared standards -----------------------------------------------------
ADR_DIRS = ["docs/adr", "docs/adrs", "docs/decisions", "docs/architecture/decisions", "adr", "decisions"]
DOC_STANDARDS = [r"^AGENTS\.md$", r"^CONTRIBUTING(\..+)?$", r"^STYLEGUIDE(\..+)?$",
                 r"^STYLE_GUIDE(\..+)?$", r"^CODING_STANDARDS(\..+)?$", r"^\.editorconfig$"]
CONFIG_STANDARDS = {
    "lint": [r"^\.eslintrc(\..+)?$", r"^eslint\.config\.(js|mjs|cjs|ts)$", r"^\.ruff\.toml$",
             r"^ruff\.toml$", r"^\.flake8$", r"^\.pylintrc$", r"^pylintrc$", r"^\.golangci\.ya?ml$",
             r"^analysis_options\.yaml$", r"^detekt\.ya?ml$", r"^checkstyle\.xml$", r"^\.editorconfig$",
             r"^clippy\.toml$", r"^\.rubocop\.yml$", r"^\.stylelintrc(\..+)?$", r"^biome\.jsonc?$"],
    "format": [r"^\.prettierrc(\..+)?$", r"^prettier\.config\.(js|cjs|mjs)$", r"^rustfmt\.toml$",
               r"^\.rustfmt\.toml$", r"^\.clang-format$", r"^\.scalafmt\.conf$"],
    "type": [r"^tsconfig(\..+)?\.json$", r"^mypy\.ini$", r"^\.mypy\.ini$", r"^pyrightconfig\.json$",
             r"^Directory\.Build\.props$"],
    "arch_conformance": [r"^\.dependency-cruiser\.(js|cjs|json)$", r"^\.importlinter$",
                         r"^importlinter\.ini$", r"^\.spectral\.ya?ml$", r"^\.spectral\.json$",
                         r"^\.go-arch-lint\.ya?ml$", r"^konsist.*\.kts?$"],
}
# config sections embedded in manifests
PYPROJECT_TOOLS = {"ruff": "lint", "black": "format", "isort": "format", "mypy": "type",
                   "pyright": "type", "pylint": "lint", "importlinter": "arch_conformance",
                   "pytest": "test"}

# --- dependency concern map (keyword -> concern) ----------------------------
CONCERN_KEYWORDS = {
    "http_client": ["axios", "got", "node-fetch", "ky", "superagent", "undici", "requests", "httpx",
                    "aiohttp", "urllib3", "okhttp", "retrofit", "feign", "webclient", "resty", "dio",
                    "reqwest", "restsharp", "refit"],
    "orm": ["prisma", "@prisma/client", "typeorm", "sequelize", "mikro-orm", "drizzle-orm", "knex",
            "mongoose", "sqlalchemy", "django", "peewee", "tortoise-orm", "hibernate",
            "spring-boot-starter-data-jpa", "mybatis", "jooq", "exposed", "gorm", "sqlx", "ent",
            "diesel", "sea-orm", "entityframeworkcore", "dapper", "drift", "floor"],
    "logging": ["winston", "pino", "bunyan", "log4js", "loglevel", "structlog", "loguru",
                "logback", "logback-classic", "slf4j", "slf4j-api", "log4j", "log4j-core",
                "zap", "zerolog", "logrus", "tracing", "env_logger", "serilog", "nlog", "logger"],
    "telemetry": ["@opentelemetry/api", "opentelemetry-api", "opentelemetry-sdk", "micrometer",
                  "prom-client", "prometheus-client", "dd-trace", "newrelic", "@sentry/node", "sentry-sdk"],
    "di": ["inversify", "tsyringe", "typedi", "awilix", "@nestjs/core", "dependency-injector",
           "injector", "dagger", "hilt", "koin", "guice", "spring-context", "spring-boot-starter",
           "wire", "fx", "get_it", "injectable", "riverpod", "autofac"],
    "validation": ["zod", "joi", "yup", "class-validator", "ajv", "valibot", "pydantic",
                   "marshmallow", "cerberus", "hibernate-validator", "jakarta.validation-api",
                   "validator", "go-playground/validator", "fluentvalidation"],
    "feature_flags": ["launchdarkly", "launchdarkly-node-server-sdk", "@launchdarkly/node-server-sdk",
                      "unleash-client", "unleash", "flagsmith", "growthbook", "@growthbook/growthbook",
                      "split", "configcat", "openfeature", "@openfeature/server-sdk"],
    "web_framework": ["express", "fastify", "koa", "@nestjs/core", "hapi", "next", "flask",
                      "fastapi", "django", "starlette", "spring-boot-starter-web", "ktor", "gin",
                      "echo", "fiber", "chi", "actix-web", "axum", "rocket"],
    "messaging": ["kafkajs", "amqplib", "bullmq", "bull", "@aws-sdk/client-sqs", "confluent-kafka",
                  "kafka-python", "pika", "celery", "spring-kafka", "spring-boot-starter-amqp",
                  "sarama", "nats", "lapin", "rdkafka", "masstransit"],
    "config": ["dotenv", "convict", "config", "@nestjs/config", "pydantic-settings", "python-dotenv",
               "dynaconf", "viper", "envconfig", "figment"],
    "i18n": ["i18next", "react-intl", "vue-i18n", "@angular/localize", "babel", "flask-babel",
             "intl", "easy_localization", "fluent"],
    "state_management": ["redux", "@reduxjs/toolkit", "zustand", "mobx", "pinia", "vuex", "recoil",
                         "jotai", "flutter_bloc", "bloc", "provider", "riverpod", "get"],
}
# concerns where >1 library is a drift signal (some, e.g. telemetry, legitimately combine)
SINGLE_CHOICE_CONCERNS = {"http_client", "orm", "logging", "di", "validation", "feature_flags",
                          "web_framework", "state_management"}

LAYER_NAMES = {
    "controllers": "presentation", "controller": "presentation", "handlers": "presentation",
    "routes": "presentation", "api": "presentation", "web": "presentation", "views": "presentation",
    "ui": "presentation", "pages": "presentation", "components": "presentation", "screens": "presentation",
    "services": "application", "service": "application", "usecases": "application",
    "use_cases": "application", "application": "application",
    "domain": "domain", "models": "domain", "entities": "domain", "core": "domain",
    "repositories": "persistence", "repository": "persistence", "repo": "persistence", "dal": "persistence",
    "persistence": "persistence", "db": "persistence", "data": "persistence",
    "infra": "infrastructure", "infrastructure": "infrastructure", "adapters": "infrastructure",
    "clients": "infrastructure", "config": "configuration", "shared": "shared", "common": "shared",
    "utils": "shared", "lib": "shared",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_test_or_generated(relpath: str) -> bool:
    return any(p.search(relpath) for p in TEST_PATTERNS)


def walk_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".git"))
        for name in sorted(filenames):
            yield Path(dirpath) / name


# --- declared standards -----------------------------------------------------
def find_declared_standards(root: Path, files: list[Path]) -> dict:
    out = {"adr_dirs": [], "docs": [], "lint": [], "format": [], "type": [], "arch_conformance": [],
           "manifest_sections": []}
    for d in ADR_DIRS:
        p = root / d
        if p.is_dir():
            adrs = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in {".md", ".adoc", ".rst"})
            out["adr_dirs"].append({
                "path": d,
                "count": len(adrs),
                "files": [{"path": rel(f, root), "sha256": sha256_file(f)} for f in adrs],
            })
    doc_res = [re.compile(p, re.I) for p in DOC_STANDARDS]
    cfg_res = {k: [re.compile(p) for p in v] for k, v in CONFIG_STANDARDS.items()}
    for f in files:
        r = rel(f, root)
        if is_test_or_generated(r):
            continue
        name = f.name
        if any(rx.match(name) for rx in doc_res):
            out["docs"].append({"path": r, "sha256": sha256_file(f)})
        for kind, rxs in cfg_res.items():
            if any(rx.match(name) for rx in rxs):
                out[kind].append({"path": r, "sha256": sha256_file(f)})
    # embedded config sections
    pyproject = root / "pyproject.toml"
    data = load_toml(pyproject)
    for tool in sorted((data.get("tool") or {}).keys()):
        if tool in PYPROJECT_TOOLS:
            out["manifest_sections"].append({"path": "pyproject.toml", "section": f"tool.{tool}",
                                             "kind": PYPROJECT_TOOLS[tool]})
    pkg = load_json(root / "package.json")
    for key in ("eslintConfig", "prettier", "dependency-cruiser"):
        if key in pkg:
            out["manifest_sections"].append({"path": "package.json", "section": key,
                                             "kind": "format" if key == "prettier" else "lint"})
    return out


def load_toml(path: Path) -> dict:
    if not path.is_file() or tomllib is None:
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


# --- toolchain --------------------------------------------------------------
TOOL_SCRIPT_KEYS = re.compile(r"^(lint|format|fmt|typecheck|type-check|types|check|test|build|arch|depcruise|prettier|eslint)(:.*)?$")


def find_toolchain(root: Path) -> list[dict]:
    cmds: list[dict] = []
    pkg = load_json(root / "package.json")
    runner = "npm run"
    if (root / "pnpm-lock.yaml").is_file():
        runner = "pnpm"
    elif (root / "yarn.lock").is_file():
        runner = "yarn"
    for name, body in sorted((pkg.get("scripts") or {}).items()):
        if TOOL_SCRIPT_KEYS.match(name):
            cmds.append({"source": "package.json", "name": name, "command": f"{runner} {name}", "runs": body})
    mk = root / "Makefile"
    if mk.is_file():
        for line in mk.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", line)
            if m and TOOL_SCRIPT_KEYS.match(m.group(1)):
                cmds.append({"source": "Makefile", "name": m.group(1), "command": f"make {m.group(1)}"})
    data = load_toml(root / "pyproject.toml")
    tool_cmd = {"ruff": "ruff check .", "black": "black --check .", "isort": "isort --check-only .",
                "mypy": "mypy .", "pyright": "pyright", "pylint": "pylint <package>",
                "importlinter": "lint-imports", "pytest": "pytest"}
    for tool in sorted((data.get("tool") or {}).keys()):
        if tool in tool_cmd:
            cmds.append({"source": "pyproject.toml", "name": tool, "command": tool_cmd[tool]})
    for gname in ("build.gradle", "build.gradle.kts"):
        g = root / gname
        if g.is_file():
            text = g.read_text(encoding="utf-8", errors="replace")
            for plugin, task in (("checkstyle", "checkstyleMain"), ("spotless", "spotlessCheck"),
                                 ("detekt", "detekt"), ("ktlint", "ktlintCheck"), ("pmd", "pmdMain"),
                                 ("spotbugs", "spotbugsMain"), ("archunit", "test")):
                if plugin in text.lower():
                    cmds.append({"source": gname, "name": plugin, "command": f"./gradlew {task}"})
    pom = root / "pom.xml"
    if pom.is_file():
        text = pom.read_text(encoding="utf-8", errors="replace").lower()
        for plugin, goal in (("maven-checkstyle-plugin", "checkstyle:check"), ("spotless-maven-plugin", "spotless:check"),
                             ("maven-pmd-plugin", "pmd:check"), ("spotbugs-maven-plugin", "spotbugs:check"),
                             ("archunit", "test")):
            if plugin in text:
                cmds.append({"source": "pom.xml", "name": plugin, "command": f"mvn {goal}"})
    if (root / "go.mod").is_file():
        cmds.append({"source": "go.mod", "name": "vet", "command": "go vet ./..."})
        if any((root / n).is_file() for n in (".golangci.yml", ".golangci.yaml")):
            cmds.append({"source": ".golangci.yml", "name": "golangci-lint", "command": "golangci-lint run"})
    if (root / "Cargo.toml").is_file():
        cmds += [{"source": "Cargo.toml", "name": "clippy", "command": "cargo clippy -- -D warnings"},
                 {"source": "Cargo.toml", "name": "fmt", "command": "cargo fmt --check"}]
    if (root / "pubspec.yaml").is_file():
        cmds.append({"source": "pubspec.yaml", "name": "analyze", "command": "dart analyze"})
    return cmds


# --- dependencies -----------------------------------------------------------
def declared_dependencies(root: Path) -> list[tuple[str, str]]:
    """Return (name, manifest) pairs, lower-cased names."""
    deps: list[tuple[str, str]] = []
    pkg = load_json(root / "package.json")
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for name in (pkg.get(section) or {}):
            deps.append((name.lower(), "package.json"))
    data = load_toml(root / "pyproject.toml")
    proj = data.get("project") or {}
    for spec in proj.get("dependencies") or []:
        deps.append((re.split(r"[\s<>=!~;\[]", spec, maxsplit=1)[0].lower(), "pyproject.toml"))
    poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
    for name in poetry:
        if name.lower() != "python":
            deps.append((name.lower(), "pyproject.toml"))
    for reqf in ("requirements.txt", "requirements-dev.txt"):
        p = root / reqf
        if p.is_file():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-")):
                    deps.append((re.split(r"[\s<>=!~;\[]", line, maxsplit=1)[0].lower(), reqf))
    gomod = root / "go.mod"
    if gomod.is_file():
        for m in re.finditer(r"^\s*(?:require\s+)?([a-z0-9.\-]+\.[a-z]+/[^\s]+)\s+v", gomod.read_text(encoding="utf-8", errors="replace"), re.M):
            deps.append((m.group(1).lower(), "go.mod"))
    cargo = load_toml(root / "Cargo.toml")
    for name in (cargo.get("dependencies") or {}):
        deps.append((name.lower(), "Cargo.toml"))
    pom = root / "pom.xml"
    if pom.is_file():
        try:
            tree = ET.parse(pom)
            for el in tree.iter():
                if el.tag.endswith("artifactId") and el.text:
                    deps.append((el.text.strip().lower(), "pom.xml"))
        except ET.ParseError:
            pass
    for gname in ("build.gradle", "build.gradle.kts"):
        g = root / gname
        if g.is_file():
            for m in re.finditer(r"""['"]([\w.\-]+):([\w.\-]+)(?::[^'"]*)?['"]""", g.read_text(encoding="utf-8", errors="replace")):
                deps.append((m.group(2).lower(), gname))
    pub = root / "pubspec.yaml"
    if pub.is_file():
        in_deps = False
        for line in pub.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^(dev_)?dependencies:\s*$", line):
                in_deps = True
                continue
            if in_deps and re.match(r"^\S", line):
                in_deps = False
            m = re.match(r"^  ([a-z0-9_]+):", line)
            if in_deps and m:
                deps.append((m.group(1), "pubspec.yaml"))
    for cs in root.glob("*.csproj"):
        for m in re.finditer(r'PackageReference\s+Include="([^"]+)"', cs.read_text(encoding="utf-8", errors="replace")):
            deps.append((m.group(1).lower(), cs.name))
    return deps


def classify_dependencies(deps: list[tuple[str, str]]) -> dict:
    by_concern: dict[str, list[dict]] = {}
    seen = set()
    for name, manifest in deps:
        for concern, keys in CONCERN_KEYWORDS.items():
            short = name.rsplit("/", 1)[-1]
            if name in keys or short in keys or any(name.endswith("/" + k) for k in keys):
                key = (concern, name)
                if key in seen:
                    continue
                seen.add(key)
                by_concern.setdefault(concern, []).append({"name": name, "manifest": manifest})
    return {k: sorted(v, key=lambda d: d["name"]) for k, v in sorted(by_concern.items())}


# --- module map -------------------------------------------------------------
def module_map(root: Path, source_files: list[str]) -> dict:
    top: dict[str, int] = {}
    layers: dict[str, dict] = {}
    for r in source_files:
        parts = r.split("/")
        if len(parts) > 1:
            top[parts[0]] = top.get(parts[0], 0) + 1
        for i, part in enumerate(parts[:-1]):
            layer = LAYER_NAMES.get(part.lower())
            if layer:
                d = "/".join(parts[: i + 1])
                entry = layers.setdefault(d, {"dir": d, "layer": layer, "files": 0})
                entry["files"] += 1
    return {
        "top_level_dirs": [{"dir": k, "source_files": v} for k, v in sorted(top.items())],
        "layers": sorted(layers.values(), key=lambda e: e["dir"]),
        "layout": "feature-folders" if _looks_feature_foldered(layers) else ("layer-folders" if layers else "flat"),
    }


def _looks_feature_foldered(layers: dict) -> bool:
    # same layer name appearing under several different parents → features each own their layers
    parents: dict[str, set] = {}
    for d in layers:
        name = d.rsplit("/", 1)[-1]
        parent = d.rsplit("/", 1)[0] if "/" in d else ""
        parents.setdefault(name, set()).add(parent)
    return any(len(p) >= 2 for p in parents.values())


# --- golden files -----------------------------------------------------------
IMPORT_RX = re.compile(r"""(?:from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|^\s*from\s+([\w.]+)\s+import|^\s*import\s+([\w.]+))""", re.M)


def git_recency(root: Path) -> dict[str, int]:
    """Map relpath -> rank (0 = most recently committed). Empty if git unavailable."""
    try:
        res = subprocess.run(["git", "-C", str(root), "log", "--name-only", "--pretty=format:", "-n", "500"],
                             capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return {}
    if res.returncode != 0:
        return {}
    order: dict[str, int] = {}
    for line in res.stdout.splitlines():
        line = line.strip()
        if line and line not in order:
            order[line] = len(order)
    return order


def import_counts(root: Path, source_files: list[str]) -> dict[str, int]:
    """Approximate in-repo fan-in: how many files import each file (by stem/module path)."""
    stems: dict[str, list[str]] = {}
    for r in source_files:
        p = Path(r)
        stems.setdefault(p.stem, []).append(r)
        mod = r.rsplit(".", 1)[0].replace("/", ".")
        stems.setdefault(mod, []).append(r)
    counts = {r: 0 for r in source_files}
    for r in source_files:
        try:
            text = (root / r).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in IMPORT_RX.finditer(text):
            target = next(g for g in m.groups() if g)
            last = target.rstrip("/").rsplit("/", 1)[-1]
            keys = {last, last.rsplit(".", 1)[-1], target.lstrip("./").replace("/", ".")}
            for k in keys:
                for hit in stems.get(k, []):
                    if hit != r:
                        counts[hit] += 1
    return counts


def junit_passing(path: Path | None) -> tuple[set[str], set[str]]:
    """Return (passing, failing) sets of classname/file hints from a JUnit XML."""
    if not path:
        return set(), set()
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError):
        return set(), set()
    passing, failing = set(), set()
    for tc in tree.iter("testcase"):
        hint = (tc.get("file") or tc.get("classname") or "").replace("\\", "/")
        if not hint:
            continue
        bad = any(child.tag in {"failure", "error", "skipped"} for child in tc)
        (failing if bad else passing).add(hint)
    return passing, failing


def rank_golden_files(root: Path, source_files: list[str], target: str | None, junit: Path | None,
                      limit: int = 5) -> list[dict]:
    if not target:
        return []
    target = target.replace("\\", "/").strip("/")
    tpath = Path(target)
    t_is_dir = (root / target).is_dir()
    t_dir = target if t_is_dir else tpath.parent.as_posix()
    t_suffix = "" if t_is_dir else "".join(tpath.suffixes[-2:]) if len(tpath.suffixes) > 1 else tpath.suffix
    t_layer = next((LAYER_NAMES[p.lower()] for p in reversed(t_dir.split("/")) if p.lower() in LAYER_NAMES), None)
    recency = git_recency(root)
    fanin = import_counts(root, source_files)
    passing, failing = junit_passing(junit)
    scored = []
    for r in source_files:
        if r == target:
            continue
        p = Path(r)
        d = p.parent.as_posix()
        score, why = 0.0, []
        if d == t_dir:
            score += 40; why.append("same_dir")
        elif t_dir and (d.startswith(t_dir + "/") or t_dir.startswith(d + "/")):
            score += 20; why.append("near_dir")
        layer = next((LAYER_NAMES[x.lower()] for x in reversed(d.split("/")) if x.lower() in LAYER_NAMES), None)
        if t_layer and layer == t_layer:
            score += 25; why.append(f"same_layer:{layer}")
        suffix = "".join(p.suffixes[-2:]) if len(p.suffixes) > 1 else p.suffix
        if t_suffix and suffix == t_suffix:
            score += 15; why.append("same_suffix")
        elif t_suffix and p.suffix == tpath.suffix:
            score += 8; why.append("same_extension")
        if r in recency:
            bonus = max(0.0, 10.0 - recency[r] / 10.0)
            score += bonus; why.append(f"recent_rank:{recency[r]}")
        if fanin.get(r):
            score += min(10, fanin[r] * 2); why.append(f"imported_by:{fanin[r]}")
        stem = p.stem
        if any(stem in h or r in h for h in failing):
            score -= 30; why.append("failing_in_junit")
        elif any(stem in h or r in h for h in passing):
            score += 5; why.append("passing_in_junit")
        if score > 0:
            scored.append({"path": r, "score": round(score, 2), "reasons": why,
                           "sha256": sha256_file(root / r)})
    scored.sort(key=lambda e: (-e["score"], e["path"]))
    return scored[:limit]


# --- main -------------------------------------------------------------------
def scan(root: Path, target: str | None = None, junit: Path | None = None, golden_limit: int = 5) -> dict:
    files = list(walk_files(root))
    rels = [rel(f, root) for f in files]
    source_files = [r for r in rels if Path(r).suffix in SOURCE_EXTS and not is_test_or_generated(r)]
    deps = classify_dependencies(declared_dependencies(root))
    notes = []
    for concern, libs in deps.items():
        if concern in SINGLE_CHOICE_CONCERNS and len(libs) > 1:
            notes.append({"type": "mixed_conventions", "concern": concern,
                          "libraries": [lib["name"] for lib in libs],
                          "guidance": "follow the library dominant in the target's module; record drift as RISK; never add another"})
    declared = find_declared_standards(root, files)
    if not declared["arch_conformance"] and not any(s["kind"] == "arch_conformance" for s in declared["manifest_sections"]):
        notes.append({"type": "no_arch_conformance",
                      "guidance": "boundaries are observed only; recommend a conformance tool as a TECHNICAL_STORY"})
    if not declared["adr_dirs"]:
        notes.append({"type": "no_adr_dir", "guidance": "propose docs/adr/ for deviation ADRs"})
    return {
        "schema": "adlc.conventions/v1",
        "repo": str(root),
        "target": target,
        "greenfield": not source_files,
        "declared_standards": declared,
        "toolchain": find_toolchain(root),
        "dependencies": deps,
        "module_map": module_map(root, source_files),
        "golden_files": rank_golden_files(root, source_files, target, junit, golden_limit),
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".", help="repository root (default: .)")
    ap.add_argument("--target", help="file or dir you will change (repo-relative) — enables golden-file ranking")
    ap.add_argument("--junit", help="optional JUnit XML; prefer files whose tests pass")
    ap.add_argument("--golden-limit", type=int, default=5)
    ap.add_argument("--out", help="write JSON here (use '-' for stdout; default .adlc/catalog/conventions.json under --repo)")
    args = ap.parse_args(argv)
    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"repo not found: {root}"}), file=sys.stderr)
        return 2
    result = scan(root, args.target, Path(args.junit) if args.junit else None, args.golden_limit)
    text = json.dumps(result, indent=2, sort_keys=False)
    if args.out == "-":
        print(text)
    else:
        out = Path(args.out) if args.out else root / ".adlc" / "catalog" / "conventions.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(json.dumps({"written": str(out), "golden_files": len(result["golden_files"]),
                          "notes": [n["type"] for n in result["notes"]]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
