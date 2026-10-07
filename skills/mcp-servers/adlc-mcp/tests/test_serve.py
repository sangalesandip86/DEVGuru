"""Tests for the ADLC Insight Hub HTTP server layer."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(src))

from adlc_mcp.serve import InsightHubHandler, start_hub, stop_hub
from adlc_mcp.kernel.module import ModuleRegistry


def _mock_registry(module_names=None):
    registry = ModuleRegistry()
    return registry


def _start_server(registry=None, static_dir=None):
    if registry is None:
        registry = _mock_registry()
    server, port, thread = start_hub(registry, port=0, static_dir=static_dir)
    return server, port


def _get(port, path):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


class TestHealth(unittest.TestCase):
    def setUp(self):
        self.server, self.port = _start_server()

    def tearDown(self):
        stop_hub(self.server)

    def test_health_returns_ok(self):
        resp, body = _get(self.port, "/api/health")
        self.assertEqual(resp.status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "ok")
        self.assertIn("modules", data)
        self.assertIn("uptime_seconds", data)

    def test_health_content_type(self):
        resp, _ = _get(self.port, "/api/health")
        ct = resp.getheader("Content-Type")
        self.assertIn("application/json", ct)


class TestStaticFiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        Path(self.tmpdir, "index.html").write_text("<h1>Test</h1>", encoding="utf-8")
        Path(self.tmpdir, "app.js").write_text("console.log(1);", encoding="utf-8")
        Path(self.tmpdir, "app.css").write_text("body{}", encoding="utf-8")
        self.server, self.port = _start_server(static_dir=Path(self.tmpdir))

    def tearDown(self):
        stop_hub(self.server)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_serves_index(self):
        resp, body = _get(self.port, "/ui/")
        self.assertEqual(resp.status, 200)
        self.assertIn(b"<h1>Test</h1>", body)

    def test_serves_js(self):
        resp, body = _get(self.port, "/ui/app.js")
        self.assertEqual(resp.status, 200)
        self.assertIn("javascript", resp.getheader("Content-Type"))

    def test_serves_css(self):
        resp, body = _get(self.port, "/ui/app.css")
        self.assertEqual(resp.status, 200)
        self.assertIn("css", resp.getheader("Content-Type"))

    def test_cache_control_header(self):
        resp, _ = _get(self.port, "/ui/app.css")
        self.assertIn("no-cache", resp.getheader("Cache-Control", ""))

    def test_missing_file_404(self):
        resp, _ = _get(self.port, "/ui/nope.js")
        self.assertEqual(resp.status, 404)


class TestPathTraversal(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        Path(self.tmpdir, "index.html").write_text("ok", encoding="utf-8")
        self.server, self.port = _start_server(static_dir=Path(self.tmpdir))

    def tearDown(self):
        stop_hub(self.server)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dotdot_blocked(self):
        resp, body = _get(self.port, "/ui/../../../etc/passwd")
        self.assertIn(resp.status, (403, 404))

    def test_encoded_dotdot_blocked(self):
        resp, body = _get(self.port, "/ui/..%2f..%2f..%2fetc%2fpasswd")
        self.assertIn(resp.status, (403, 404))


class TestSSE(unittest.TestCase):
    def setUp(self):
        self.server, self.port = _start_server()

    def tearDown(self):
        stop_hub(self.server)

    def test_sse_headers(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request("GET", "/api/events")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertIn("text/event-stream", resp.getheader("Content-Type"))
        self.assertEqual(resp.getheader("Cache-Control"), "no-cache")
        conn.close()


class TestModuleNotEnabled(unittest.TestCase):
    def setUp(self):
        self.server, self.port = _start_server()

    def tearDown(self):
        stop_hub(self.server)

    def test_changesets_404_when_no_cm(self):
        resp, body = _get(self.port, "/api/changesets")
        self.assertEqual(resp.status, 404)
        data = json.loads(body)
        self.assertIn("module not enabled", data["error"])

    def test_evidence_404_when_no_ledger(self):
        resp, body = _get(self.port, "/api/evidence?change_set_id=CS-1")
        self.assertEqual(resp.status, 404)
        data = json.loads(body)
        self.assertIn("module not enabled", data["error"])

    def test_journal_404_when_no_journal(self):
        resp, body = _get(self.port, "/api/journal?change_set_id=CS-1")
        self.assertEqual(resp.status, 404)

    def test_stage_404_when_no_engine(self):
        resp, body = _get(self.port, "/api/stage?change_set_id=CS-1")
        self.assertEqual(resp.status, 404)

    def test_conflicts_404_when_no_concurrency(self):
        resp, body = _get(self.port, "/api/conflicts?files=a.py")
        self.assertEqual(resp.status, 404)

    def test_workers_404_when_no_coordinator(self):
        resp, body = _get(self.port, "/api/workers?plan_id=p1")
        self.assertEqual(resp.status, 404)

    def test_trace_404_when_no_journal(self):
        resp, body = _get(self.port, "/api/trace?change_set_id=CS-1")
        self.assertEqual(resp.status, 404)


class TestCORS(unittest.TestCase):
    def setUp(self):
        self.server, self.port = _start_server()

    def tearDown(self):
        stop_hub(self.server)

    def test_cors_header_present(self):
        resp, _ = _get(self.port, "/api/health")
        self.assertIsNotNone(resp.getheader("Access-Control-Allow-Origin"))

    def test_options_returns_204(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("OPTIONS", "/api/health")
        resp = conn.getresponse()
        conn.close()
        self.assertEqual(resp.status, 204)


class TestUnknownRoutes(unittest.TestCase):
    def setUp(self):
        self.server, self.port = _start_server()

    def tearDown(self):
        stop_hub(self.server)

    def test_unknown_path_404(self):
        resp, body = _get(self.port, "/api/nonexistent")
        self.assertEqual(resp.status, 404)

    def test_root_404(self):
        resp, body = _get(self.port, "/")
        self.assertEqual(resp.status, 404)


class TestServerLifecycle(unittest.TestCase):
    def test_start_and_stop(self):
        server, port, thread = start_hub(_mock_registry(), port=0)
        self.assertGreater(port, 0)
        self.assertTrue(thread.is_alive())
        stop_hub(server)
        thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
