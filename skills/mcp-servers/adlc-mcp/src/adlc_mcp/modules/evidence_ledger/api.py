"""Evidence Ledger — public surface. The ONLY file other code may import from this module.

Plan §6 Server 1 (record_evidence, query_evidence, record_incident, query_incidents,
record_correction). Identity is always a parameter resolved by the host from the
authenticated connection; no method accepts actor_type / actor_id / agent_role / trust_level.
"""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any, Protocol

from adlc_mcp.kernel import db
from adlc_mcp.kernel.config import Config
from adlc_mcp.kernel.errors import NotFound, PermissionDenied, ValidationError
from adlc_mcp.kernel.identity import Identity, system_identity
from adlc_mcp.kernel.util import dumps_or_none, now_iso

from . import domain
from .store import EvidenceStore

NAME = "evidence_ledger"


class EvidenceLedgerApi(Protocol):
    """What callers may rely on. A remote adapter implementing this replaces the in-process facade."""

    def record_evidence(self, identity: Identity, **kwargs: Any) -> dict[str, Any]: ...
    def record_correction(self, identity: Identity, **kwargs: Any) -> dict[str, Any]: ...
    def query_evidence(self, identity: Identity, **filters: Any) -> list[dict[str, Any]]: ...
    def record_incident(self, identity: Identity, **kwargs: Any) -> dict[str, Any]: ...
    def query_incidents(self, identity: Identity, **filters: Any) -> list[dict[str, Any]]: ...
    def record_lesson(self, identity: Identity, **fields: Any) -> dict[str, Any]: ...
    def query_lessons(self, identity: Identity, **filters: Any) -> list[dict[str, Any]]: ...
    def blocking_items(self, change_set_id: str) -> list[str]: ...
    def verify(self) -> list[dict[str, Any]]: ...


