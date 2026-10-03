#!/usr/bin/env python3
"""CI check: every new dependency or major-version bump is backed by a DECISION.

Plan v3.1 §4.15 / ADR 0005: on an existing codebase a new dependency is a deviation from the
project's standards. It needs a DECISION with a short ADR (architect REVIEWED) and
`human:tech-lead` APPROVAL. This check enforces the machine-checkable part: a dependency-
manifest diff that isn't linked to a DECISION fails. The human APPROVAL itself is enforced by
CODEOWNERS review on the PR, not here.

Manifests: package.json, pyproject.toml, requirements*.txt, pom.xml, build.gradle(.kts),
go.mod, Cargo.toml, pubspec.yaml, *.csproj.

A dependency change is covered when its package name appears in either
  * a DECISION entry in an Evidence Ledger export (--evidence, JSON list or {"entries": [...]},
    lifecycle_state not REJECTED), or
  * an ADR file added/changed in the same diff (path containing `adr/` or `decisions/`).

Usage:
  check_dependency_decisions.py --base REF [--head REF] [--repo DIR] [--evidence FILE]
  check_dependency_decisions.py --base-dir DIR --head-dir DIR [--evidence FILE]
Exit codes: 0 = pass, 1 = dependency change without a DECISION, 2 = bad input.
Removals and minor/patch bumps are reported as info and never fail the check
(`--strict-removals` makes removals require a DECISION too).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover — 3.10 fallback below
    tomllib = None  # type: ignore[assignment]

Deps = dict[str, str | None]  # package name -> version spec (None if unpinned / path / git)


# --------------------------------------------------------------------------- manifest kinds

def manifest_kind(path: str) -> str | None:
    name = PurePosixPath(path).name
    low = name.lower()
    if low == "package.json":
        return "npm"
    if low == "pyproject.toml":
        return "pypi-pyproject"
    if re.fullmatch(r"requirements[\w.\-]*\.(txt|in)", low):
        return "pypi-requirements"
    if low == "pom.xml":
        return "maven"
    if low in ("build.gradle", "build.gradle.kts"):
        return "gradle"
    if low == "go.mod":
        return "go"
    if low == "cargo.toml":
        return "cargo"
    if low == "pubspec.yaml":
        return "pub"
    if low.endswith(".csproj"):
        return "nuget"
    return None


ECOSYSTEM = {"pypi-pyproject": "pypi", "pypi-requirements": "pypi", "gradle": "maven"}


# --------------------------------------------------------------------------- parsers

def _norm_py(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.split("[")[0].strip()).lower()


PEP508 = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*(?:\[[^\]]*\])?)\s*(.*)$")


def _pep508(req: str) -> tuple[str, str | None] | None:
    req = req.split(";")[0].split("#")[0].strip()
    m = PEP508.match(req)
    if not m or not m.group(1):
        return None
    spec = m.group(2).strip() or None
    return _norm_py(m.group(1)), spec


def parse_npm(text: str) -> Deps:
    data = json.loads(text)
    deps: Deps = {}
    for sec in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, ver in (data.get(sec) or {}).items():
            deps[name] = str(ver)
    return deps


def parse_requirements(text: str) -> Deps:
    deps: Deps = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")) or "://" in line:
            continue
        parsed = _pep508(line)
        if parsed:
            deps[parsed[0]] = parsed[1]
    return deps


def _toml(text: str) -> dict:
    if tomllib is not None:
        return tomllib.loads(text)
    raise RuntimeError("TOML parsing needs Python 3.11+ (tomllib)")


def parse_pyproject(text: str) -> Deps:
    data = _toml(text)
    deps: Deps = {}
    project = data.get("project", {})
    reqs = list(project.get("dependencies", []))
    for group in (project.get("optional-dependencies") or {}).values():
        reqs += group
    for group in (data.get("dependency-groups") or {}).values():
        reqs += [r for r in group if isinstance(r, str)]
    for r in reqs:
        parsed = _pep508(r)
        if parsed:
            deps[parsed[0]] = parsed[1]
    poetry = data.get("tool", {}).get("poetry", {})
    tables = [poetry.get("dependencies", {}), poetry.get("dev-dependencies", {})]
    tables += [g.get("dependencies", {}) for g in (poetry.get("group") or {}).values()]
    for table in tables:
        for name, spec in table.items():
            if name.lower() == "python":
                continue
            deps[_norm_py(name)] = spec if isinstance(spec, str) else (spec.get("version") if isinstance(spec, dict) else None)
    return deps


def _strip_ns(root: ET.Element) -> None:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def parse_pom(text: str) -> Deps:
    root = ET.fromstring(text)
    _strip_ns(root)
    props = {}
    for p in root.findall("./properties/*"):
        props[p.tag] = (p.text or "").strip()
    if root.find("./version") is not None:
        props["project.version"] = (root.findtext("./version") or "").strip()
    deps: Deps = {}
    for d in root.iter("dependency"):
        g, a = (d.findtext("groupId") or "").strip(), (d.findtext("artifactId") or "").strip()
        if not a:
            continue
        v = (d.findtext("version") or "").strip() or None
        if v:
            v = re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), v)
        deps[f"{g}:{a}"] = v
    return deps


GRADLE_DEP = re.compile(
    r"\b(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testRuntimeOnly|"
    r"testCompileOnly|androidTestImplementation|debugImplementation|kapt|ksp|annotationProcessor|classpath)"
    r"\s*\(?\s*(?:platform\s*\(\s*)?[\"']([^:\"'\s]+):([^:\"'\s]+)(?::([^\"'\s]+))?[\"']"
)


def parse_gradle(text: str) -> Deps:
    return {f"{g}:{a}": (v or None) for g, a, v in GRADLE_DEP.findall(text)}


def parse_gomod(text: str) -> Deps:
    deps: Deps = {}
    in_block = False
    for raw in text.splitlines():
        line = raw.split("//")[0].strip()
        if not line:
            continue
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if line.startswith("require "):
            line = line[len("require "):].strip()
        elif not in_block:
            continue
        parts = line.split()
        if len(parts) >= 2:
            deps[parts[0]] = parts[1]
    return deps


def parse_cargo(text: str) -> Deps:
    data = _toml(text)
    deps: Deps = {}
    tables = [data.get(k, {}) for k in ("dependencies", "dev-dependencies", "build-dependencies")]
    tables.append((data.get("workspace") or {}).get("dependencies", {}))
    for target in (data.get("target") or {}).values():
        tables += [target.get(k, {}) for k in ("dependencies", "dev-dependencies", "build-dependencies")]
    for table in tables:
        for name, spec in table.items():
            deps[name] = spec if isinstance(spec, str) else (spec.get("version") if isinstance(spec, dict) else None)
    return deps


def parse_pubspec(text: str) -> Deps:
    """Minimal YAML reader for the dependency sections of pubspec.yaml (no PyYAML)."""
    deps: Deps = {}
    section = None
    child_indent = None
    for raw in text.splitlines():
        line = raw.split(" #")[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            key = line.split(":")[0].strip()
            section = key if key in ("dependencies", "dev_dependencies", "dependency_overrides") else None
            child_indent = None
            continue
        if section is None:
            continue
        if child_indent is None:
            child_indent = indent
        if indent != child_indent:
            continue  # nested (sdk:, path:, git:, version:) — handled below
        name, _, val = line.strip().partition(":")
        val = val.strip().strip("'\"") or None
        deps[name.strip()] = val
    # `name:\n    version: ^1.2.0` form
    for m in re.finditer(r"^\s+([A-Za-z0-9_]+):\s*\n\s+version:\s*['\"]?([^'\"\n]+)", text, re.M):
        if m.group(1) in deps:
            deps[m.group(1)] = m.group(2).strip()
    # SDK pseudo-dependencies (`flutter: {sdk: flutter}`) are not packages.
    for m in re.finditer(r"^\s+([A-Za-z0-9_]+):\s*\n\s+sdk:", text, re.M):
        deps.pop(m.group(1), None)
    return deps


def parse_csproj(text: str) -> Deps:
    root = ET.fromstring(text)
    _strip_ns(root)
    deps: Deps = {}
    for ref in root.iter("PackageReference"):
        name = ref.get("Include") or ref.get("Update")
        if not name:
            continue
        ver = ref.get("Version") or (ref.findtext("Version") or "").strip() or None
        deps[name] = ver
    return deps


PARSERS = {
    "npm": parse_npm, "pypi-requirements": parse_requirements, "pypi-pyproject": parse_pyproject,
    "maven": parse_pom, "gradle": parse_gradle, "go": parse_gomod, "cargo": parse_cargo,
    "pub": parse_pubspec, "nuget": parse_csproj,
}


# --------------------------------------------------------------------------- diffing

def major_of(version: str | None) -> tuple[int, int] | None:
    """Return (major, minor) from a version spec like '^1.2.3', '>=2.0', 'v1.4.0', '1.0.0-rc'."""
    if not version:
        return None
    m = re.search(r"(\d+)(?:\.(\d+))?", version)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2) or 0)


def is_major_bump(old: str | None, new: str | None) -> bool:
    a, b = major_of(old), major_of(new)
    if a is None or b is None:
        return False
    if b[0] > a[0]:
        return True
    return a[0] == 0 and b[0] == 0 and b[1] > a[1]  # 0.x: a minor bump is breaking under semver


@dataclass
class Change:
    file: str
    ecosystem: str
    package: str
    change: str            # added | major_upgrade | removed | upgraded | downgraded | changed
    from_version: str | None
    to_version: str | None
    requires_decision: bool


def diff_manifest(path: str, kind: str, base_text: str | None, head_text: str | None,
                  strict_removals: bool = False) -> list[Change]:
    parse = PARSERS[kind]
    base = parse(base_text) if base_text else {}
    head = parse(head_text) if head_text else {}
    eco = ECOSYSTEM.get(kind, kind)
    out: list[Change] = []
    for name in sorted(set(base) | set(head)):
        if name not in base:
            out.append(Change(path, eco, name, "added", None, head[name], True))
        elif name not in head:
            out.append(Change(path, eco, name, "removed", base[name], None, strict_removals))
        elif base[name] != head[name]:
            if is_major_bump(base[name], head[name]):
                out.append(Change(path, eco, name, "major_upgrade", base[name], head[name], True))
            else:
                a, b = major_of(base[name]), major_of(head[name])
                kind_ = "downgraded" if a and b and b < a else ("upgraded" if a and b else "changed")
                out.append(Change(path, eco, name, kind_, base[name], head[name], False))
    return out


# --------------------------------------------------------------------------- decisions

def name_variants(change: Change) -> list[str]:
    names = [change.package]
    if change.ecosystem == "maven" and ":" in change.package:
        names.append(change.package.split(":", 1)[1])
    if change.ecosystem == "npm" and change.package.startswith("@") and "/" in change.package:
        names.append(change.package.split("/", 1)[1])
    if change.ecosystem == "go":
        segs = [s for s in change.package.split("/") if not re.fullmatch(r"v\d+", s)]
        if segs:
            names.append(segs[-1])
    return list(dict.fromkeys(names))


def mentions(text: str, name: str) -> bool:
    rx = r"(?<![A-Za-z0-9_.\-/@])" + re.escape(name) + r"(?![A-Za-z0-9_\-])"
    if re.search(rx, text, re.IGNORECASE):
        return True
    if "-" in name or "_" in name or "." in name:  # python normalisation: foo-bar ≈ foo_bar ≈ foo.bar
        flex = "[-_.]".join(re.escape(part) for part in re.split(r"[-_.]", name))
        return bool(re.search(r"(?<![A-Za-z0-9_.\-/@])" + flex + r"(?![A-Za-z0-9_\-])", text, re.IGNORECASE))
    return False


@dataclass
class DecisionSource:
    ref: str
    text: str


def load_evidence(path: Path | None) -> list[DecisionSource]:
    if not path:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", data) if isinstance(data, dict) else data
    out = []
    for e in entries:
        if not isinstance(e, dict) or str(e.get("classification", "")).upper() != "DECISION":
            continue
        if str(e.get("lifecycle_state", "")).upper() == "REJECTED":
            continue
        text = " ".join(str(e.get(k, "")) for k in ("content", "source", "title", "rationale"))
        out.append(DecisionSource(f"ledger:{e.get('entry_id', '?')}", text))
    return out


def is_adr_path(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    return p.endswith(".md") and ("/adr/" in f"/{p}" or "/adrs/" in f"/{p}" or "/decisions/" in f"/{p}")


# --------------------------------------------------------------------------- sources

class GitSource:
    def __init__(self, repo: Path, base: str, head: str):
        self.repo, self.base, self.head = repo, base, head

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    def changed_files(self) -> list[str]:
        proc = self._git("diff", "--name-only", "--no-renames", f"{self.base}...{self.head}")
        if proc.returncode != 0:
            proc = self._git("diff", "--name-only", "--no-renames", self.base, self.head)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())
        return [ln for ln in proc.stdout.splitlines() if ln.strip()]

    def read(self, side: str, path: str) -> str | None:
        ref = self.base if side == "base" else self.head
        proc = self._git("show", f"{ref}:{path}")
        return proc.stdout if proc.returncode == 0 else None


class DirSource:
    def __init__(self, base: Path, head: Path):
        self.base_dir, self.head_dir = base, head
        self.base, self.head = str(base), str(head)

    @staticmethod
    def _files(root: Path) -> dict[str, Path]:
        out = {}
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in {".git", "node_modules", ".venv", "target", "build"}]
            for fn in fns:
                full = Path(dp) / fn
                out[full.relative_to(root).as_posix()] = full
        return out

    def changed_files(self) -> list[str]:
        b, h = self._files(self.base_dir), self._files(self.head_dir)
        changed = []
        for rel in sorted(set(b) | set(h)):
            if rel not in b or rel not in h or b[rel].read_bytes() != h[rel].read_bytes():
                changed.append(rel)
        return changed

    def read(self, side: str, path: str) -> str | None:
        p = (self.base_dir if side == "base" else self.head_dir) / path
        return p.read_text(encoding="utf-8") if p.exists() else None


# --------------------------------------------------------------------------- main

def run(source, evidence: list[DecisionSource], strict_removals: bool = False) -> dict:
    changed = source.changed_files()
    decisions = list(evidence)
    for path in changed:
        if is_adr_path(path):
            text = source.read("head", path)
            if text:
                decisions.append(DecisionSource(f"adr:{path}", text))
    findings, manifests, errors = [], [], []
    for path in changed:
        kind = manifest_kind(path)
        if not kind:
            continue
        manifests.append(path)
        try:
            changes = diff_manifest(path, kind, source.read("base", path), source.read("head", path), strict_removals)
        except Exception as exc:  # noqa: BLE001 — unparseable manifest is a finding, fail-safe
            errors.append({"file": path, "error": f"could not parse manifest: {exc}"})
            continue
        for c in changes:
            refs = [d.ref for d in decisions if any(mentions(d.text, n) for n in name_variants(c))]
            status = "info" if not c.requires_decision else ("ok" if refs else "missing_decision")
            findings.append({
                "file": c.file, "ecosystem": c.ecosystem, "package": c.package, "change": c.change,
                "from": c.from_version, "to": c.to_version, "requires_decision": c.requires_decision,
                "decision_refs": refs, "status": status,
            })
    missing = [f for f in findings if f["status"] == "missing_decision"]
    return {
        "check": "dependency-decision-check",
        "ok": not missing and not errors,
        "base": source.base, "head": source.head,
        "manifests_changed": manifests,
        "decisions_considered": [d.ref for d in decisions],
        "missing_decision_count": len(missing),
        "findings": findings,
        "errors": errors,
        "note": "A DECISION link is necessary, not sufficient: human:tech-lead APPROVAL is enforced by CODEOWNERS review (plan v3.1 §4.15).",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="base git ref (e.g. origin/main)")
    ap.add_argument("--head", default="HEAD", help="head git ref (default HEAD)")
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--base-dir", type=Path, help="compare directory trees instead of git refs")
    ap.add_argument("--head-dir", type=Path)
    ap.add_argument("--evidence", type=Path, help="Evidence Ledger export (JSON) with DECISION entries")
    ap.add_argument("--strict-removals", action="store_true", help="removed dependencies also need a DECISION")
    args = ap.parse_args(argv)
    try:
        if args.base_dir or args.head_dir:
            if not (args.base_dir and args.head_dir):
                raise ValueError("--base-dir and --head-dir must be given together")
            source = DirSource(args.base_dir, args.head_dir)
        elif args.base:
            source = GitSource(args.repo, args.base, args.head)
        else:
            raise ValueError("give --base REF or --base-dir/--head-dir")
        report = run(source, load_evidence(args.evidence), args.strict_removals)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"check": "dependency-decision-check", "ok": False, "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and not report["ok"]:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Dependency changes without a DECISION (plan v3.1 §4.15)\n\n")
            for f in report["findings"]:
                if f["status"] == "missing_decision":
                    fh.write(f"- `{f['package']}` ({f['change']} {f['from'] or ''}→{f['to'] or ''}) in `{f['file']}`\n")
            for e in report["errors"]:
                fh.write(f"- `{e['file']}`: {e['error']}\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
