"""Contract Registry persistence. Owns ``contract_registry.db``; no other module touches it."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from adlc_mcp.kernel import db
from adlc_mcp.kernel.util import canonical_json, loads_or_none

MODULE = "contract_registry"
MIGRATIONS = Path(__file__).parent / "migrations"
_JSON = ("consumers", "spec", "contract_versions", "request", "result")


def _decode(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for c in _JSON:
        if c in out and isinstance(out[c], str):
            out[c] = loads_or_none(out[c])
    return out


class ContractStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def migrate(self) -> list[str]:
        return db.run_migrations(self.conn, MODULE, MIGRATIONS)

    def get_contract(self, contract_id: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)).fetchone())

    def insert_contract(self, row: dict[str, Any]) -> None:
        row = dict(row, consumers=canonical_json(row["consumers"]))
        self.conn.execute(f"INSERT INTO contracts ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
                          list(row.values()))

    def set_consumers(self, contract_id: str, consumers: list[str]) -> None:
        self.conn.execute("UPDATE contracts SET consumers = ? WHERE contract_id = ?",
                          (canonical_json(consumers), contract_id))

    def insert_version(self, row: dict[str, Any]) -> None:
        row = dict(row, spec=canonical_json(row["spec"]))
        self.conn.execute(
            f"INSERT INTO contract_versions ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
            list(row.values()))

    def get_version(self, contract_id: str, version: str, party: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute(
            "SELECT * FROM contract_versions WHERE contract_id = ? AND version = ? AND party = ?",
            (contract_id, version, party)).fetchone())

    def latest_version(self, contract_id: str, party: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute(
            "SELECT * FROM contract_versions WHERE contract_id = ? AND party = ? ORDER BY rowid DESC LIMIT 1",
            (contract_id, party)).fetchone())

    def append_deployment(self, row: dict[str, Any]) -> dict[str, Any]:
        return _decode(db.append_chained(self.conn, "deployments", dict(
            row, contract_versions=canonical_json(row["contract_versions"]))))

    def current_deployment(self, app: str, environment: str) -> dict[str, Any] | None:
        return _decode(self.conn.execute(
            "SELECT * FROM deployments WHERE app = ? AND environment = ? ORDER BY seq DESC LIMIT 1",
            (app, environment)).fetchone())

    def deployment_history(self, app: str, environment: str) -> list[dict[str, Any]]:
        return [_decode(r) for r in self.conn.execute(
            "SELECT * FROM deployments WHERE app = ? AND environment = ? ORDER BY seq", (app, environment))]

    def append_result(self, row: dict[str, Any]) -> dict[str, Any]:
        return _decode(db.append_chained(self.conn, "check_results", dict(
            row, request=canonical_json(row["request"]), result=canonical_json(row["result"]))))

    def verify(self) -> list[dict[str, Any]]:
        return [db.verify_chain(self.conn, "deployments"), db.verify_chain(self.conn, "check_results")]