class EvidenceLedger:
    """In-process facade over the module's store and domain rules."""

    def __init__(self, conn: sqlite3.Connection, platform_release_sha: str = "unversioned",
                 retention_days: int = 90, repo_root: Path | None = None) -> None:
        if retention_days < 1:
            raise ValidationError("evidence retention must be at least 1 day")
        self._store = EvidenceStore(conn)
        self._release = platform_release_sha
        self._retention_days = retention_days
        self._repo_root = repo_root if repo_root is not None else _find_repo_root()

    def migrate(self) -> list[str]:
        applied = self._store.migrate()
        self._store.set_retention_days(self._retention_days)
        return applied

    # ---------------------------------------------------------------- record_evidence
    def record_evidence(
        self,
        identity: Identity,
        *,
        run_id: str,
        classification: str,
        content: str,
        source_type: str,
        source: str | None = None,
        change_set_id: str | None = None,
        input_references: list[str] | None = None,
        output_references: list[str] | None = None,
        decision_ids: list[str] | None = None,
        lifecycle_state: str | None = None,
        snapshot_id: str | None = None,
        signal_source: str | None = None,
        metadata: dict[str, Any] | None = None,
        model_id: str | None = None,
        tool: str | None = None,
        answers_entry_id: str | None = None,
    ) -> dict[str, Any]:
        if not run_id:
            raise ValidationError("run_id is required")
        referenced = self._store.get_entries(list(input_references or []))
        domain.validate_entry(
            identity, classification=classification, content=content, source=source,
            input_references=input_references, referenced=referenced, lifecycle_state=lifecycle_state,
            signal_source=signal_source, metadata=metadata,
        )
        parent_id = outcome = None
        if answers_entry_id:
            parent = self._require(answers_entry_id)
            if parent["classification"] not in ("QUESTION", "ASSUMPTION"):
                raise ValidationError("answers_entry_id must reference a QUESTION or ASSUMPTION")
            parent_id, outcome = answers_entry_id, "ANSWERED"
        return self._append(
            identity, run_id=run_id, classification=classification, content=content, source=source,
            source_type=source_type, referenced=referenced, change_set_id=change_set_id,
            input_references=input_references, output_references=output_references, decision_ids=decision_ids,
            lifecycle_state=lifecycle_state, snapshot_id=snapshot_id, signal_source=signal_source,
            metadata=metadata, model_id=model_id, tool=tool, parent_entry_id=parent_id, outcome_status=outcome,
        )

    # ---------------------------------------------------------------- record_correction
    def record_correction(
        self,
        identity: Identity,
        *,
        parent_entry_id: str,
        run_id: str,
        content: str,
        source_type: str,
        source: str | None = None,
        classification: str = "INFERENCE",
        input_references: list[str] | None = None,
        signal_source: str | None = None,
        model_id: str | None = None,
        tool: str | None = None,
    ) -> dict[str, Any]:
        """The only way to 'correct' a past entry: a new CHALLENGED entry pointing at it."""
        parent = self._require(parent_entry_id)
        refs = list(dict.fromkeys([*(input_references or []), parent_entry_id]))
        referenced = self._store.get_entries(refs)
        domain.validate_entry(
            identity, classification=classification, content=content, source=source, input_references=refs,
            referenced=referenced, lifecycle_state=None, signal_source=signal_source, metadata=None,
        )
        return self._append(
            identity, run_id=run_id, classification=classification, content=content, source=source,
            source_type=source_type, referenced=referenced, change_set_id=parent["change_set_id"],
            input_references=refs, signal_source=signal_source, model_id=model_id, tool=tool,
            parent_entry_id=parent_entry_id, outcome_status="CHALLENGED",
        )

    # ---------------------------------------------------------------- query_evidence
    def query_evidence(
        self,
        identity: Identity,
        *,
        change_set_id: str | None = None,
        actor_role: str | None = None,
        classification: str | None = None,
        trust_level: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = self._store.query_entries(
            {"change_set_id": change_set_id, "agent_role": actor_role, "classification": classification,
             "trust_level": trust_level},
            max(1, min(limit, 1000)),
        )
        for r in rows:
            r["derived_status"] = self._derived_status(r)
        return rows

    # ---------------------------------------------------------------- incidents (ADR 0006)
    def record_incident(self, identity: Identity, **fields: Any) -> dict[str, Any]:
        """A signal plus local evidence pointers. No free-text use-case content is accepted."""
        domain.reject_unknown_fields(fields, domain.INCIDENT_FIELDS, "record_incident")
        refs = self._store.get_entries(list(fields.get("evidence_refs") or []))
        domain.validate_incident(identity, fields, refs, self._failure_classes())
        note = fields.get("note")
        return self._store.append_incident({
            "incident_id": f"INC-{uuid.uuid4().hex[:12]}",
            "skill": fields["skill"],
            "step": fields["step"],
            "failure_class": fields.get("failure_class"),
            "signal_type": fields["signal_type"],
            "signal_source": fields["signal_source"],
            "verification_strength": dumps_or_none(fields.get("verification_strength")),
            "pattern_eligible": int(fields["pattern_eligible"]),
            "evidence_refs": dumps_or_none(list(fields["evidence_refs"])),
            "note": note,
            "note_author_type": identity.actor_type if note else None,
            "note_author_id": identity.actor_id if note else None,
            "actor_type": identity.actor_type,
            "actor_id": identity.actor_id,
            "agent_role": identity.agent_role,
            "platform_release_sha": self._release,
            "timestamp": now_iso(),
        })

    def query_incidents(
        self,
        identity: Identity,
        *,
        skill: str | None = None,
        step: str | None = None,
        failure_class: str | None = None,
        signal_type: str | None = None,
        signal_source: str | None = None,
        pattern_eligible_only: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Pointers and classes only — never evidence content (resolve evidence_refs through query_evidence)."""
        rows = self._store.query_incidents(
            {"skill": skill, "step": step, "failure_class": failure_class, "signal_type": signal_type,
             "signal_source": signal_source, "pattern_eligible": 1 if pattern_eligible_only else None},
            max(1, min(limit, 1000)),
        )
        return [{k: r[k] for k in _INCIDENT_VIEW} for r in rows]

    def incident_clusters(self, identity: Identity, *, min_incidents: int = 1) -> list[dict[str, Any]]:
        """Pattern-eligible incidents grouped by (skill, step, failure_class) — the improvement-review input."""
        clusters: dict[tuple, dict[str, Any]] = {}
        for r in self._store.query_incidents({"pattern_eligible": 1}, 100000):
            if not r["failure_class"]:
                continue
            key = (r["skill"], r["step"], r["failure_class"])
            c = clusters.setdefault(key, {"skill": key[0], "step": key[1], "failure_class": key[2],
                                          "incident_ids": [], "change_sets": set(), "last_seen": r["timestamp"]})
            c["incident_ids"].append(r["incident_id"])
            c["change_sets"] |= {e["change_set_id"] for e in self._store.get_entries(r["evidence_refs"])
                                 if e["change_set_id"]}
            c["last_seen"] = max(c["last_seen"], r["timestamp"])
        out = []
        for c in clusters.values():
            if len(c["incident_ids"]) >= min_incidents:
                out.append(dict(c, occurrences={"incidents": len(c["incident_ids"]),
                                                "change_sets": len(c.pop("change_sets")), "projects": 1}))
        return sorted(out, key=lambda c: -c["occurrences"]["incidents"])

    # ---------------------------------------------------------------- lessons (ADR 0006)
    def record_lesson(self, identity: Identity, **fields: Any) -> dict[str, Any]:
        """Record a sanitized lesson (scope PROJECT), or promote one to ORG.

        ORG: never from an AGENT; requires parent_lesson_id and approval_entry_id naming a HUMAN-authored
        APPROVED evidence entry whose output_references include the parent lesson. The ORG row copies the
        approved lesson's content; only a fresh sanitization_result is supplied.
        """
        domain.reject_unknown_fields(fields, domain.LESSON_FIELDS, "record_lesson")
        sanitization = domain.validate_sanitization(fields.get("sanitization_result"))
        scope = fields.get("scope") or "PROJECT"
        if scope not in domain.LESSON_SCOPES:
            raise ValidationError(f"scope must be one of {domain.LESSON_SCOPES}")
        if scope == "ORG":
            return self._promote_lesson(identity, fields, sanitization)
        if fields.get("parent_lesson_id") or fields.get("approval_entry_id"):
            raise ValidationError("parent_lesson_id/approval_entry_id apply only to an ORG promotion")
        domain.validate_lesson_content(fields, self._failure_classes())
        incident_refs = fields.get("incident_refs")
        if not isinstance(incident_refs, list) or not incident_refs:
            raise ValidationError("incident_refs must list the cluster's incident_ids")
        incidents = self._store.get_incidents(incident_refs)
        if len(incidents) != len(set(incident_refs)):
            raise ValidationError("incident_refs not found in this ledger")
        cluster = (fields["skill"], fields["step"], fields["failure_class"])
        if any((i["skill"], i["step"], i["failure_class"]) != cluster for i in incidents):
            raise ValidationError("every referenced incident must belong to the lesson's (skill, step, failure_class)")
        failed = self._store.get_entries([ref for i in incidents for ref in i["evidence_refs"]])
        domain.check_not_self_authored(identity, domain.failing_actors(failed), "lesson")
        return self._append_lesson(identity, {
            "parent_lesson_id": None,
            "skill": fields["skill"],
            "step": fields["step"],
            "failure_class": fields["failure_class"],
            "occurrences": dumps_or_none(fields["occurrences"]),
            "what_failed": fields["what_failed"],
            "advice": fields["advice"],
            "check": fields.get("check"),
            "remedy_kind": fields["remedy_kind"],
            "reproduction_ref": fields.get("reproduction_ref"),
            "incident_refs": dumps_or_none(list(incident_refs)),
            "scope": "PROJECT",
            "approval_entry_id": None,
        }, sanitization)

    def _promote_lesson(self, identity: Identity, fields: dict[str, Any], sanitization: dict[str, Any]):
        if identity.is_agent:
            raise PermissionDenied("agents can never set lesson scope ORG; promotion follows a human APPROVED")
        content_keys = set(fields) - {"scope", "parent_lesson_id", "approval_entry_id", "sanitization_result"}
        if content_keys:
            raise ValidationError(f"an ORG promotion copies the approved lesson; do not resupply {sorted(content_keys)}")
        parent = self._store.get_lesson(fields.get("parent_lesson_id") or "")
        if parent is None or parent["scope"] != "PROJECT":
            raise ValidationError("parent_lesson_id must name an existing PROJECT lesson")
        approval = self._store.get_entry(fields.get("approval_entry_id") or "")
        if approval is None or approval["actor_type"] != "HUMAN" or approval["lifecycle_state"] != "APPROVED":
            raise PermissionDenied("approval_entry_id must name a HUMAN-authored APPROVED entry")
        if parent["lesson_id"] not in (approval["output_references"] or []):
            raise PermissionDenied("the APPROVED entry must reference the lesson in output_references")
        keep = ("skill", "step", "failure_class", "what_failed", "advice", "check", "remedy_kind", "reproduction_ref")
        row = {k: parent[k] for k in keep}
        row.update(parent_lesson_id=parent["lesson_id"], occurrences=dumps_or_none(parent["occurrences"]),
                   incident_refs=dumps_or_none(parent["incident_refs"]), scope="ORG",
                   approval_entry_id=approval["entry_id"])
        return self._append_lesson(identity, row, sanitization)

    def _append_lesson(self, identity: Identity, row: dict[str, Any], sanitization: dict[str, Any]):
        return self._store.append_lesson(dict(
            row, lesson_id=f"LES-{uuid.uuid4().hex[:10]}", sanitization_result=dumps_or_none(sanitization),
            actor_type=identity.actor_type, actor_id=identity.actor_id, agent_role=identity.agent_role,
            platform_release_sha=self._release, timestamp=now_iso()))

    def query_lessons(
        self,
        identity: Identity,
        *,
        skill: str | None = None,
        failure_class: str | None = None,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Lessons with ``last_fired`` (latest matching incident) for pruning rules that no longer fire."""
        rows = self._store.query_lessons({"skill": skill, "failure_class": failure_class, "scope": scope},
                                         max(1, min(limit, 1000)))
        for r in rows:
            r["last_fired"] = self._store.last_incident_at(r["skill"], r["step"], r["failure_class"])
        return rows

    # ---------------------------------------------------------------- retention
    def purge_expired_content(self) -> dict[str, Any]:
        """Delete evidence payloads older than the retention period. Chained rows (and verify) are unaffected.

        A SYSTEM PURGE marker is appended so auditors can see what was deleted and when.
        """
        count = self._store.purge_expired_content()
        retention = self._store.retention_days()
        if count > 0:
            self.record_evidence(
                system_identity("retention-purge"),
                run_id=f"purge-{now_iso()}",
                classification="FACT",
                content=f"Purged {count} evidence payload(s) older than {retention} day(s)",
                source_type="system_lifecycle",
                source="evidence_ledger:purge_expired_content",
                tool="server",
                metadata={"purge_count": count, "retention_days": retention},
            )
        return {"purged": count, "retention_days": retention}

    # ---------------------------------------------------------------- derived views
    def blocking_items(self, change_set_id: str) -> list[str]:
        """Completion-criteria inputs (§4.5): open blocking QUESTIONs, unexpired ASSUMPTIONs above LOW."""
        out = []
        for e in self._store.query_entries({"change_set_id": change_set_id}, 100000):
            status = self._derived_status(e)
            meta = e.get("metadata") or {}
            if e["classification"] == "QUESTION" and meta.get("blocking") and status == "OPEN":
                out.append(f"open blocking QUESTION {e['entry_id']}: {(e['content'] or '[expired]')[:120]}")
            if e["classification"] == "ASSUMPTION" and meta.get("impact") in ("MEDIUM", "HIGH") and status == "OPEN":
                out.append(f"unexpired {meta['impact']}-impact ASSUMPTION {e['entry_id']}: "
                           f"{(e['content'] or '[expired]')[:120]}")
        return out

    def verify(self) -> list[dict[str, Any]]:
        return self._store.verify()

    def get_entry(self, entry_id: str) -> dict[str, Any]:
        return self._require(entry_id)

    def _failure_classes(self):
        return domain.known_failure_classes(self._repo_root)

    # ---------------------------------------------------------------- hooks (SYSTEM)
    def append_fact(self, hook_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Hook contract (docs/authoring-conventions.md): {run_id, tool, source_type, content, source, change_set_id?}.

        Called in-process by scripts/ledger_cli.py — deliberately not an MCP tool.
        """
        allowed = {"run_id", "tool", "source_type", "content", "source", "change_set_id", "snapshot_id"}
        extra = set(payload) - allowed
        if extra:
            raise ValidationError(f"unexpected fields for append-fact (identity/trust are never supplied): {sorted(extra)}")
        return self.record_evidence(
            system_identity(f"hook:{hook_name}"),
            run_id=payload.get("run_id") or "",
            classification="FACT",
            content=payload.get("content") or "",
            source_type=payload.get("source_type") or "hook_observation",
            source=payload.get("source"),
            change_set_id=payload.get("change_set_id"),
            snapshot_id=payload.get("snapshot_id"),
            tool=payload.get("tool"),
        )

    # ---------------------------------------------------------------- internals
    def _require(self, entry_id: str) -> dict[str, Any]:
        e = self._store.get_entry(entry_id)
        if e is None:
            raise NotFound(f"entry {entry_id} not found")
        return e

    def _derived_status(self, e: dict[str, Any]) -> str | None:
        outcomes = {c["outcome_status"] for c in self._store.children_of(e["entry_id"])}
        if e["classification"] in ("QUESTION", "ASSUMPTION"):
            if "ANSWERED" in outcomes:
                return "ANSWERED"
            return "EXPIRED" if domain.is_expired(e) else "OPEN"
        return "CHALLENGED" if "CHALLENGED" in outcomes else None

    def _append(self, identity: Identity, *, referenced: list[dict[str, Any]], source_type: str,
                model_id: str | None, tool: str | None, **fields: Any) -> dict[str, Any]:
        row = {
            "entry_id": f"ENTRY-{uuid.uuid4().hex[:12]}",
            "run_id": fields["run_id"],
            "change_set_id": fields.get("change_set_id"),
            "actor_type": identity.actor_type,
            "actor_id": identity.actor_id,
            "agent_role": identity.agent_role,
            "model_id": domain.resolve_model(identity, model_id),
            "tool": domain.resolve_tool(identity, tool),
            "classification": fields["classification"],
            "trust_level": domain.derive_trust(source_type, referenced, identity),
            "source_type": source_type,
            "source": fields.get("source"),
            "input_references": dumps_or_none(fields.get("input_references")),
            "output_references": dumps_or_none(fields.get("output_references")),
            "decision_ids": dumps_or_none(fields.get("decision_ids")),
            "lifecycle_state": fields.get("lifecycle_state"),
            "snapshot_id": fields.get("snapshot_id"),
            "parent_entry_id": fields.get("parent_entry_id"),
            "outcome_status": fields.get("outcome_status"),
            "platform_release_sha": self._release,
            "timestamp": now_iso(),
            "signal_source": fields.get("signal_source"),
            "metadata": dumps_or_none(fields.get("metadata")),
        }
        return self._store.append_entry(row, fields["content"])


_INCIDENT_VIEW = ("incident_id", "skill", "step", "failure_class", "signal_type", "signal_source",
                  "verification_strength", "pattern_eligible", "evidence_refs", "note", "note_author_type",
                  "timestamp")


def _find_repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "skills").is_dir():
            return parent
    return None


def open_ledger(db_path: str | Path, platform_release_sha: str = "unversioned",
                retention_days: int = 90) -> EvidenceLedger:
    ledger = EvidenceLedger(db.connect(db_path), platform_release_sha, retention_days)
    ledger.migrate()
    return ledger


class EvidenceLedgerModule:
    """Module-protocol wrapper used by the composition root or a standalone host."""

    name = NAME

    def __init__(self, config: Config) -> None:
        self._conn = db.connect(config.db_path(NAME))
        self._ledger = EvidenceLedger(self._conn, config.platform_release_sha, config.evidence_retention_days)

    def migrate(self, conn: sqlite3.Connection | None = None) -> None:
        self._ledger.migrate()

    def register_tools(self, server: Any, identity: Identity) -> list[str]:
        from .tools import register_tools

        return register_tools(server, self._ledger, identity)

    @property
    def api(self) -> EvidenceLedger:
        return self._ledger

    def close(self) -> None:
        self._conn.close()


def create_module(config: Config) -> EvidenceLedgerModule:
    module = EvidenceLedgerModule(config)
    module.migrate()
    return module
