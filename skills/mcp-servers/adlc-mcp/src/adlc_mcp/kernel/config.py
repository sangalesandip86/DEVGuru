"""Runtime configuration, read from the environment.

| Variable | Default | Meaning |
|---|---|---|
| ``ADLC_DATA_DIR`` | ``.adlc`` | Directory holding one SQLite file per module |
| ``ADLC_MODULES`` | ``evidence_ledger`` | Comma-separated modules to enable (Phase 0: evidence_ledger; Phase 2: + change_management, work_planning; Phase 3: + contract_registry) |
| ``ADLC_LEDGER_DB`` | — | Override the evidence_ledger database file |
| ``ADLC_PLATFORM_RELEASE_SHA`` | ``unversioned`` | Platform release recorded on every ledger entry |
| ``ADLC_CREDENTIALS`` | ``~/.adlc/credentials.json`` | Pilot credentials file (token hashes) |
| ``ADLC_EVIDENCE_RETENTION_DAYS`` | ``90`` | Local evidence payload retention (ADR 0006); minimum 1 |
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

KNOWN_MODULES = ("evidence_ledger", "change_management", "contract_registry", "work_planning")


def parse_modules(value: str | None) -> tuple[str, ...]:
    names = tuple(n.strip() for n in (value or "evidence_ledger").split(",") if n.strip())
    unknown = [n for n in names if n not in KNOWN_MODULES]
    if unknown:
        raise ValueError(f"unknown module(s) {unknown}; known: {KNOWN_MODULES}")
    return names


@dataclass(frozen=True)
class Config:
    data_dir: Path = Path(".adlc")
    modules: tuple[str, ...] = ("evidence_ledger",)
    platform_release_sha: str = "unversioned"
    evidence_retention_days: int = 90
    db_overrides: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def from_env(cls, modules: str | None = None, data_dir: str | None = None) -> "Config":
        overrides = {}
        if os.environ.get("ADLC_LEDGER_DB"):
            overrides["evidence_ledger"] = Path(os.environ["ADLC_LEDGER_DB"])
        return cls(
            data_dir=Path(data_dir or os.environ.get("ADLC_DATA_DIR", ".adlc")),
            modules=parse_modules(modules if modules is not None else os.environ.get("ADLC_MODULES")),
            platform_release_sha=os.environ.get("ADLC_PLATFORM_RELEASE_SHA", "unversioned"),
            evidence_retention_days=int(os.environ.get("ADLC_EVIDENCE_RETENTION_DAYS", "90")),
            db_overrides=overrides,
        )

    def db_path(self, module: str) -> Path:
        """Each module owns its own SQLite file — no shared tables, no cross-module joins."""
        return self.db_overrides.get(module, self.data_dir / f"{module}.db")
