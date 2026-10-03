"""SQLite connection factory, per-module migrations runner, and the hash-chained append helper."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Callable

from .util import GENESIS_HASH, now_iso, row_digest


def connect(path: str | os.PathLike) -> sqlite3.Connection:
    p = Path(path)
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), isolation_level=None, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run_migrations(conn: sqlite3.Connection, module: str, migrations_dir: str | os.PathLike) -> list[str]:
    """Apply ``NNNN_*.sql`` files in order, once each. Returns the names applied this call."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " module TEXT NOT NULL, version TEXT NOT NULL, applied_at TEXT NOT NULL,"
        " PRIMARY KEY (module, version))"
    )
    done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations WHERE module = ?", (module,))}
    applied = []
    for f in sorted(Path(migrations_dir).glob("[0-9][0-9][0-9][0-9]_*.sql")):
        if f.name in done:
            continue
        conn.executescript("BEGIN;\n" + f.read_text(encoding="utf-8") + "\nCOMMIT;")
        conn.execute(
            "INSERT INTO schema_migrations (module, version, applied_at) VALUES (?, ?, ?)",
            (module, f.name, now_iso()),
        )
        applied.append(f.name)
    return applied


def append_chained(
    conn: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
    after_insert: Callable[[sqlite3.Connection, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Insert into a hash-chained, append-only table (columns ``seq``, ``prev_hash``, ``row_hash``).

    Each row's hash covers its own content and the previous row's hash, so any edit,
    deletion, or reordering is detectable by :func:`verify_chain` even on a local file.
    ``after_insert`` runs inside the same transaction (e.g. to store an unchained payload).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        last = conn.execute(f"SELECT seq, row_hash FROM {table} ORDER BY seq DESC LIMIT 1").fetchone()
        seq = (last["seq"] + 1) if last else 1
        prev_hash = last["row_hash"] if last else GENESIS_HASH
        full = dict(row, seq=seq, prev_hash=prev_hash)
        full["row_hash"] = row_digest(prev_hash, full)
        cols = ", ".join(f'"{c}"' for c in full)
        marks = ", ".join("?" for _ in full)
        conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(full.values()))
        if after_insert is not None:
            after_insert(conn, full)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return full


def verify_chain(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    prev = GENESIS_HASH
    expected = 1
    checked = 0
    for r in conn.execute(f"SELECT * FROM {table} ORDER BY seq"):
        row = dict(r)
        problem = None
        if row["seq"] != expected:
            problem = f"sequence gap: expected {expected}, found {row['seq']}"
        elif row["prev_hash"] != prev:
            problem = "prev_hash does not match previous row"
        elif row_digest(prev, row) != row["row_hash"]:
            problem = "row_hash mismatch (content altered)"
        if problem:
            return {"table": table, "ok": False, "checked": checked, "first_bad_seq": row["seq"], "problem": problem}
        prev = row["row_hash"]
        expected += 1
        checked += 1
    return {"table": table, "ok": True, "checked": checked, "head_hash": prev}
