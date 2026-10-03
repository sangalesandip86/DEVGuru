"""Test support: puts src/ on sys.path and builds temp data dirs and credentials."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adlc_mcp.kernel.config import Config  # noqa: E402
from adlc_mcp.kernel.identity import Identity, issue_credential, resolve_identity  # noqa: E402

DEVELOPER = Identity("AGENT", "agent:developer", agent_role="developer", tool="claude-code", model_id="model-a")
CODE_REVIEWER = Identity("AGENT", "agent:code-reviewer", agent_role="code-reviewer", tool="copilot", model_id="model-b")
SECURITY = Identity("AGENT", "agent:security-reviewer", agent_role="security-reviewer", tool="copilot", model_id="model-b")
HUMAN_LEAD = Identity("HUMAN", "alice", tool="claude-code", human_roles=("human:tech-lead",))
CI = Identity("SYSTEM", "ci:github-actions", tool="ci")


class TempEnv:
    """A temp data dir + Config. Use as a context manager or call close()."""

    def __init__(self, modules: str = "evidence_ledger") -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = Path(self._tmp.name)
        self.config = Config.from_env(modules=modules, data_dir=str(self.dir))
        self.credentials = self.dir / "credentials.json"

    def issue(self, actor_type: str, actor_id: str, **kw) -> str:
        return issue_credential(actor_type, actor_id, credentials=self.credentials, **kw)

    def resolve(self, token: str) -> Identity:
        return resolve_identity(token, self.credentials)

    def close(self) -> None:
        self._tmp.cleanup()

    def __enter__(self) -> "TempEnv":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
