#!/usr/bin/env python3
"""Static import scan for dependency discovery (plan §4.5, §5.3).

Scans Python, JavaScript/TypeScript, Java, and Go sources for imports and classifies each
imported module:

  internal  - resolves inside the scanned repository (omitted unless --include-internal)
  stdlib    - language standard library (omitted unless --include-stdlib)
  external  - declared in a dependency manifest of the repository     -> RESOLVED
  cross-repo- matches a prefix in --known-repos (another repo in scope) -> RESOLVED
  unknown   - none of the above                                        -> UNRESOLVED

Every dependency carries evidence_level STATIC. Anything the scan cannot resolve is reported as
UNRESOLVED — never silently dropped and never reported as "no dependency" (§5.3).

Output: JSON on stdout. Exit codes: 0 ok, 2 usage error, 3 unresolved found with
--fail-on-unresolved.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "vendor", ".venv", "venv", "__pycache__", "dist", "build",
             "target", ".tox", ".mypy_cache", ".idea", ".gradle"}

LANG_BY_EXT = {".py": "python", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
               ".ts": "js", ".tsx": "js", ".java": "java", ".go": "go"}

PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)")
PY_FROM = re.compile(r"^\s*from\s+(\.*[\w.]*)\s+import\s")
JS_PATTERNS = [
    re.compile(r"""^\s*import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""),
    re.compile(r"""^\s*export\s+[^'"]*?\s+from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""\bimport\(\s*['"]([^'"]+)['"]\s*\)"""),
]
JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;")
GO_SINGLE = re.compile(r"""^\s*import\s+(?:[\w.]+\s+)?"([^"]+)\"""")
GO_BLOCK_LINE = re.compile(r"""^\s*(?:[\w.]+\s+)?"([^"]+)\"""")

NODE_BUILTINS = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console", "crypto", "dgram",
    "dns", "events", "fs", "http", "http2", "https", "module", "net", "os", "path", "perf_hooks",
    "process", "querystring", "readline", "stream", "string_decoder", "timers", "tls", "tty", "url",
    "util", "v8", "vm", "worker_threads", "zlib",
}
JAVA_STDLIB_PREFIXES = ("java.", "javax.", "jdk.", "sun.", "com.sun.", "org.w3c.", "org.xml.")


# ---------- extraction ----------

def extract(path: Path, lang: str) -> list[tuple[str, int]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found: list[tuple[str, int]] = []
    in_go_block = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if lang == "python":
            m = PY_IMPORT.match(line)
            if m:
                for mod in m.group(1).split(","):
                    found.append((mod.strip().split(" ")[0], lineno))
                continue
            m = PY_FROM.match(line)
            if m:
                found.append((m.group(1), lineno))
        elif lang == "js":
            for pat in JS_PATTERNS:
                for m in pat.finditer(line):
                    found.append((m.group(1), lineno))
        elif lang == "java":
            m = JAVA_IMPORT.match(line)
            if m:
                found.append((m.group(1), lineno))
        elif lang == "go":
            stripped = line.strip()
            if in_go_block:
                if stripped.startswith(")"):
                    in_go_block = False
                    continue
                m = GO_BLOCK_LINE.match(line)
                if m:
                    found.append((m.group(1), lineno))
            elif re.match(r"^\s*import\s*\(", line):
                in_go_block = True
            else:
                m = GO_SINGLE.match(line)
                if m:
                    found.append((m.group(1), lineno))
    return found


# ---------- repository context ----------

class RepoContext:
    def __init__(self, root: Path):
        self.root = root
        self.py_declared = self._python_declared()
        self.py_top_level = self._python_top_level()
        self.js_declared = self._js_declared()
        self.go_module, self.go_requires = self._go_mod()
        self.jvm_build_text = self._jvm_build_text()
        self.java_packages = self._java_packages()

    def _read(self, rel: str) -> str:
        p = self.root / rel
        try:
            return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        except OSError:
            return ""

    @staticmethod
    def _norm_py(name: str) -> str:
        return re.sub(r"[-_.]+", "_", name).lower()

    def _python_declared(self) -> set[str]:
        names: set[str] = set()
        for req in self.root.glob("requirements*.txt"):
            for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.split("#")[0].strip()
                if line and not line.startswith("-"):
                    names.add(self._norm_py(re.split(r"[\s<>=!~\[;]", line)[0]))
        pyproject = self._read("pyproject.toml")
        for m in re.finditer(r"""['"]([A-Za-z0-9_.\-]+)\s*(?:[<>=!~\[;][^'"]*)?['"]""", pyproject):
            names.add(self._norm_py(m.group(1)))
        for m in re.finditer(r"^\s*([A-Za-z0-9_.\-]+)\s*=", pyproject, re.M):
            names.add(self._norm_py(m.group(1)))
        return names

    def _python_top_level(self) -> set[str]:
        tops: set[str] = set()
        for base in (self.root, self.root / "src"):
            if not base.is_dir():
                continue
            for child in base.iterdir():
                if child.is_dir() and child.name not in SKIP_DIRS:
                    tops.add(child.name)
                elif child.suffix == ".py":
                    tops.add(child.stem)
        return tops

    def _js_declared(self) -> set[str]:
        names: set[str] = set()
        for pkg in self.root.rglob("package.json"):
            if any(part in SKIP_DIRS for part in pkg.relative_to(self.root).parts):
                continue
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data.get("name"), str):
                names.add(data["name"])  # workspace package — internal
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                names.update((data.get(key) or {}).keys())
        return names

    def _go_mod(self) -> tuple[str | None, list[str]]:
        text = self._read("go.mod")
        module = None
        m = re.search(r"^module\s+(\S+)", text, re.M)
        if m:
            module = m.group(1)
        requires = re.findall(r"^\s*(?:require\s+)?([\w.\-]+\.[\w.\-/]+)\s+v[\w.\-+]+", text, re.M)
        return module, requires

    def _jvm_build_text(self) -> str:
        return "\n".join(self._read(f) for f in ("pom.xml", "build.gradle", "build.gradle.kts"))

    def _java_packages(self) -> set[str]:
        pkgs: set[str] = set()
        for f in self.root.rglob("*.java"):
            if any(part in SKIP_DIRS for part in f.relative_to(self.root).parts):
                continue
            try:
                head = f.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                continue
            m = re.search(r"^\s*package\s+([\w.]+)\s*;", head, re.M)
            if m:
                pkgs.add(m.group(1))
        return pkgs


