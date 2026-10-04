"""Tests for system_map.py — system-map.json builder."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import system_map as sm


class OpenApiTest(unittest.TestCase):
    def test_detects_openapi_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "api" / "openapi.json"
            spec.parent.mkdir()
            spec.write_text(json.dumps({
                "openapi": "3.0.0",
                "info": {"title": "Users API", "version": "1.0"},
                "paths": {"/users": {"get": {}}, "/users/{id}": {"get": {}}},
            }), encoding="utf-8")
            services = sm.scan_contracts(root)
            self.assertEqual(len(services), 1)
            self.assertEqual(services[0]["name"], "Users API")
            self.assertEqual(services[0]["type"], "http")
            self.assertEqual(len(services[0]["endpoints"]), 2)


class AsyncApiTest(unittest.TestCase):
    def test_detects_asyncapi_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "events.yaml"
            spec.write_text(
                'asyncapi: "2.0.0"\n'
                'info:\n  title: Order Events\n  version: "1.0"\n'
                'channels:\n  order/created:\n    subscribe: {}\n',
                encoding="utf-8",
            )
            services = sm.scan_contracts(root)
            self.assertEqual(len(services), 1)
            self.assertEqual(services[0]["type"], "async")


class ProtoTest(unittest.TestCase):
    def test_detects_grpc_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proto = root / "api.proto"
            proto.write_text(
                'syntax = "proto3";\n'
                "service UserService {\n"
                "  rpc GetUser (GetUserRequest) returns (User);\n"
                "  rpc ListUsers (ListRequest) returns (UserList);\n"
                "}\n",
                encoding="utf-8",
            )
            services = sm.scan_contracts(root)
            self.assertEqual(len(services), 1)
            self.assertEqual(services[0]["name"], "UserService")
            self.assertEqual(services[0]["type"], "grpc")
            self.assertIn("GetUser", services[0]["rpcs"])


class EnvHostsTest(unittest.TestCase):
    def test_extracts_urls_from_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "DATABASE_URL=postgres://localhost/db\n"
                "API_HOST=https://api.example.com/v1\n",
                encoding="utf-8",
            )
            hosts = sm.scan_env_hosts(root)
            self.assertEqual(len(hosts), 1)
            self.assertEqual(hosts[0]["url"], "https://api.example.com/v1")


class BackstageTest(unittest.TestCase):
    def test_reads_catalog_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "catalog-info.yaml").write_text(
                "apiVersion: backstage.io/v1alpha1\n"
                "kind: Component\n"
                "metadata:\n  name: my-service\n"
                "spec:\n  owner: platform-team\n",
                encoding="utf-8",
            )
            meta = sm.scan_backstage(root)
            self.assertEqual(len(meta), 1)
            self.assertEqual(meta[0]["name"], "my-service")


class BuildMapTest(unittest.TestCase):
    def test_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "openapi.json"
            spec.write_text(json.dumps({
                "openapi": "3.0.0",
                "info": {"title": "Test", "version": "1"},
                "paths": {"/health": {"get": {}}},
            }), encoding="utf-8")
            result = sm.build_system_map(root)
            self.assertEqual(result["classification"], "FACT")
            self.assertEqual(len(result["services"]), 1)

    def test_api_scan_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api_scan = {
                "cross_repo_edges": [
                    {"caller_repo": "frontend", "callee_repo": "api",
                     "path": "/users", "confidence": "high"},
                ],
            }
            result = sm.build_system_map(root, api_scan)
            self.assertEqual(len(result["edges"]), 1)
            self.assertEqual(result["edges"][0]["from"], "frontend")


class EmptyRepoTest(unittest.TestCase):
    def test_empty_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = sm.build_system_map(Path(tmp))
            self.assertEqual(result["services"], [])
            self.assertEqual(result["edges"], [])


if __name__ == "__main__":
    unittest.main()
