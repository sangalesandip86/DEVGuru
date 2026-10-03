#!/usr/bin/env python3
"""Static scan for runtime API dependencies (plan §4.5 dependency-discovery).

Finds, per repository:
  outbound - HTTP client calls (requests/httpx/fetch/axios/Go net/http/Java HTTP clients) and
             URL literals, i.e. services this repo calls
  inbound  - route definitions (Flask/FastAPI/Express/Spring/Go), i.e. APIs this repo serves

Outbound calls are resolved to a repository through --known-hosts (host or URL prefix -> repo).
A call whose target is not a literal URL, or whose host is not in --known-hosts, is reported as
UNRESOLVED — the cautious default (§5.3). Every entry carries evidence_level STATIC.

With several repos scanned together (--repo NAME=PATH ...), outbound paths are also matched against
other repos' inbound routes, producing cross-repo edges with confidence "medium".

Output: JSON on stdout. Exit codes: 0 ok, 2 usage error, 3 unresolved found with
--fail-on-unresolved.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SKIP_DIRS = {".git", "node_modules", "vendor", ".venv", "venv", "__pycache__", "dist", "build",
             "target", ".gradle"}
EXTS = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".kt", ".go"}

URL_LITERAL = r"""(?P<q>['"`])(?P<url>(?:https?://|/)[^'"`\s]*)(?P=q)"""

OUTBOUND = [
    ("python-requests", re.compile(r"\b(?:requests|httpx|session|client)\.(get|post|put|patch|delete|head|request)\(\s*(?:" + URL_LITERAL + r")?")),
    ("js-fetch", re.compile(r"\bfetch\(\s*(?:" + URL_LITERAL + r")?")),
    ("js-axios", re.compile(r"\baxios(?:\.(get|post|put|patch|delete|request))?\(\s*(?:" + URL_LITERAL + r")?")),
    ("go-http", re.compile(r"\bhttp\.(Get|Post|Head|NewRequest(?:WithContext)?)\(\s*(?:[^,)]*,\s*)?(?:" + URL_LITERAL + r")?")),
    ("java-resttemplate", re.compile(r"\brestTemplate\.(getForObject|getForEntity|postForObject|postForEntity|exchange|put|delete)\(\s*(?:" + URL_LITERAL + r")?")),
    ("java-webclient", re.compile(r"\.uri\(\s*(?:" + URL_LITERAL + r")?")),
    ("java-httpclient", re.compile(r"\bURI\.create\(\s*(?:" + URL_LITERAL + r")?")),
]
INBOUND = [
    ("python-decorator", re.compile(r"@\w+\.(get|post|put|patch|delete|route|api_route)\(\s*(['\"])([^'\"]+)\2")),
    ("express", re.compile(r"\b(?:app|router)\.(get|post|put|patch|delete|all|use)\(\s*(['\"`])(/[^'\"`]*)\2")),
    ("spring", re.compile(r"@(Get|Post|Put|Patch|Delete|Request)Mapping\(\s*(?:value\s*=\s*|path\s*=\s*)?(\")([^\"]+)\2")),
    ("go-handle", re.compile(r"\b(?:http|mux|r|router)\.(HandleFunc|Handle|Get|Post|Put|Delete)\(\s*(\")(/[^\"]*)\2")),
]
BARE_URL = re.compile(r"""['"`](https?://[^'"`\s]+)['"`]""")


def iter_files(root: Path):
    for p in root.rglob("*"):
        if p.suffix in EXTS and p.is_file() and not any(x in SKIP_DIRS for x in p.relative_to(root).parts):
            yield p


def normalize_route(path: str) -> str:
    path = re.sub(r"\{[^}]+\}|<[^>]+>|:\w+", "{}", path.split("?")[0])
    return "/" + path.strip("/")


def route_matches(path: str, route: str) -> bool:
    """A concrete path matches a route whose '{}' segments accept any single segment."""
    ps, rs = path.strip("/").split("/"), route.strip("/").split("/")
    return len(ps) == len(rs) and all(r == "{}" or r == q for q, r in zip(ps, rs))


def resolve_host(url: str, known_hosts: dict[str, str]) -> str | None:
    for prefix, repo in sorted(known_hosts.items(), key=lambda kv: -len(kv[0])):
        if url.startswith(prefix) or urlparse(url).netloc == prefix:
            return repo
    return None


def scan_repo(name: str, root: Path, known_hosts: dict[str, str]) -> dict:
    outbound, inbound = [], []
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            loc = f"{rel}:{lineno}"
            matched_spans = []
            for client, pat in OUTBOUND:
                for m in pat.finditer(line):
                    url = m.group("url")
                    matched_spans.append(m.span())
                    outbound.append({"client": client, "url": url, "location": loc})
            for framework, pat in INBOUND:
                for m in pat.finditer(line):
                    inbound.append({"framework": framework, "method": m.group(1).upper(),
                                    "route": normalize_route(m.group(3)), "location": loc})
            for m in BARE_URL.finditer(line):
                if not any(s <= m.start() <= e for s, e in matched_spans):
                    outbound.append({"client": "url-literal", "url": m.group(1), "location": loc})

    for call in outbound:
        url = call["url"]
        if not url:
            call.update(status="UNRESOLVED", target=None, reason="target not a literal URL")
        elif url.startswith("/"):
            call.update(status="UNRESOLVED", target=None, reason="relative path; base URL unknown")
        else:
            repo = resolve_host(url, known_hosts)
            call.update(status="RESOLVED" if repo else "UNRESOLVED", target=repo,
                        reason=None if repo else f"host {urlparse(url).netloc} not in known hosts")
        call["evidence_level"] = "STATIC"
    for route in inbound:
        route["evidence_level"] = "STATIC"
    return {"repo": name, "root": str(root), "outbound": outbound, "inbound": inbound}


def cross_match(repos: list[dict]) -> list[dict]:
    """Match unresolved relative/absolute outbound paths to other repos' inbound routes."""
    edges = []
    for src in repos:
        for call in src["outbound"]:
            if call["status"] == "RESOLVED" or not call["url"]:
                continue
            path = normalize_route(urlparse(call["url"]).path or call["url"])
            for dst in repos:
                if dst is src:
                    continue
                for route in dst["inbound"]:
                    if path != "/" and route_matches(path, route["route"]):
                        edges.append({"source": src["repo"], "target": dst["repo"], "type": "http",
                                      "route": path, "evidence_level": "STATIC", "confidence": "medium",
                                      "locations": [call["location"], route["location"]]})
    return edges


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Static scan for HTTP API calls and routes.")
    ap.add_argument("--repo", action="append", required=True, metavar="NAME=PATH",
                    help="repository to scan; repeat for multi-repo cross-matching")
    ap.add_argument("--known-hosts", type=Path,
                    help='JSON object mapping host or URL prefix to repo, e.g. {"billing.internal": "acme/billing"}')
    ap.add_argument("--fail-on-unresolved", action="store_true")
    args = ap.parse_args(argv)

    known = {}
    if args.known_hosts:
        try:
            known = json.loads(args.known_hosts.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(json.dumps({"error": f"cannot read --known-hosts: {exc}"}))
            return 2
    repos = []
    for spec in args.repo:
        name, sep, path = spec.partition("=")
        root = Path(path if sep else name)
        if not root.is_dir():
            print(json.dumps({"error": f"not a directory: {root}"}))
            return 2
        repos.append(scan_repo(name if sep else root.resolve().name, root.resolve(), known))

    edges = cross_match(repos)
    unresolved = sum(1 for r in repos for c in r["outbound"] if c["status"] == "UNRESOLVED")
    print(json.dumps({"repos": repos, "cross_repo_edges": edges, "unresolved_count": unresolved,
                      "note": "Static analysis only; dynamic URLs, service discovery, and message "
                              "queues are not covered. UNRESOLVED defaults to the cautious reading (§5.3)."},
                     indent=2))
    return 3 if args.fail_on_unresolved and unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
