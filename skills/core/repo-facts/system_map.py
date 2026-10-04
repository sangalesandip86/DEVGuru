#!/usr/bin/env python3
"""Build system-map.json from API contracts, env/host literals and optional Backstage catalog.

Aggregates:
  - OpenAPI/AsyncAPI specs → service nodes with endpoints
  - .proto files → gRPC service nodes
  - env/host literals (URL-like strings in .env* files) → external edges
  - Backstage catalog-info.yaml (if present) → service metadata
  - scan-api-calls.py output (if --api-scan provided) → cross-service edges

Output: .adlc/catalog/system-map.json

Usage:
    python system_map.py <repo_root> [--api-scan api-deps.json] [--stdout] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".gradle", "coverage", ".tox",
}

OPENAPI_RE = re.compile(r'"openapi"\s*:\s*"[23]', re.I)
ASYNCAPI_RE = re.compile(r'"asyncapi"\s*:\s*"[23]|^asyncapi:\s+["\']?[23]', re.I | re.M)
PROTO_SERVICE_RE = re.compile(r"^\s*service\s+(\w+)\s*\{", re.M)
PROTO_RPC_RE = re.compile(r"^\s*rpc\s+(\w+)\s*\(", re.M)
ENV_URL_RE = re.compile(r"^[A-Z_]+=\s*(https?://[^\s]+)", re.M)
BACKSTAGE_RE = re.compile(r"kind:\s*Component", re.I)


def _iter_files(root: Path, extensions: set[str], max_files: int = 50_000):
    count = 0
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in SKIP_DIRS:
                    stack.append(p)
            elif p.is_file() and p.suffix in extensions:
                yield p
                count += 1
                if count >= max_files:
                    return


def _read(p: Path, limit: int = 500_000) -> str:
    try:
        return p.read_bytes()[:limit].decode("utf-8", errors="replace")
    except OSError:
        return ""


def _parse_openapi_title(text: str) -> str | None:
    m = re.search(r'"title"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1)
    m = re.search(r"^title:\s+(.+)$", text, re.M)
    return m.group(1).strip().strip("'\"") if m else None


def _parse_openapi_paths(text: str) -> list[str]:
    paths = re.findall(r'"(/[^"]+)"\s*:\s*\{', text)
    if not paths:
        paths = re.findall(r"^  (/[^\s:]+)\s*:", text, re.M)
    return paths


def _parse_asyncapi_channels(text: str) -> list[str]:
    channels = re.findall(r'"([^"]+)"\s*:\s*\{[^}]*"(?:subscribe|publish)"', text)
    if not channels:
        channels = re.findall(r"^  ([^\s:]+)\s*:", text, re.M)
    return channels


def scan_contracts(root: Path) -> list[dict]:
    services: list[dict] = []

    for p in _iter_files(root, {".yaml", ".yml", ".json"}):
        rel = p.relative_to(root).as_posix()
        text = _read(p)
        if OPENAPI_RE.search(text):
            title = _parse_openapi_title(text) or rel
            paths = _parse_openapi_paths(text)
            services.append({
                "name": title, "type": "http", "source": rel,
                "evidence_level": "STATIC",
                "endpoints": [{"method": "ANY", "path": ep} for ep in paths[:50]],
            })
        elif ASYNCAPI_RE.search(text):
            title = _parse_openapi_title(text) or rel
            channels = _parse_asyncapi_channels(text)
            services.append({
                "name": title, "type": "async", "source": rel,
                "evidence_level": "STATIC",
                "channels": channels[:50],
            })

    for p in _iter_files(root, {".proto"}):
        rel = p.relative_to(root).as_posix()
        text = _read(p)
        for svc_name in PROTO_SERVICE_RE.findall(text):
            rpcs = PROTO_RPC_RE.findall(text)
            services.append({
                "name": svc_name, "type": "grpc", "source": rel,
                "evidence_level": "STATIC",
                "rpcs": rpcs[:50],
            })

    return services


def scan_env_hosts(root: Path) -> list[dict]:
    externals: list[dict] = []
    for p in root.glob(".env*"):
        if not p.is_file():
            continue
        text = _read(p)
        for url in ENV_URL_RE.findall(text):
            externals.append({"url": url, "source": p.name, "evidence_level": "STATIC"})
    return externals


def scan_backstage(root: Path) -> list[dict]:
    metadata: list[dict] = []
    for name in ("catalog-info.yaml", "catalog-info.yml"):
        p = root / name
        if p.is_file():
            text = _read(p)
            if BACKSTAGE_RE.search(text):
                name_m = re.search(r"name:\s+(.+)", text)
                owner_m = re.search(r"owner:\s+(.+)", text)
                metadata.append({
                    "name": name_m.group(1).strip() if name_m else "unknown",
                    "owner": owner_m.group(1).strip() if owner_m else "unknown",
                    "source": name,
                })
    return metadata


def build_system_map(root: Path, api_scan: dict | None = None) -> dict:
    services = scan_contracts(root)
    externals = scan_env_hosts(root)
    backstage = scan_backstage(root)

    edges: list[dict] = []
    if api_scan:
        for edge in api_scan.get("cross_repo_edges", []):
            edges.append({
                "from": edge.get("caller_repo", "unknown"),
                "to": edge.get("callee_repo", "unknown"),
                "path": edge.get("path", ""),
                "confidence": edge.get("confidence", "medium"),
                "evidence_level": "STATIC",
            })

    return {
        "classification": "FACT",
        "source": "system_map.py",
        "root": root.name,
        "services": services,
        "external_hosts": externals,
        "edges": edges,
        "backstage": backstage,
    }


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_root")
    ap.add_argument("--api-scan", help="output from scan-api-calls.py (cross-repo edges)")
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--out", help="output directory (default: <repo_root>/.adlc/catalog)")
    args = ap.parse_args(argv)

    root = Path(args.repo_root).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}), file=sys.stderr)
        return 2

    api_scan = None
    if args.api_scan:
        api_scan = json.loads(Path(args.api_scan).read_text(encoding="utf-8"))

    result = build_system_map(root, api_scan)
    if args.stdout:
        print(json.dumps(result, indent=2))
        return 0

    out = Path(args.out) if args.out else root / ".adlc" / "catalog"
    out.mkdir(parents=True, exist_ok=True)
    (out / "system-map.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"written": str(out / "system-map.json"),
                      "services": len(result["services"]),
                      "edges": len(result["edges"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
