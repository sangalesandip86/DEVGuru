"""ADLC Insight Hub — HTTP layer.

Serves the bundled static UI and a REST + SSE API backed by the module registry.
Binds to 127.0.0.1 only (loopback). Started alongside the MCP stdio transport.

    server, port, thread = start_hub(registry, config)
    # ... later ...
    stop_hub(server)
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from adlc_mcp.kernel.identity import system_identity
from adlc_mcp.kernel.module import ModuleRegistry

_STATIC_DIR = Path(__file__).parent / "static"
_IDENTITY = system_identity("insight-hub", tool="server")
_START_TIME = time.monotonic()

CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, default=str).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


class InsightHubHandler(BaseHTTPRequestHandler):
    registry: ModuleRegistry
    static_dir: Path = _STATIC_DIR
    _sse_clients: list[Any] = []
    _sse_lock = threading.Lock()

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin.startswith("http://127.0.0.1") or origin.startswith("http://localhost"):
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = _json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        try:
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status)

    def _module_api(self, name: str) -> Any:
        if name not in self.registry:
            return None
        return self.registry.get(name).api

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path.startswith("/ui"):
            return self._serve_static(path)
        if path == "/api/health":
            return self._api_health()
        if path == "/api/events":
            return self._api_events()
        if path == "/api/changesets":
            return self._api_changesets()
        if path.startswith("/api/changeset/"):
            cs_id = path[len("/api/changeset/"):]
            return self._api_changeset(cs_id)
        if path == "/api/evidence":
            return self._api_evidence(qs)
        if path == "/api/journal":
            return self._api_journal(qs)
        if path == "/api/stage":
            return self._api_stage(qs)
        if path == "/api/conflicts":
            return self._api_conflicts(qs)
        if path == "/api/workers":
            return self._api_workers(qs)
        if path == "/api/trace":
            return self._api_trace(qs)
        if path == "/api/handoffs":
            return self._api_handoffs(qs)
        if path == "/api/tasks":
            return self._api_tasks(qs)
        if path == "/api/status-history":
            return self._api_status_history(qs)
        if path == "/api/risk-history":
            return self._api_risk_history(qs)
        if path == "/api/overview":
            return self._api_overview()
        self._send_error_json(404, "not found")

    # ---------------------------------------------------------------- static files
    def _serve_static(self, path: str) -> None:
        rel = path[len("/ui"):]
        if not rel or rel == "/":
            rel = "/index.html"

        safe = Path(self.static_dir / rel.lstrip("/")).resolve()
        if not str(safe).startswith(str(self.static_dir.resolve())):
            self._send_error_json(403, "forbidden")
            return

        if not safe.is_file():
            self._send_error_json(404, "not found")
            return

        ext = safe.suffix.lower()
        ct = CONTENT_TYPES.get(ext, mimetypes.guess_type(str(safe))[0] or "application/octet-stream")
        body = safe.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self._cors_headers()
        try:
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return

    # ---------------------------------------------------------------- API: health
    def _api_health(self) -> None:
        uptime = time.monotonic() - _START_TIME
        self._send_json({
            "status": "ok",
            "modules": self.registry.names(),
            "uptime_seconds": round(uptime, 1),
        })

    # ---------------------------------------------------------------- API: SSE events
    def _api_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors_headers()
        self.end_headers()

        try:
            while True:
                digest = _digest(str(time.time()).encode())
                chunk = f"event: heartbeat\ndata: {json.dumps({'digest': digest})}\n\n"
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
                time.sleep(15)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    # ---------------------------------------------------------------- API: changesets
    def _api_changesets(self) -> None:
        cm = self._module_api("change_management")
        if cm is None:
            return self._send_error_json(404, "module not enabled: change_management")
        try:
            rows = cm._store.conn.execute(
                "SELECT id, status, risk_tier, title, created_at, updated_at "
                "FROM change_sets ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
            self._send_json([dict(r) for r in rows])
        except Exception as exc:
            self._send_error_json(500, str(exc))

    def _api_changeset(self, cs_id: str) -> None:
        cm = self._module_api("change_management")
        if cm is None:
            return self._send_error_json(404, "module not enabled: change_management")
        try:
            result = cm.get_change_set(_IDENTITY, cs_id)
            self._send_json(result)
        except Exception as exc:
            self._send_error_json(404, str(exc))

    # ---------------------------------------------------------------- API: evidence
    def _api_evidence(self, qs: dict) -> None:
        ledger = self._module_api("evidence_ledger")
        if ledger is None:
            return self._send_error_json(404, "module not enabled: evidence_ledger")
        cs_id = qs.get("change_set_id", [""])[0]
        try:
            results = ledger.query_evidence(_IDENTITY, change_set_id=cs_id or None)
            self._send_json(results)
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: journal
    def _api_journal(self, qs: dict) -> None:
        journal = self._module_api("event_journal")
        if journal is None:
            return self._send_error_json(404, "module not enabled: event_journal")
        cs_id = qs.get("change_set_id", [""])[0]
        try:
            results = journal.query_journal(change_set_id=cs_id or None)
            self._send_json(results)
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: stage
    def _api_stage(self, qs: dict) -> None:
        engine = self._module_api("stage_engine")
        if engine is None:
            return self._send_error_json(404, "module not enabled: stage_engine")
        cs_id = qs.get("change_set_id", [""])[0]
        try:
            current = engine.get_current_stage(change_set_id=cs_id) if cs_id else {}
            graph = engine.get_transition_graph()
            self._send_json({"current": current, "graph": graph})
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: conflicts
    def _api_conflicts(self, qs: dict) -> None:
        conc = self._module_api("concurrency")
        if conc is None:
            return self._send_error_json(404, "module not enabled: concurrency")
        files = qs.get("files", [])
        try:
            results = conc.check_conflicts(_IDENTITY, planned_files=files)
            self._send_json(results)
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: workers
    def _api_workers(self, qs: dict) -> None:
        pc = self._module_api("parallel_coordinator")
        if pc is None:
            return self._send_error_json(404, "module not enabled: parallel_coordinator")
        plan_id = qs.get("plan_id", [""])[0]
        if not plan_id:
            return self._send_error_json(400, "plan_id is required")
        try:
            results = pc.get_worker_status(plan_id=plan_id)
            self._send_json(results)
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: trace (ALL events)
    def _api_trace(self, qs: dict) -> None:
        journal = self._module_api("event_journal")
        if journal is None:
            return self._send_error_json(404, "module not enabled: event_journal")
        cs_id = qs.get("change_set_id", [""])[0]
        event_type = qs.get("event_type", [""])[0]
        try:
            events = journal.query_journal(
                change_set_id=cs_id or None,
                event_type=event_type or None,
                limit=1000,
            )
            self._send_json(events)
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: handoffs
    def _api_handoffs(self, qs: dict) -> None:
        cm = self._module_api("change_management")
        if cm is None:
            return self._send_error_json(404, "module not enabled: change_management")
        cs_id = qs.get("change_set_id", [""])[0]
        try:
            if cs_id:
                rows = cm._store.handoffs(cs_id)
            else:
                raw = cm._store.conn.execute(
                    "SELECT * FROM handoffs ORDER BY seq DESC LIMIT 200"
                ).fetchall()
                rows = [dict(r) for r in raw]
                for row in rows:
                    if isinstance(row.get("payload"), str):
                        try:
                            row["payload"] = json.loads(row["payload"])
                        except (TypeError, ValueError):
                            pass
            self._send_json(rows)
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: tasks
    def _api_tasks(self, qs: dict) -> None:
        cm = self._module_api("change_management")
        if cm is None:
            return self._send_error_json(404, "module not enabled: change_management")
        cs_id = qs.get("change_set_id", [""])[0]
        try:
            if cs_id:
                rows = cm._store.tasks(cs_id)
            else:
                raw = cm._store.conn.execute(
                    "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 200"
                ).fetchall()
                rows = [dict(r) for r in raw]
            self._send_json(rows)
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: status-history
    def _api_status_history(self, qs: dict) -> None:
        cm = self._module_api("change_management")
        if cm is None:
            return self._send_error_json(404, "module not enabled: change_management")
        cs_id = qs.get("change_set_id", [""])[0]
        try:
            if cs_id:
                rows = cm._store.history(cs_id)
            else:
                raw = cm._store.conn.execute(
                    "SELECT * FROM status_history ORDER BY seq DESC LIMIT 200"
                ).fetchall()
                rows = [dict(r) for r in raw]
            self._send_json(rows)
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: risk-history
    def _api_risk_history(self, qs: dict) -> None:
        cm = self._module_api("change_management")
        if cm is None:
            return self._send_error_json(404, "module not enabled: change_management")
        cs_id = qs.get("change_set_id", [""])[0]
        try:
            if cs_id:
                rows = cm._store.risk_history(cs_id)
            else:
                raw = cm._store.conn.execute(
                    "SELECT * FROM risk_assessments ORDER BY seq DESC LIMIT 200"
                ).fetchall()
                rows = [dict(r) for r in raw]
                for row in rows:
                    for k in ("reason_codes", "detail"):
                        if isinstance(row.get(k), str):
                            try:
                                row[k] = json.loads(row[k])
                            except (TypeError, ValueError):
                                pass
            self._send_json(rows)
        except Exception as exc:
            self._send_error_json(500, str(exc))

    # ---------------------------------------------------------------- API: overview (aggregate)
    def _api_overview(self) -> None:
        result = {"change_sets": 0, "evidence": 0, "handoffs": 0, "tasks": 0,
                  "journal_events": 0, "roles": [], "stages_seen": []}
        cm = self._module_api("change_management")
        if cm:
            try:
                r = cm._store.conn.execute("SELECT COUNT(*) as c FROM change_sets").fetchone()
                result["change_sets"] = r["c"] if r else 0
                r = cm._store.conn.execute("SELECT COUNT(*) as c FROM handoffs").fetchone()
                result["handoffs"] = r["c"] if r else 0
                r = cm._store.conn.execute("SELECT COUNT(*) as c FROM tasks").fetchone()
                result["tasks"] = r["c"] if r else 0
                rows = cm._store.conn.execute(
                    "SELECT DISTINCT from_role AS r FROM handoffs UNION SELECT DISTINCT to_role FROM handoffs"
                ).fetchall()
                result["roles"] = sorted(set(r["r"] for r in rows if r["r"]))
            except Exception:
                pass
        ledger = self._module_api("evidence_ledger")
        if ledger:
            try:
                r = ledger._store.conn.execute("SELECT COUNT(*) as c FROM evidence").fetchone()
                result["evidence"] = r["c"] if r else 0
            except Exception:
                pass
        journal = self._module_api("event_journal")
        if journal:
            try:
                r = journal._store.conn.execute("SELECT COUNT(*) as c FROM journal_entries").fetchone()
                result["journal_events"] = r["c"] if r else 0
                rows = journal._store.conn.execute(
                    "SELECT DISTINCT json_extract(payload, '$.stage') as s FROM journal_entries "
                    "WHERE event_type IN ('stage.enter','stage.exit') AND s IS NOT NULL"
                ).fetchall()
                result["stages_seen"] = sorted(set(r["s"] for r in rows if r["s"]))
            except Exception:
                pass
        self._send_json(result)


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _make_handler(registry: ModuleRegistry, static_dir: Path | None = None) -> type:
    class Handler(InsightHubHandler):
        pass
    Handler.registry = registry
    if static_dir is not None:
        Handler.static_dir = static_dir
    return Handler


def start_hub(registry: ModuleRegistry, config: Any = None,
              port: int = 0, static_dir: Path | None = None) -> tuple[HTTPServer, int, threading.Thread]:
    handler_cls = _make_handler(registry, static_dir)
    server = _ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, actual_port, thread


def stop_hub(server: HTTPServer) -> None:
    server.shutdown()