# ---------- classification ----------

def js_package_name(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def classify(module: str, lang: str, ctx: RepoContext, known: dict[str, str]) -> tuple[str, str]:
    """Return (kind, target)."""
    if not module.startswith("."):
        for prefix, repo in sorted(known.items(), key=lambda kv: -len(kv[0])):
            if module == prefix or module.startswith((prefix + ".", prefix + "/")):
                return "cross-repo", repo

    if lang == "python":
        if module.startswith("."):
            return "internal", module
        top = module.split(".")[0]
        if top in getattr(sys, "stdlib_module_names", ()) or top == "__future__":
            return "stdlib", top
        if top in ctx.py_top_level:
            return "internal", top
        if RepoContext._norm_py(top) in ctx.py_declared:
            return "external", top
        return "unknown", top

    if lang == "js":
        if module.startswith((".", "/", "~/", "@/")):
            return "internal", module
        if module.startswith("node:") or module.split("/")[0] in NODE_BUILTINS:
            return "stdlib", module
        name = js_package_name(module)
        if name in ctx.js_declared:
            return "external", name
        return "unknown", name

    if lang == "java":
        if module.startswith(JAVA_STDLIB_PREFIXES):
            return "stdlib", module
        pkg = module.rsplit(".", 1)[0]
        if any(pkg == p or pkg.startswith(p + ".") or p.startswith(pkg + ".") for p in ctx.java_packages):
            return "internal", pkg
        group = ".".join(module.split(".")[:2])
        if group and group in ctx.jvm_build_text:
            return "external", group
        return "unknown", group

    if lang == "go":
        if ctx.go_module and (module == ctx.go_module or module.startswith(ctx.go_module + "/")):
            return "internal", module
        if "." not in module.split("/")[0]:
            return "stdlib", module
        for req in ctx.go_requires:
            if module == req or module.startswith(req + "/"):
                return "external", req
        return "unknown", module

    return "unknown", module


def iter_sources(root: Path, only: list[str] | None):
    if only:
        for rel in only:
            p = (root / rel)
            if p.suffix in LANG_BY_EXT and p.is_file():
                yield p
        return
    for p in root.rglob("*"):
        if p.suffix in LANG_BY_EXT and p.is_file() \
                and not any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            yield p


def scan(root: Path, repo_name: str, known: dict[str, str], only: list[str] | None = None,
         include_internal: bool = False, include_stdlib: bool = False) -> dict:
    ctx = RepoContext(root)
    grouped: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    files_scanned = 0
    for path in iter_sources(root, only):
        files_scanned += 1
        lang = LANG_BY_EXT[path.suffix]
        rel = path.relative_to(root).as_posix()
        for module, lineno in extract(path, lang):
            kind, target = classify(module, lang, ctx, known)
            if kind == "internal" and not include_internal:
                continue
            if kind == "stdlib" and not include_stdlib:
                continue
            grouped[(kind, target, lang)].append(f"{rel}:{lineno}")

    deps = []
    for (kind, target, lang), locs in sorted(grouped.items()):
        resolved = kind in ("external", "cross-repo", "internal", "stdlib")
        deps.append({
            "source": repo_name,
            "target": target,
            "type": "import",
            "kind": kind,
            "language": lang,
            "evidence_level": "STATIC",
            "status": "RESOLVED" if resolved else "UNRESOLVED",
            "confidence": {"cross-repo": "high", "external": "high" if lang != "java" else "medium",
                           "internal": "high", "stdlib": "high"}.get(kind, "low"),
            "locations": locs,
        })
    unresolved = sum(1 for d in deps if d["status"] == "UNRESOLVED")
    return {
        "repo": repo_name,
        "root": str(root),
        "files_scanned": files_scanned,
        "dependencies": deps,
        "unresolved_count": unresolved,
        "note": "Static analysis only. Dynamic imports, reflection, and runtime service calls are not "
                "covered; UNRESOLVED entries default to the cautious reading (§5.3).",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Static import scan for dependency discovery.")
    ap.add_argument("root", type=Path, help="repository root to scan")
    ap.add_argument("--repo-name", help="name recorded as the dependency source (default: dir name)")
    ap.add_argument("--known-repos", type=Path,
                    help='JSON object mapping module/package prefixes to repo names, e.g. {"@acme/billing": "acme/billing"}')
    ap.add_argument("--files", nargs="*", help="limit scan to these repo-relative files")
    ap.add_argument("--include-internal", action="store_true")
    ap.add_argument("--include-stdlib", action="store_true")
    ap.add_argument("--fail-on-unresolved", action="store_true")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(json.dumps({"error": f"not a directory: {args.root}"}))
        return 2
    known = {}
    if args.known_repos:
        try:
            known = json.loads(args.known_repos.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(json.dumps({"error": f"cannot read --known-repos: {exc}"}))
            return 2
    root = args.root.resolve()
    result = scan(root, args.repo_name or root.name, known, args.files,
                  args.include_internal, args.include_stdlib)
    print(json.dumps(result, indent=2))
    return 3 if args.fail_on_unresolved and result["unresolved_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
