#!/usr/bin/env python3
"""BM25 similar-task search against the ADLC Evidence Ledger.

Finds historical evidence entries most relevant to a query.

Usage:
    python adlc_related.py --query "authentication token refresh"
    python adlc_related.py --query "payment flow" --db .adlc/evidence_ledger.db --top 5
    python adlc_related.py --query "login bug" --pretty
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "skills" / "mcp-servers" / "adlc-mcp" / "src"))


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def search(db_path: str, query: str, top_n: int = 10) -> list[dict]:
    from adlc_mcp.modules.evidence_ledger.bm25 import bm25_search

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT e.entry_id, e.classification, e.agent_role, e.source_type, "
            "e.change_set_id, e.timestamp, c.content "
            "FROM evidence e LEFT JOIN evidence_content c ON c.entry_id = e.entry_id "
            "ORDER BY e.seq DESC LIMIT 1000"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    corpus = [dict(r) for r in rows]
    if not corpus:
        return []

    return bm25_search(query, corpus, content_key="content", top_n=top_n)


def main() -> None:
    parser = argparse.ArgumentParser(description="ADLC similar-task BM25 search")
    parser.add_argument("--query", required=True, help="Search query text")
    parser.add_argument("--db", default=os.path.join(".adlc", "evidence_ledger.db"),
                        help="Path to evidence_ledger.db")
    parser.add_argument("--top", type=int, default=10, help="Number of results")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    args = parser.parse_args()

    results = search(args.db, args.query, args.top)

    if args.pretty:
        print(f"Query: {args.query}")
        print(f"Results: {len(results)}\n")
        for i, r in enumerate(results, 1):
            content = (r.get("content") or "")[:120]
            print(f"  {i}. [{r.get('classification', '?')}] score={r.get('relevance_score', 0):.3f}")
            print(f"     role={r.get('agent_role', '?')}  cs={r.get('change_set_id', '?')}")
            print(f"     {content}")
            print()
    else:
        json.dump({"query": args.query, "results": results}, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
