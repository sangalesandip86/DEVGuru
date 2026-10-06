"""Run the ``adlc`` MCP server over stdio.

    python -m adlc_mcp                                   # modules from ADLC_MODULES (default evidence_ledger)
    python -m adlc_mcp --modules change_management       # one module alone — proves extractability
    python -m adlc_mcp --list-tools                      # print the tool surface for this credential

The session identity comes from ADLC_TOKEN (one credential per role session).
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
from threading import Event

from adlc_mcp.app import build_server
from adlc_mcp.kernel.config import Config
from adlc_mcp.kernel.errors import AdlcError
from adlc_mcp.kernel.identity import resolve_identity


class _Recorder:
    """Stand-in server used by --list-tools so the tool surface can be inspected without the SDK."""

    def __init__(self) -> None:
        self.tools: list[str] = []

    def tool(self, name: str | None = None, description: str | None = None):
        def deco(fn):
            self.tools.append(name or fn.__name__)
            return fn
        return deco


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="adlc-mcp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modules", help="comma-separated modules (overrides ADLC_MODULES)")
    ap.add_argument("--data-dir", help="overrides ADLC_DATA_DIR")
    ap.add_argument("--list-tools", action="store_true")
    ap.add_argument("--serve-ui", action="store_true",
                     help="Start Insight Hub UI HTTP server only (no MCP stdio)")
    ap.add_argument("--port", type=int, default=0,
                     help="Port for the UI server (default: auto-assign)")
    args = ap.parse_args(argv)
    try:
        config = Config.from_env(modules=args.modules, data_dir=args.data_dir)
        identity = resolve_identity()
        if args.list_tools:
            _, registry, tools = build_server(config, identity, server=_Recorder())
            print(json.dumps({"identity": identity.as_dict(), "modules": registry.names(), "tools": tools}, indent=2))
            registry.close()
            return 0
        if args.serve_ui:
            from adlc_mcp.serve import start_hub, stop_hub
            _, registry, _ = build_server(config, identity, server=_Recorder())
            http_server, port, _ = start_hub(registry, config, port=args.port)
            print(f"Insight Hub UI: http://127.0.0.1:{port}/ui/")
            stop_event = Event()
            signal.signal(signal.SIGINT, lambda *_: stop_event.set())
            signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
            try:
                stop_event.wait()
            finally:
                stop_hub(http_server)
                registry.close()
            return 0
        server, registry, _ = build_server(config, identity)
    except (AdlcError, ValueError) as exc:
        print(f"adlc-mcp: {exc}", file=sys.stderr)
        return 2
    try:
        server.run()
    finally:
        registry.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
