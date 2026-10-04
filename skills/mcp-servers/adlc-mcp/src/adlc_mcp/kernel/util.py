"""Canonical JSON, hashing, and clock helpers."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

GENESIS_HASH = "0" * 64


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def dumps_or_none(obj: Any) -> str | None:
    return None if obj is None else canonical_json(obj)


def loads_or_none(text: str | None) -> Any:
    return None if text is None else json.loads(text)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def response_envelope(ok: bool, data: Any = None, *, scope: str | None = None,
                      warnings: list[str] | None = None, error: str | None = None) -> dict:
    """Standard response envelope so callers detect scope mismatches and staleness."""
    env: dict[str, Any] = {"ok": ok, "as_of": now_iso()}
    if scope:
        env["scope"] = scope
    if data is not None:
        env["data"] = data
    if warnings:
        env["warnings"] = warnings
    if error:
        env["error"] = error
    return env


def row_digest(prev_hash: str, row: dict[str, Any]) -> str:
    """Hash of a chained row: sha256(prev_hash + canonical JSON of its non-null columns except row_hash).

    NULL columns are omitted ("absent" == NULL) so a migration that adds a nullable column with
    ``ALTER TABLE … ADD COLUMN`` leaves every existing row's hash — and the chain — valid.
    """
    body = {k: v for k, v in row.items() if k != "row_hash" and v is not None}
    return sha256_hex(prev_hash + canonical_json(body))
