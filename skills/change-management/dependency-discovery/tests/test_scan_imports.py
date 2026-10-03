import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan-imports.py"
spec = importlib.util.spec_from_file_location("scan_imports", SCRIPT)
scan_imports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan_imports)


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class ScanImportsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def deps(self, known=None, **kw):
        result = scan_imports.scan(self.root, "repo-a", known or {}, **kw)
        return {(d["kind"], d["target"]): d for d in result["dependencies"]}, result

    def test_python(self):
        write(self.root, "requirements.txt", "requests==2.31\n# comment\nPyYAML>=6\n")
        write(self.root, "app/__init__.py", "")
        write(self.root, "app/main.py",
              "import os, json\nimport requests\nimport yaml\nfrom app import util\n"
              "from . import sibling\nimport acme_billing.client\nimport mystery_pkg\n")
        deps, result = self.deps({"acme_billing": "acme/billing"})
        self.assertEqual(deps[("external", "requests")]["status"], "RESOLVED")
        self.assertEqual(deps[("cross-repo", "acme/billing")]["status"], "RESOLVED")
        self.assertEqual(deps[("unknown", "mystery_pkg")]["status"], "UNRESOLVED")
        self.assertEqual(deps[("unknown", "mystery_pkg")]["locations"], ["app/main.py:7"])
        self.assertNotIn(("stdlib", "os"), deps)
        self.assertNotIn(("internal", "app"), deps)
        # yaml is declared as PyYAML: name differs from import name -> cautious UNRESOLVED
        self.assertEqual(deps[("unknown", "yaml")]["status"], "UNRESOLVED")
        self.assertTrue(all(d["evidence_level"] == "STATIC" for d in result["dependencies"]))

    def test_js_ts(self):
        write(self.root, "package.json", json.dumps({"name": "web", "dependencies": {"react": "18", "@acme/ui": "1"}}))
        write(self.root, "src/a.ts",
              "import React from 'react';\nimport { Button } from '@acme/ui/button';\n"
              "import x from './local';\nconst fs = require('fs');\nimport('node:path');\n"
              "import api from '@acme/billing-client';\nexport { y } from 'left-pad';\n")
        deps, _ = self.deps({"@acme/billing-client": "acme/billing"})
        self.assertIn(("external", "react"), deps)
        self.assertIn(("external", "@acme/ui"), deps)
        self.assertIn(("cross-repo", "acme/billing"), deps)
        self.assertEqual(deps[("unknown", "left-pad")]["status"], "UNRESOLVED")
        self.assertNotIn(("stdlib", "fs"), deps)

    def test_java(self):
        write(self.root, "pom.xml", "<groupId>com.fasterxml</groupId>")
        write(self.root, "src/main/java/com/acme/pay/Fee.java",
              "package com.acme.pay;\nimport java.util.List;\nimport com.acme.pay.model.Money;\n"
              "import com.fasterxml.jackson.databind.ObjectMapper;\nimport org.unknown.Thing;\n")
        deps, _ = self.deps(include_internal=True)
        self.assertIn(("internal", "com.acme.pay.model"), deps)
        self.assertIn(("external", "com.fasterxml"), deps)
        self.assertEqual(deps[("unknown", "org.unknown")]["status"], "UNRESOLVED")

    def test_go(self):
        write(self.root, "go.mod", "module github.com/acme/svc\n\nrequire (\n\tgithub.com/google/uuid v1.6.0\n)\n")
        write(self.root, "main.go",
              'package main\n\nimport (\n\t"fmt"\n\t"github.com/acme/svc/internal/x"\n'
              '\tuuid "github.com/google/uuid"\n\t"github.com/other/lib"\n)\n')
        deps, _ = self.deps()
        self.assertIn(("external", "github.com/google/uuid"), deps)
        self.assertEqual(deps[("unknown", "github.com/other/lib")]["status"], "UNRESOLVED")
        self.assertNotIn(("stdlib", "fmt"), deps)

    def test_skips_node_modules_and_cli_exit_code(self):
        write(self.root, "node_modules/x/index.js", "require('should-not-appear')")
        write(self.root, "a.py", "import ghost_module\n")
        _, result = self.deps()
        self.assertEqual(result["files_scanned"], 1)
        self.assertEqual(scan_imports.main([str(self.root), "--fail-on-unresolved"]), 3)


if __name__ == "__main__":
    unittest.main()
