"""Runtime configuration, read from the environment.

| Variable | Default | Meaning |
|---|---|---|
| ``ADLC_DATA_DIR`` | ``.adlc`` | Directory holding one SQLite file per module |
| ``ADLC_WORKSPACE_ID`` | — | Explicit workspace identifier; derived from manifest/git/cwd when absent |
| ``ADLC_MODULES`` | ``evidence_ledger`` | Comma-separated modules to enable (Phase 0: evidence_ledger; Phase 2: + change_management, work_planning; Phase 3: + contract_registry) |
| ``ADLC_LEDGER_DB`` | — | Override the evidence_ledger database file |
| ``ADLC_PLATFORM_RELEASE_SHA`` | ``unversioned`` | Platform release recorded on every ledger entry |
| ``ADLC_CREDENTIALS`` | ``~/.adlc/credentials.json`` | Pilot credentials file (token hashes) |
| ``ADLC_EVIDENCE_RETENTION_DAYS`` | ``90`` | Local evidence payload retention (ADR 0006); minimum 1 |
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

KNOWN_MODULES = ("evidence_ledger", "change_management", "contract_registry", "work_planning",
                 "event_journal", "stage_engine", "concurrency", "parallel_coordinator")
MANIFEST_NAME = "adlc.workspace.yaml"


def parse_modules(value: str | None) -> tuple[str, ...]:
    names = tuple(n.strip() for n in (value or "evidence_ledger").split(",") if n.strip())
    unknown = [n for n in names if n not in KNOWN_MODULES]
    if unknown:
        raise ValueError(f"unknown module(s) {unknown}; known: {KNOWN_MODULES}")
    return names


def _derive_workspace_id() -> str | None:
    env = os.environ.get("ADLC_WORKSPACE_ID")
    if env:
        return env
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        manifest = parent / MANIFEST_NAME
        if manifest.is_file():
            try:
                import json
                text = manifest.read_text(encoding="utf-8")
                data = json.loads(text)
                system = data.get("system")
                if system:
                    return system
            except Exception:
                pass
            break
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return "git-" + hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:16]
    except Exception:
        pass
    return "local-" + hashlib.sha256(str(cwd).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Config:
    data_dir: Path = Path(".adlc")
    workspace_id: str | None = None
    modules: tuple[str, ...] = ("evidence_ledger",)
    platform_release_sha: str = "unversioned"
    evidence_retention_days: int = 90
    db_overrides: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def from_env(cls, modules: str | None = None, data_dir: str | None = None,
                 workspace_id: str | None = ...) -> "Config":
        overrides = {}
        if os.environ.get("ADLC_LEDGER_DB"):
            overrides["evidence_ledger"] = Path(os.environ["ADLC_LEDGER_DB"])
        ws = _derive_workspace_id() if workspace_id is ... else workspace_id
        return cls(
            data_dir=Path(data_dir or os.environ.get("ADLC_DATA_DIR", ".adlc")),
            workspace_id=ws,
            modules=parse_modules(modules if modules is not None else os.environ.get("ADLC_MODULES")),
            platform_release_sha=os.environ.get("ADLC_PLATFORM_RELEASE_SHA", "unversioned"),
            evidence_retention_days=int(os.environ.get("ADLC_EVIDENCE_RETENTION_DAYS", "90")),
            db_overrides=overrides,
        )

    def db_path(self, module: str) -> Path:
        """Each module owns its own SQLite file — no shared tables, no cross-module joins.
        Per-workspace: databases are namespaced under data_dir/workspace_id/ so concurrent
        sessions on different projects never share a ledger."""
        if module in self.db_overrides:
            return self.db_overrides[module]
        base = self.data_dir
        if self.workspace_id:
            base = base / self.workspace_id
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{module}.db"
