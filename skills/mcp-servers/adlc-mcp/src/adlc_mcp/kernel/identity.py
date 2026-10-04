"""Identity and authentication (plan §4.3 identity-and-auth, §5.8, §6).

Pilot-grade model:
  * One credential (bearer token) per role session. The server process reads the token
    from ``ADLC_TOKEN`` and resolves it against a credentials file (``ADLC_CREDENTIALS``,
    default ``~/.adlc/credentials.json``) that stores only token *hashes*.
  * ``actor_type`` / ``actor_id`` / ``agent_role`` / ``tool`` come from the credential —
    never from a tool-call argument.
  * Beyond a single-user, single-workspace pilot, replace :func:`resolve_identity` with the
    organisation's OAuth2 / mTLS / RBAC layer; nothing else changes because modules only
    ever see an :class:`Identity`.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .errors import AuthError, PermissionDenied
from .vocab import ACTOR_TYPES, AGENT_ROLES, HUMAN_APPROVERS, TOOLS


@dataclass(frozen=True)
class Identity:
    actor_type: str
    actor_id: str
    agent_role: str | None = None
    tool: str | None = None
    model_id: str | None = None
    human_roles: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.actor_type not in ACTOR_TYPES:
            raise AuthError(f"invalid actor_type in credential: {self.actor_type!r}")
        if self.actor_type == "AGENT" and self.agent_role not in AGENT_ROLES:
            raise AuthError(f"AGENT credential has unknown agent_role: {self.agent_role!r}")
        if self.actor_type != "AGENT" and self.agent_role is not None:
            raise AuthError("agent_role is only valid on AGENT credentials")
        if self.tool is not None and self.tool not in TOOLS:
            raise AuthError(f"invalid tool in credential: {self.tool!r}")
        for role in self.human_roles:
            if self.actor_type != "HUMAN" or role not in HUMAN_APPROVERS:
                raise AuthError(f"invalid human role {role!r} for {self.actor_type} credential")

    @property
    def is_agent(self) -> bool:
        return self.actor_type == "AGENT"

    @property
    def is_human(self) -> bool:
        return self.actor_type == "HUMAN"

    @property
    def is_system(self) -> bool:
        return self.actor_type == "SYSTEM"

    def require(self, *actor_types: str, action: str) -> None:
        if self.actor_type not in actor_types:
            raise PermissionDenied(
                f"{action} requires actor_type in {actor_types}; caller is {self.actor_type}:{self.actor_id}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "agent_role": self.agent_role,
            "tool": self.tool,
            "model_id": self.model_id,
            "human_roles": list(self.human_roles),
        }


def hash_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def credentials_path(path: str | os.PathLike | None = None) -> Path:
    if path:
        return Path(path)
    env = os.environ.get("ADLC_CREDENTIALS")
    return Path(env) if env else Path.home() / ".adlc" / "credentials.json"


def _load(path: str | os.PathLike | None) -> dict[str, dict[str, Any]]:
    p = credentials_path(path)
    if not p.exists():
        raise AuthError(f"credentials file not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    tokens = data.get("tokens", data)
    if not isinstance(tokens, dict):
        raise AuthError("credentials file must map token-hash -> identity")
    return tokens


def resolve_identity(token: str | None = None, credentials: str | os.PathLike | None = None) -> Identity:
    """Resolve a bearer token to a server-trusted Identity. Never trusts caller-asserted fields."""
    token = token if token is not None else os.environ.get("ADLC_TOKEN")
    if not token:
        raise AuthError("no credential presented (set ADLC_TOKEN for this role session)")
    entry = _load(credentials).get(hash_token(token))
    if entry is None:
        raise AuthError("credential not recognised")
    if entry.get("revoked"):
        raise AuthError("credential revoked")
    if entry.get("expires_at"):
        from datetime import datetime, timezone
        try:
            exp = datetime.fromisoformat(entry["expires_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp:
                raise AuthError(f"credential expired at {entry['expires_at']}")
        except (ValueError, TypeError):
            raise AuthError("credential has an invalid expires_at value")
    return Identity(
        actor_type=entry["actor_type"],
        actor_id=entry["actor_id"],
        agent_role=entry.get("agent_role"),
        tool=entry.get("tool"),
        model_id=entry.get("model_id"),
        human_roles=tuple(entry.get("human_roles", ())),
    )


def system_identity(name: str, tool: str | None = None) -> Identity:
    """Identity for in-process SYSTEM writers (hooks, ingesters). Never reachable via an MCP tool."""
    return Identity(actor_type="SYSTEM", actor_id=name, tool=tool)


def issue_credential(
    actor_type: str,
    actor_id: str,
    *,
    agent_role: str | None = None,
    tool: str | None = None,
    model_id: str | None = None,
    human_roles: Iterable[str] = (),
    credentials: str | os.PathLike | None = None,
    expires_at: str | None = None,
) -> str:
    """Mint a token, store only its hash, and return the plaintext token once."""
    ident = Identity(actor_type, actor_id, agent_role, tool, model_id, tuple(human_roles))  # validates
    p = credentials_path(credentials)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"tokens": {}}
    token = secrets.token_urlsafe(32)
    entry = {k: v for k, v in ident.as_dict().items() if v not in (None, [])}
    if expires_at:
        entry["expires_at"] = expires_at
    data.setdefault("tokens", {})[hash_token(token)] = entry
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return token


def revoke_credential(
    token: str,
    credentials: str | os.PathLike | None = None,
) -> bool:
    """Revoke a credential by marking it in the credentials file."""
    p = credentials_path(credentials)
    if not p.exists():
        return False
    data = json.loads(p.read_text(encoding="utf-8"))
    tokens = data.get("tokens", data)
    h = hash_token(token)
    if h not in tokens:
        return False
    tokens[h]["revoked"] = True
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return True
