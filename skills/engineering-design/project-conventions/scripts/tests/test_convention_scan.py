import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("convention_scan", HERE.parent / "convention_scan.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


def write(root: Path, rel: str, text: str = "") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class TsProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.root = Path(self.tmp.name)
        write(r, "package.json", json.dumps({
            "scripts": {"lint": "eslint .", "typecheck": "tsc --noEmit", "start": "node dist"},
            "dependencies": {"axios": "1", "got": "14", "pino": "9", "zod": "3", "@prisma/client": "5",
                             "inversify": "6", "express": "4"},
            "devDependencies": {"eslint": "9"},
        }))
        write(r, "eslint.config.js", "export default []")
        write(r, ".prettierrc", "{}")
        write(r, "tsconfig.json", "{}")
        write(r, "AGENTS.md", "# guidance")
        write(r, "docs/adr/0001-use-pino.md", "# ADR")
        write(r, "src/orders/controllers/order.controller.ts", "import { OrderService } from '../services/order.service';\n")
        write(r, "src/orders/services/order.service.ts", "import { OrderRepository } from '../repositories/order.repository';\n")
        write(r, "src/orders/services/pricing.service.ts", "import { OrderService } from './order.service';\n")
        write(r, "src/orders/repositories/order.repository.ts", "export class OrderRepository {}\n")
        write(r, "src/billing/services/invoice.service.ts", "export class InvoiceService {}\n")
        write(r, "src/orders/services/order.service.spec.ts", "test")
        write(r, "node_modules/axios/index.js", "x")
        self.result = cs.scan(r, target="src/orders/services/discount.service.ts")

    def tearDown(self):
        self.tmp.cleanup()

    def test_declared_standards_with_hashes(self):
        d = self.result["declared_standards"]
        self.assertEqual([x["path"] for x in d["lint"]], ["eslint.config.js"])
        self.assertTrue(any(x["path"] == ".prettierrc" for x in d["format"]))
        self.assertTrue(any(x["path"] == "tsconfig.json" for x in d["type"]))
        self.assertTrue(any(x["path"] == "AGENTS.md" for x in d["docs"]))
        self.assertEqual(d["adr_dirs"][0]["path"], "docs/adr")
        self.assertTrue(d["adr_dirs"][0]["files"][0]["sha256"].startswith("sha256:"))

    def test_toolchain_from_package_scripts(self):
        names = {c["name"] for c in self.result["toolchain"]}
        self.assertIn("lint", names)
        self.assertIn("typecheck", names)
        self.assertNotIn("start", names)

    def test_dependency_concerns_and_mixed_note(self):
        deps = self.result["dependencies"]
        self.assertEqual({d["name"] for d in deps["http_client"]}, {"axios", "got"})
        self.assertEqual([d["name"] for d in deps["logging"]], ["pino"])
        self.assertIn("@prisma/client", {d["name"] for d in deps["orm"]})
        self.assertIn("inversify", {d["name"] for d in deps["di"]})
        mixed = [n for n in self.result["notes"] if n["type"] == "mixed_conventions"]
        self.assertEqual([n["concern"] for n in mixed], ["http_client"])

    def test_module_map_layers_and_feature_layout(self):
        mm = self.result["module_map"]
        dirs = {e["dir"]: e["layer"] for e in mm["layers"]}
        self.assertEqual(dirs["src/orders/services"], "application")
        self.assertEqual(dirs["src/orders/repositories"], "persistence")
        self.assertEqual(mm["layout"], "feature-folders")

    def test_golden_files_ranked_and_exclude_tests_vendor(self):
        paths = [g["path"] for g in self.result["golden_files"]]
        self.assertEqual(paths[0].rsplit("/", 1)[0], "src/orders/services")
        self.assertNotIn("src/orders/services/order.service.spec.ts", paths)
        self.assertFalse(any("node_modules" in p for p in paths))
        # same-layer file in another feature ranks below same-dir files
        self.assertLess(paths.index("src/orders/services/order.service.ts"),
                        paths.index("src/billing/services/invoice.service.ts"))

    def test_no_arch_conformance_note(self):
        self.assertIn("no_arch_conformance", [n["type"] for n in self.result["notes"]])
        self.assertFalse(self.result["greenfield"])


class PythonProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.root = Path(self.tmp.name)
        write(r, "pyproject.toml", (
            '[project]\nname = "orders"\ndependencies = ["fastapi>=0.110", "sqlalchemy", "structlog", "pydantic>=2", "httpx"]\n'
            '[tool.ruff]\nline-length = 100\n[tool.mypy]\nstrict = true\n[tool.importlinter]\nroot_package = "orders"\n'
        ))
        write(r, "Makefile", "lint:\n\truff check .\ntest:\n\tpytest\nrun:\n\tuvicorn app:app\n")
        write(r, "CONTRIBUTING.md", "be nice")
        write(r, "orders/api/routes.py", "from orders.service.order_service import OrderService\n")
        write(r, "orders/service/order_service.py", "from orders.repository.order_repo import OrderRepo\n")
        write(r, "orders/repository/order_repo.py", "class OrderRepo: pass\n")
        write(r, "tests/test_orders.py", "def test_x(): pass\n")
        write(r, "junit.xml", '<testsuite><testcase classname="orders.service.order_service" name="t"/></testsuite>')

    def tearDown(self):
        self.tmp.cleanup()

    def test_python_scan(self):
        res = cs.scan(self.root, target="orders/service/refund_service.py", junit=self.root / "junit.xml")
        sections = {s["section"] for s in res["declared_standards"]["manifest_sections"]}
        self.assertTrue({"tool.ruff", "tool.mypy", "tool.importlinter"} <= sections)
        self.assertNotIn("no_arch_conformance", [n["type"] for n in res["notes"]])
        names = {c["command"] for c in res["toolchain"]}
        self.assertIn("make lint", names)
        self.assertIn("ruff check .", names)
        self.assertNotIn("make run", names)
        deps = res["dependencies"]
        self.assertEqual([d["name"] for d in deps["orm"]], ["sqlalchemy"])
        self.assertEqual([d["name"] for d in deps["logging"]], ["structlog"])
        self.assertEqual([d["name"] for d in deps["validation"]], ["pydantic"])
        self.assertEqual([d["name"] for d in deps["http_client"]], ["httpx"])
        self.assertEqual([n for n in res["notes"] if n["type"] == "mixed_conventions"], [])
        golden = res["golden_files"]
        self.assertEqual(golden[0]["path"], "orders/service/order_service.py")
        self.assertIn("passing_in_junit", golden[0]["reasons"])
        self.assertFalse(any(g["path"].startswith("tests/") for g in golden))

    def test_cli_writes_default_catalog(self):
        rc = cs.main(["--repo", str(self.root)])
        self.assertEqual(rc, 0)
        out = self.root / ".adlc" / "catalog" / "conventions.json"
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "adlc.conventions/v1")
        self.assertEqual(data["golden_files"], [])  # no --target

    def test_greenfield_and_bad_repo(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertTrue(cs.scan(Path(empty))["greenfield"])
        self.assertEqual(cs.main(["--repo", str(self.root / "nope")]), 2)


if __name__ == "__main__":
    unittest.main()
