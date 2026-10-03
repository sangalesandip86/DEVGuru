"""Change Management — public surface. The ONLY file other code may import from this module.

Plan §6 Server 2, §4.5, §5.10. Authorization lives here (not in the host) so it survives
extraction: no caller sets PLAN_APPROVED / INTEGRATED / RELEASED / ROLLED_BACK through
update_status; those come only from SYSTEM-ingested forge events.

Ports (dependencies on other modules, satisfied by adapters in ``adlc_mcp.app``):
  * :class:`EvidencePort` — completion-criteria inputs from the Evidence Ledger and a sink
    for SYSTEM facts about state transitions.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Protocol

from adlc_mcp.kernel import db
from adlc_mcp.kernel.config import Config
from adlc_mcp.kernel.errors import NotFound, PermissionDenied, ValidationError
from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.util import canonical_json as domain_json, now_iso
from adlc_mcp.kernel.vocab import AGENT_ROLES, RISK_TIERS, max_tier, tier_index

from . import domain
from .store import ChangeStore

NAME = "change_management"
_SHA = re.compile(r"^[0-9a-f]{7,40}$")


# --------------------------------------------------------------------------- ports
class EvidencePort(Protocol):
    def blocking_items(self, change_set_id: str) -> list[str]:
        """Open blocking QUESTIONs and unexpired ASSUMPTIONs with impact > LOW."""

    def record_system_fact(self, change_set_id: str, content: str, source: str) -> None:
        """Record a SYSTEM FACT (e.g. an observed state transition)."""


class NullEvidencePort:
    """Used when the Evidence Ledger is not connected. Fails safe: integration cannot be confirmed."""

    def blocking_items(self, change_set_id: str) -> list[str]:
        return ["evidence ledger not connected: cannot confirm absence of blocking QUESTIONs/ASSUMPTIONs"]

    def record_system_fact(self, change_set_id: str, content: str, source: str) -> None:
        return None


class ChangeSetStatusReader(Protocol):
    """Narrow read-only view other modules may depend on (work_planning uses it via a port)."""

    def statuses(self, change_set_ids: list[str]) -> dict[str, str | None]: ...


# --------------------------------------------------------------------------- facade
class ChangeManagement:
    def __init__(self, conn: sqlite3.Connection, evidence: EvidencePort | None = None,
                 repo_root: Path | None = None) -> None:
        self._store = ChangeStore(conn)
        self._evidence = evidence or NullEvidencePort()
        self._repo_root = repo_root if repo_root is not None else _find_repo_root()

    def migrate(self) -> list[str]:
        return self._store.migrate()

    # ------------------------------------------------------------ create / read
    def create_change_set(
        self,
        identity: Identity,
        *,
        title: str,
        requirements: list[str],
        repositories: list[str],
        contracts: list[str] | None = None,
        environments: list[str] | None = None,
        system: str | None = None,
        initiative: str | None = None,
        parent_id: str | None = None,
        depends_on: list[str] | None = None,
        release_environment: str = "production",
        story_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        if not title or not requirements or not repositories:
            raise ValidationError("title, requirements and repositories are required")
        for ref in [parent_id, *(depends_on or [])]:
            if ref and self._store.get_change_set(ref) is None:
                raise NotFound(f"change set {ref} not found")
        cs_id = f"CS-{uuid.uuid4().hex[:8]}"
        ts = now_iso()
        self._store.insert_change_set({
            "id": cs_id, "title": title, "system": system, "initiative": initiative,
            "requirements": list(requirements), "repositories": list(repositories),
            "contracts": list(contracts or []), "environments": list(environments or []),
            "release_environment": release_environment, "status": "DRAFT", "risk_tier": None,
            "parent_id": parent_id, "depends_on": list(depends_on or []), "story_refs": list(story_refs or []),
            "created_by": f"{identity.actor_type}:{identity.actor_id}", "created_at": ts, "updated_at": ts,
        })
        self._store.append_history({
            "change_set_id": cs_id, "from_status": None, "to_status": "DRAFT", "actor_type": identity.actor_type,
            "actor_id": identity.actor_id, "via": "create", "reason": None, "timestamp": ts,
        })
        return self.get_change_set(identity, cs_id)

    def get_change_set(self, identity: Identity, change_set_id: str) -> dict[str, Any]:
        cs = self._require(change_set_id)
        cs["effective_risk_tier"] = domain.effective_tier(cs["risk_tier"])
        cs["tasks"] = self._store.tasks(change_set_id)
        cs["latest_snapshot"] = self._store.latest_snapshot(change_set_id)
        cs["dependencies"] = self._store.dependencies(change_set_id)
        cs["risk_history"] = self._store.risk_history(change_set_id)
        cs["handoffs"] = self._store.handoffs(change_set_id)
        cs["forge_events"] = self._store.forge_events(change_set_id)
        cs["status_history"] = self._store.history(change_set_id)
        return cs

    def statuses(self, change_set_ids: list[str]) -> dict[str, str | None]:
        out = {}
        for cs_id in change_set_ids:
            cs = self._store.get_change_set(cs_id)
            out[cs_id] = cs["status"] if cs else None
        return out

    # ------------------------------------------------------------ status
    def update_status(
        self, identity: Identity, *, change_set_id: str, status: str, reason: str, block_kind: str | None = None
    ) -> dict[str, Any]:
        cs = self._require(change_set_id)
        domain.check_manual_transition(identity, cs["status"], status, cs["blocked_from"], cs["block_kind"])
        if not reason:
            raise ValidationError("reason is required for every status change")
        if status == "BLOCKED":
            if block_kind not in domain.BLOCK_KINDS:
                raise ValidationError(f"block_kind must be one of {domain.BLOCK_KINDS}")
        self._transition(cs, status, identity, "update_status", reason, block_kind)
        return self.get_change_set(identity, change_set_id)

    def ingest_forge_event(
        self, identity: Identity, *, change_set_id: str, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """SYSTEM-only. The forge (merge, deploy, CODEOWNERS review) is the source of truth (§5.10)."""
        identity.require("SYSTEM", action="ingest_forge_event")
        domain.validate_forge_event(event_type, payload)
        cs = self._require(change_set_id)
        prior = self._store.forge_events(change_set_id)
        event = {"event_type": event_type, "payload": payload}
        target, note = self._decide(cs, [*prior, event], event)
        recorded = self._store.append_forge_event({
            "id": f"FE-{uuid.uuid4().hex[:10]}", "change_set_id": change_set_id, "event_type": event_type,
            "payload": domain_json(payload), "ingested_by": identity.actor_id,
            "resulting_status": target[0] if target else cs["status"], "timestamp": now_iso(),
        })
        if target:
            self._transition(cs, target[0], identity, f"forge_event:{recorded['id']}", note, target[1])
        return {"event_id": recorded["id"], "status": self._require(change_set_id)["status"], "note": note}

    def _decide(self, cs: dict[str, Any], events: list[dict[str, Any]], event: dict[str, Any]):
        status, et = cs["status"], event["event_type"]
        if et in ("plan_check_passed", "codeowners_review"):
            if status != "PLANNED":
                return None, f"recorded; plan approval evaluated only in PLANNED (status={status})"
            accepted = {h["from_role"] for h in self._store.handoffs(cs["id"]) if h["verdict"] == "ACCEPT"}
            missing = domain.plan_approval_missing(cs["risk_tier"], events, accepted)
            if missing:
                return None, "plan approval pending: " + "; ".join(missing)
            return ("PLAN_APPROVED", None), f"approval matrix satisfied for {domain.effective_tier(cs['risk_tier'])}"
        if et == "pr_merged":
            if status == "INTEGRATED":
                return None, "recorded; already INTEGRATED"
            if status != "VERIFYING":
                return ("BLOCKED", "ESCALATION"), f"merge observed while {status}: verification was bypassed"
            merged = {e["payload"]["repository"] for e in events if e["event_type"] == "pr_merged"}
            pending = sorted(set(cs["repositories"]) - merged)
            if pending:
                return None, f"awaiting merges in {pending}"
            blockers = self._integration_blockers(cs)
            if blockers:
                return ("BLOCKED", "ESCALATION"), "merged but completion criteria unmet: " + "; ".join(blockers)
            return ("INTEGRATED", None), "all repositories merged and completion criteria met"
        if et in ("deployment", "environment_approval"):
            if status != "INTEGRATED":
                return None, f"recorded; release evaluated only in INTEGRATED (status={status})"
            missing = domain.release_missing(cs["risk_tier"], events, cs["release_environment"])
            if missing:
                return None, "release pending: " + "; ".join(missing)
            return ("RELEASED", None), "deployment observed and release approvals satisfied"
        if et == "rollback":
            if status != "RELEASED":
                return None, f"recorded; ROLLED_BACK is reachable only from RELEASED (status={status})"
            return ("ROLLED_BACK", None), "rollback observed"
        return None, "recorded"

    def _integration_blockers(self, cs: dict[str, Any]) -> list[str]:
        """Completion criteria (§4.5) this module can check; the rest arrive through the EvidencePort."""
        out = [f"UNRESOLVED dependency {d['source']} -> {d['target']}"
               for d in self._latest_dependencies(cs["id"]) if d["status"] == "UNRESOLVED"]
        out += [f"task {t['id']} not DONE ({t['status']})" for t in self._store.tasks(cs["id"]) if t["status"] != "DONE"]
        out += self._evidence.blocking_items(cs["id"])
        return out

    def _transition(self, cs: dict[str, Any], target: str, identity: Identity, via: str, reason: str | None,
                    block_kind: str | None) -> None:
        if target == "BLOCKED":
            self._store.set_status(cs["id"], "BLOCKED", cs["status"], block_kind)
        else:
            self._store.set_status(cs["id"], target, None, None)
        self._store.append_history({
            "change_set_id": cs["id"], "from_status": cs["status"], "to_status": target,
            "actor_type": identity.actor_type, "actor_id": identity.actor_id, "via": via, "reason": reason,
            "timestamp": now_iso(),
        })
        self._evidence.record_system_fact(
            cs["id"], f"Change Set {cs['id']} {cs['status']} -> {target} ({reason or 'no reason'})",
            f"change_management:{via}",
        )

    # ------------------------------------------------------------ snapshots
    def create_snapshot(
        self,
        identity: Identity,
        *,
        change_set_id: str,
        repositories: dict[str, str],
        contracts: dict[str, str] | None = None,
        environments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cs = self._require(change_set_id)
        missing = sorted(set(cs["repositories"]) - set(repositories))
        if missing:
            raise ValidationError(f"snapshot must pin every repository in the Change Set; missing {missing}")
        bad = [r for r, sha in repositories.items() if not _SHA.match(sha or "")]
        if bad:
            raise ValidationError(f"commit SHAs required (\"latest\" is never a reproducibility mechanism): {bad}")
        snap = {
            "id": f"SNAP-{uuid.uuid4().hex[:8]}", "change_set_id": change_set_id, "repositories": repositories,
            "contracts": contracts or {}, "environments": environments or {},
            "created_by": f"{identity.actor_type}:{identity.actor_id}", "created_at": now_iso(),
        }
        self._store.insert_snapshot(snap)
        return snap

    def validate_snapshot_currency(
        self,
        identity: Identity,
        *,
        snapshot_id: str,
        current_heads: dict[str, str],
        changed_paths: dict[str, list[str]] | None = None,
        task_paths: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        snap = self._store.get_snapshot(snapshot_id)
        if snap is None:
            raise NotFound(f"snapshot {snapshot_id} not found")
        result = domain.staleness(snap["repositories"], current_heads, changed_paths or {}, task_paths or {})
        result["snapshot_id"] = snapshot_id
        return result

    # ------------------------------------------------------------ dependencies
    def record_dependency(
        self,
        identity: Identity,
        *,
        change_set_id: str,
        source: str,
        target: str,
        type: str,
        confidence: float,
        evidence_level: str,
        resolved: bool = False,
    ) -> dict[str, Any]:
        self._require(change_set_id)
        if evidence_level not in ("DECLARED", "STATIC", "OBSERVED"):
            raise ValidationError("evidence_level must be DECLARED, STATIC or OBSERVED")
        if not 0.0 <= float(confidence) <= 1.0:
            raise ValidationError("confidence must be within [0, 1]")
        row = {
            "id": f"DEP-{uuid.uuid4().hex[:8]}", "change_set_id": change_set_id, "source": source, "target": target,
            "type": type, "confidence": float(confidence), "evidence_level": evidence_level,
            # Not proven resolved → UNRESOLVED (§5.3), never "no dependency".
            "status": "RESOLVED" if resolved else "UNRESOLVED",
            "recorded_by": f"{identity.actor_type}:{identity.actor_id}", "timestamp": now_iso(),
        }
        self._store.insert_dependency(row)
        return row

    def _latest_dependencies(self, cs_id: str) -> list[dict[str, Any]]:
        latest: dict[tuple, dict[str, Any]] = {}
        for d in self._store.dependencies(cs_id):
            latest[(d["source"], d["target"], d["type"])] = d
        return list(latest.values())

    # ------------------------------------------------------------ risk tiering
    def compute_risk_tier(
        self,
        identity: Identity,
        *,
        change_set_id: str,
        paths: list[str],
        reason_codes: list[str] | None = None,
        assessed_tiers: list[str] | None = None,
        tier_floor: str | None = None,
        diff_lines: int | None = None,
    ) -> dict[str, Any]:
        cs = self._require(change_set_id)
        if tier_floor is not None and tier_floor not in RISK_TIERS:
            raise ValidationError(f"tier_floor must be one of {RISK_TIERS}")
        rules, default, source = domain.load_path_tiers(self._repo_root)
        result = domain.compute_tier(list(paths or []), list(reason_codes or []), list(assessed_tiers or []),
                                     rules, default)
        final = result["final_tier"]
        if tier_floor:                                    # story-type floor raises, never lowers (v3.1)
            final = max_tier([final, tier_floor])
        previous = cs["risk_tier"]
        if previous and tier_index(previous) > tier_index(final):
            final = previous                              # recomputation never removes scrutiny
        result.update(final_tier=final, previous_tier=previous, tier_source=source)
        cap = domain.diff_size_cap()
        result["decompose_required"] = diff_lines is not None and diff_lines > cap
        result["diff_size_cap"] = cap
        self._store.append_risk({
            "change_set_id": change_set_id, "kind": "COMPUTED", "base_tier": result["base_tier"], "final_tier": final,
            "previous_tier": previous, "direction": _direction(previous, final),
            "reason_codes": domain_json(result["reason_codes"]),
            "detail": domain_json({"matches": result["matches"], "uncomputable": result["uncomputable"],
                                   "diff_lines": diff_lines, "tier_floor": tier_floor}),
            "actor_type": identity.actor_type, "actor_id": identity.actor_id, "timestamp": now_iso(),
        })
        self._store.set_risk_tier(change_set_id, final)
        return result

    def override_risk_tier(self, identity: Identity, *, change_set_id: str, tier: str, reason: str) -> dict[str, Any]:
        """HUMAN-only. Every downgrade is logged; a rising downgrade rate signals miscalibration (§4.5)."""
        identity.require("HUMAN", action="override_risk_tier")
        cs = self._require(change_set_id)
        if tier not in RISK_TIERS or not reason:
            raise ValidationError("a valid tier and a reason are required")
        row = self._store.append_risk({
            "change_set_id": change_set_id, "kind": "HUMAN_OVERRIDE", "base_tier": None, "final_tier": tier,
            "previous_tier": cs["risk_tier"], "direction": _direction(cs["risk_tier"], tier), "reason_codes": None,
            "detail": domain_json({"reason": reason}), "actor_type": identity.actor_type,
            "actor_id": identity.actor_id, "timestamp": now_iso(),
        })
        self._store.set_risk_tier(change_set_id, tier)
        return row

    def override_stats(self) -> dict[str, Any]:
        rows = self._store.all_overrides()
        downgrades = sum(1 for r in rows if r["direction"] == "DOWNGRADE")
        return {"overrides": len(rows), "downgrades": downgrades,
                "downgrade_rate": (downgrades / len(rows)) if rows else 0.0}

    # ------------------------------------------------------------ handoffs
    def record_handoff(
        self,
        identity: Identity,
        *,
        change_set_id: str,
        to_role: str,
        payload: dict[str, Any],
        verdict: str | None = None,
        domain_name: str | None = None,
    ) -> dict[str, Any]:
        cs = self._require(change_set_id)
        from_role = identity.agent_role if identity.is_agent else f"{identity.actor_type.lower()}:{identity.actor_id}"
        if to_role not in AGENT_ROLES and not to_role.startswith("human:"):
            raise ValidationError("to_role must be an agent role or a human:<role> (Degraded Mode stand-in)")
        if verdict is not None and verdict not in domain.VERDICTS:
            raise ValidationError(f"verdict must be one of {domain.VERDICTS}")
        domain.validate_handoff_payload(payload)
        row = self._store.append_handoff({
            "id": f"HO-{uuid.uuid4().hex[:10]}", "change_set_id": change_set_id, "from_role": from_role,
            "to_role": to_role, "verdict": verdict, "domain": domain_name, "payload": domain_json(payload),
            "actor_type": identity.actor_type, "actor_id": identity.actor_id, "timestamp": now_iso(),
        })
        pair = {from_role, to_role}
        rejections = sum(1 for h in self._store.handoffs(change_set_id)
                         if h["verdict"] == "REJECT" and {h["from_role"], h["to_role"]} == pair)
        escalate = None
        if verdict == "REJECT" and from_role == "security-reviewer":
            escalate = "security REJECT blocks within its domain; only a human lifts it"
        elif rejections >= domain.MAX_HANDOFF_CYCLES:
            escalate = f"{rejections} rejections between {sorted(pair)}: max handoff cycles reached"
        if escalate and cs["status"] not in ("BLOCKED", *domain.TERMINAL, "RELEASED"):
            self._transition(cs, "BLOCKED", identity, f"handoff:{row['id']}", escalate, "ESCALATION")
        row["escalated"] = escalate
        return row

    # ------------------------------------------------------------ tasks
    def record_task(
        self,
        identity: Identity,
        *,
        change_set_id: str,
        task_id: str,
        owner_role: str,
        depends_on: list[str] | None = None,
        worktree: str | None = None,
        status: str = "PENDING",
        ac_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        cs = self._require(change_set_id)
        if owner_role not in AGENT_ROLES:
            raise ValidationError(f"owner_role must be one of {AGENT_ROLES}")
        if status not in domain.TASK_STATUSES:
            raise ValidationError(f"status must be one of {domain.TASK_STATUSES}")
        existing = self._store.get_task(change_set_id, task_id)
        if existing and existing["status"] == "BLOCKED" and status != "BLOCKED" and existing["blocked_reason"] \
                and existing["blocked_reason"].startswith("ESCALATE") and not identity.is_human:
            raise PermissionDenied("task was escalated; only a human can unblock it")
        if status == "IN_PROGRESS":
            if cs["status"] != "EXECUTING":
                raise ValidationError("tasks start only while the Change Set is EXECUTING (after PLAN_APPROVED)")
            if not worktree:
                raise ValidationError("each running task needs its own isolated git worktree")
            clash = [t for t in self._store.tasks_using_worktree(worktree)
                     if (t["change_set_id"], t["id"]) != (change_set_id, task_id)]
            if clash:
                raise ValidationError(f"worktree {worktree} is in use by {clash[0]['change_set_id']}/{clash[0]['id']}")
            undone = [d for d in (depends_on or (existing or {}).get("depends_on") or [])
                      if (self._store.get_task(change_set_id, d) or {}).get("status") != "DONE"]
            if undone:
                raise ValidationError(f"dependencies not DONE: {undone}")
        self._store.upsert_task({
            "change_set_id": change_set_id, "id": task_id, "owner_role": owner_role,
            "depends_on": list(depends_on if depends_on is not None else (existing or {}).get("depends_on") or []),
            "worktree": worktree if worktree is not None else (existing or {}).get("worktree"),
            "attempts": (existing or {}).get("attempts", 0), "status": status,
            "blocked_reason": (existing or {}).get("blocked_reason") if status == "BLOCKED" else None,
            "checkpoint": (existing or {}).get("checkpoint"),
            "ac_refs": list(ac_refs if ac_refs is not None else (existing or {}).get("ac_refs") or []),
            "updated_at": now_iso(),
        })
        return self._store.get_task(change_set_id, task_id)

    def checkpoint_task(
        self, identity: Identity, *, change_set_id: str, task_id: str, commit_sha: str, ledger_cursor: str,
        snapshot_id: str,
    ) -> dict[str, Any]:
        task = self._require_task(change_set_id, task_id)
        if not _SHA.match(commit_sha or ""):
            raise ValidationError("commit_sha must be a commit SHA")
        if self._store.get_snapshot(snapshot_id) is None:
            raise NotFound(f"snapshot {snapshot_id} not found")
        task["checkpoint"] = {"commit_sha": commit_sha, "ledger_cursor": ledger_cursor, "snapshot_id": snapshot_id}
        task["updated_at"] = now_iso()
        self._store.upsert_task(task)
        return self._store.get_task(change_set_id, task_id)

    def record_task_failure(
        self, identity: Identity, *, change_set_id: str, task_id: str, failure_class: str, detail: str = ""
    ) -> dict[str, Any]:
        """Apply the per-failure-class retry policy (§4.1). Only RETRY classes draw on the 3-attempt cap."""
        if failure_class not in domain.FAILURE_POLICY:
            raise ValidationError(f"failure_class must be one of {sorted(domain.FAILURE_POLICY)}")
        task = self._require_task(change_set_id, task_id)
        policy, counts = domain.FAILURE_POLICY[failure_class]
        if counts:
            task["attempts"] += 1
        action = policy
        if policy == "RETRY" and task["attempts"] >= domain.ITERATION_CAP:
            action, task["status"] = "STOP", "BLOCKED"
            task["blocked_reason"] = f"STOP: iteration cap {domain.ITERATION_CAP} reached ({failure_class})"
        elif policy == "STOP":
            task["status"], task["blocked_reason"] = "BLOCKED", f"STOP: persistent {failure_class}"
        elif policy == "ESCALATE":
            task["status"], task["blocked_reason"] = "BLOCKED", f"ESCALATE: {failure_class} — human required"
        task["updated_at"] = now_iso()
        self._store.upsert_task(task)
        return {"task": self._store.get_task(change_set_id, task_id), "policy": policy, "action": action,
                "resume_from": task.get("checkpoint") if policy == "RESUME" else None, "detail": detail}

    # ------------------------------------------------------------ misc
    def verify(self) -> list[dict[str, Any]]:
        return self._store.verify()

    def _require(self, cs_id: str) -> dict[str, Any]:
        cs = self._store.get_change_set(cs_id)
        if cs is None:
            raise NotFound(f"change set {cs_id} not found")
        return cs

    def _require_task(self, cs_id: str, task_id: str) -> dict[str, Any]:
        task = self._store.get_task(cs_id, task_id)
        if task is None:
            raise NotFound(f"task {cs_id}/{task_id} not found")
        return task


def _direction(previous: str | None, new: str) -> str:
    if previous is None or previous == new:
        return "NONE"
    return "UPGRADE" if tier_index(new) > tier_index(previous) else "DOWNGRADE"


def _find_repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "skills").is_dir():
            return parent
    return None


# --------------------------------------------------------------------------- module wrapper
class ChangeManagementModule:
    name = NAME

    def __init__(self, config: Config, evidence: EvidencePort | None = None) -> None:
        self._conn = db.connect(config.db_path(NAME))
        self._api = ChangeManagement(self._conn, evidence)

    def migrate(self, conn: sqlite3.Connection | None = None) -> None:
        self._api.migrate()

    def register_tools(self, server: Any, identity: Identity) -> list[str]:
        from .tools import register_tools

        return register_tools(server, self._api, identity)

    @property
    def api(self) -> ChangeManagement:
        return self._api

    def close(self) -> None:
        self._conn.close()


def create_module(config: Config, evidence: EvidencePort | None = None) -> ChangeManagementModule:
    module = ChangeManagementModule(config, evidence)
    module.migrate()
    return module
