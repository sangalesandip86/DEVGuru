"""Architecture fitness tests for the modular monolith (docs/adr/0001-mcp-modular-monolith.md).

Rules, checked by scanning imports with ``ast``:
  1. The kernel never imports any module.
  2. A module never imports another module — not even its api. Cross-module wiring happens
     only in the composition root (app.py) through ports.
  3. app.py imports other modules only through ``adlc_mcp.modules.<name>.api``.
  4. Every module has the standard shape and every known module is checked.
"""
import ast
import unittest
from pathlib import Path

from tests._support import SRC

from adlc_mcp.kernel.config import KNOWN_MODULES

PKG = SRC / "adlc_mcp"
MODULES = PKG / "modules"
REQUIRED_FILES = ("__init__.py", "api.py", "domain.py", "store.py", "tools.py")


def imports_of(path: Path) -> list[str]:
    """Absolute dotted names imported by ``path`` (relative imports resolved)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(SRC).with_suffix("")
    package = list(rel.parts[:-1]) if rel.name != "__init__" else list(rel.parts[:-1])
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            out.append(mod)
            out += [f"{mod}.{a.name}" for a in node.names]   # `from x import api` → x.api
    return out


def module_of(dotted: str) -> str | None:
    parts = dotted.split(".")
    if parts[:2] == ["adlc_mcp", "modules"] and len(parts) >= 3:
        return parts[2]
    return None


class ModuleBoundaries(unittest.TestCase):
    def test_every_known_module_exists_with_standard_shape(self):
        present = sorted(p.name for p in MODULES.iterdir() if p.is_dir() and not p.name.startswith("_"))
        self.assertEqual(present, sorted(KNOWN_MODULES))
        for name in KNOWN_MODULES:
            for f in REQUIRED_FILES:
                self.assertTrue((MODULES / name / f).is_file(), f"{name}/{f} missing")
            self.assertTrue(list((MODULES / name / "migrations").glob("0001_*.sql")), f"{name} has no migrations")

    def test_kernel_imports_no_module(self):
        for f in (PKG / "kernel").rglob("*.py"):
            bad = [i for i in imports_of(f) if module_of(i)]
            self.assertEqual(bad, [], f"kernel file {f.name} imports modules: {bad}")

    def test_modules_do_not_import_each_other(self):
        for name in KNOWN_MODULES:
            for f in (MODULES / name).rglob("*.py"):
                foreign = sorted({i for i in imports_of(f) if module_of(i) not in (None, name)})
                self.assertEqual(foreign, [], f"{name}/{f.name} imports another module: {foreign}")
                stray = [i for i in imports_of(f) if i.startswith("adlc_mcp.") and not (
                    i.startswith("adlc_mcp.kernel") or module_of(i) == name)]
                self.assertEqual(stray, [], f"{name}/{f.name} imports outside kernel/own module: {stray}")

    def test_app_uses_only_public_apis(self):
        for i in imports_of(PKG / "app.py"):
            m = module_of(i)
            if m is None:
                continue
            ok = i in ("adlc_mcp.modules", f"adlc_mcp.modules.{m}", f"adlc_mcp.modules.{m}.api") \
                or i.startswith(f"adlc_mcp.modules.{m}.api.")
            self.assertTrue(ok, f"app.py reaches into module internals: {i}")

    def test_only_app_wires_modules(self):
        for f in PKG.rglob("*.py"):
            if f.name == "app.py" or MODULES in f.parents:
                continue
            bad = [i for i in imports_of(f) if module_of(i)]
            self.assertEqual(bad, [], f"{f.relative_to(PKG)} imports modules; only app.py may: {bad}")

    def test_each_module_owns_its_own_database(self):
        from adlc_mcp.kernel.config import Config

        cfg = Config(data_dir=Path("d"))
        self.assertEqual(len({cfg.db_path(n) for n in KNOWN_MODULES}), len(KNOWN_MODULES))
        for name in KNOWN_MODULES:
            for sql in (MODULES / name / "migrations").glob("*.sql"):
                text = sql.read_text(encoding="utf-8").upper()
                self.assertNotIn("ATTACH", text, f"{name}/{sql.name} attaches another database")


class Extractability(unittest.TestCase):
    def test_each_module_runs_standalone(self):
        from tests._support import TempEnv, CI

        from adlc_mcp.app import build_server

        class Rec:
            def __init__(self):
                self.names = []

            def tool(self, name=None, description=None):
                return lambda fn: self.names.append(name) or fn

        for name in KNOWN_MODULES:
            env = TempEnv(name)
            try:
                _, registry, tools = build_server(env.config, CI, server=Rec())
                self.assertEqual(registry.names(), [name])
                self.assertTrue(tools)
                self.assertEqual(sorted(p.name for p in env.dir.glob("*.db")), [f"{name}.db"])
                registry.close()
            finally:
                env.close()


if __name__ == "__main__":
    unittest.main()
