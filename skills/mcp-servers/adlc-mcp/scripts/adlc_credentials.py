#!/usr/bin/env python3
"""Mint and inspect pilot-grade ADLC credentials (only token hashes are stored).

    adlc_credentials.py issue --actor-type AGENT --actor-id agent:developer --agent-role developer --tool claude-code
    adlc_credentials.py issue --actor-type HUMAN --actor-id alice --human-role human:tech-lead
    adlc_credentials.py issue --actor-type SYSTEM --actor-id ci:github-actions --tool ci
    ADLC_TOKEN=... adlc_credentials.py whoami
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from adlc_mcp.kernel.errors import AdlcError  # noqa: E402
from adlc_mcp.kernel.identity import credentials_path, issue_credential, resolve_identity, revoke_credential  # noqa: E402
from adlc_mcp.kernel.vocab import ACTOR_TYPES, AGENT_ROLES, HUMAN_APPROVERS, TOOLS  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    iss = sub.add_parser("issue")
    iss.add_argument("--actor-type", required=True, choices=ACTOR_TYPES)
    iss.add_argument("--actor-id", required=True)
    iss.add_argument("--agent-role", choices=AGENT_ROLES)
    iss.add_argument("--tool", choices=TOOLS)
    iss.add_argument("--model-id")
    iss.add_argument("--human-role", action="append", default=[], choices=HUMAN_APPROVERS)
    iss.add_argument("--expires-in", type=int, metavar="HOURS",
                     help="credential expires after this many hours (CISA 2026: short-lived credentials)")
    iss.add_argument("--credentials")
    who = sub.add_parser("whoami")
    who.add_argument("--credentials")
    rev = sub.add_parser("revoke")
    rev.add_argument("token", help="the plaintext token to revoke")
    rev.add_argument("--credentials")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "issue":
            expires_at = None
            if args.expires_in:
                from datetime import datetime, timedelta, timezone
                expires_at = (datetime.now(timezone.utc) + timedelta(hours=args.expires_in)).isoformat()
            token = issue_credential(args.actor_type, args.actor_id, agent_role=args.agent_role, tool=args.tool,
                                     model_id=args.model_id, human_roles=args.human_role,
                                     credentials=args.credentials, expires_at=expires_at)
            result = {"token": token, "stored_in": str(credentials_path(args.credentials))}
            if expires_at:
                result["expires_at"] = expires_at
            print(json.dumps(result))
        elif args.cmd == "revoke":
            ok = revoke_credential(args.token, credentials=args.credentials)
            print(json.dumps({"revoked": ok}))
            return 0 if ok else 1
        else:
            print(json.dumps(resolve_identity(credentials=args.credentials).as_dict()))
    except AdlcError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
