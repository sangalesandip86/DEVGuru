#!/usr/bin/env python3
"""Evidence Ledger CLI — the hook-facing write path. Not an MCP tool.

    append-fact   read one JSON object on stdin and append a FACT as SYSTEM hook:<name>
                  {run_id, tool, source_type, content, source, change_set_id?}
                  hook name: --hook, else $ADLC_HOOK_NAME, else "unknown"
    verify        verify the hash chains and content commitments; exit 1 if any is broken
    purge         delete evidence payloads older than $ADLC_EVIDENCE_RETENTION_DAYS (default 90);
                  chained rows stay, so verify still passes (run it daily, e.g. from cron/CI)
    query         print entries as JSON (filters: --change-set, --classification, --role, --trust)

Database: $ADLC_LEDGER_DB, else $ADLC_DATA_DIR/evidence_ledger.db (default .adlc/).
Optional hardening: if $ADLC_REQUIRE_HOOK_TOKEN=1, append-fact requires $ADLC_HOOK_TOKEN to resolve
to a SYSTEM credential, so an agent with shell access cannot impersonate a hook.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from adlc_mcp.kernel.config import Config  # noqa: E402
from adlc_mcp.kernel.errors import AdlcError  # noqa: E402
from adlc_mcp.kernel.identity import resolve_identity, system_identity  # noqa: E402
from adlc_mcp.modules.evidence_ledger.api import open_ledger  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="ledger database path (overrides env)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    af = sub.add_parser("append-fact")
    af.add_argument("--hook", default=None)
    sub.add_parser("verify")
    sub.add_parser("purge")
    q = sub.add_parser("query")
    q.add_argument("--change-set")
    q.add_argument("--classification")
    q.add_argument("--role")
    q.add_argument("--trust")
    q.add_argument("--limit", type=int, default=100)
    args = ap.parse_args(argv)

    config = Config.from_env()
    ledger = open_ledger(args.db or config.db_path("evidence_ledger"), config.platform_release_sha,
                         config.evidence_retention_days)
    try:
        if args.cmd == "append-fact":
            if os.environ.get("ADLC_REQUIRE_HOOK_TOKEN") == "1":
                resolve_identity(os.environ.get("ADLC_HOOK_TOKEN")).require("SYSTEM", action="append-fact")
            payload = json.loads(sys.stdin.read() or "{}")
            hook = args.hook or os.environ.get("ADLC_HOOK_NAME") or "unknown"
            entry = ledger.append_fact(hook, payload)
            print(json.dumps({"entry_id": entry["entry_id"], "trust_level": entry["trust_level"],
                              "row_hash": entry["row_hash"]}))
        elif args.cmd == "verify":
            results = ledger.verify()
            print(json.dumps(results, indent=2))
            return 0 if all(r["ok"] for r in results) else 1
        elif args.cmd == "purge":
            print(json.dumps(ledger.purge_expired_content()))
        else:
            reader = system_identity("cli:query")
            rows = ledger.query_evidence(reader, change_set_id=args.change_set, classification=args.classification,
                                         actor_role=args.role, trust_level=args.trust, limit=args.limit)
            print(json.dumps(rows, indent=2))
    except (AdlcError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
