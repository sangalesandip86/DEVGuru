"""Work Planning — public surface. The ONLY file other code may import from this module.

Plan v3.1 §6 Module 4. No tool lets an agent-authenticated caller set READY, DONE or ACCEPTED:
story status is derived from SYSTEM-ingested plan commits and CI/forge events.

Ports (satisfied by adapters in ``adlc_mcp.app``; swapped for remote clients on extraction):
  * :class:`EvaluatorPort` — DoR/DoD policy evaluation. The in-process adapter will wrap
    ``skills/enforcement/ci-checks/planning-gates``; this module never imports those scripts.
  * :class:`ChangeSetStatusPort` — statuses of linked Change Sets.
"""
from __future__ import annotations

import sqlite3
from collections import deque
from typing import Any, Protocol

from adlc_mcp.kernel import db
from adlc_mcp.kernel.config import Config
from adlc_mcp.kernel.errors import NotFound, ValidationError
from adlc_mcp.kernel.identity import Identity
from adlc_mcp.kernel.util import now_iso

from . import domain
from .store import PlanningStore

NAME = "work_planning"


# --------------------------------------------------------------------------- ports
class EvaluatorPort(Protocol):
    def evaluate(self, gate: str, story: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Return {"passed": bool, "missing": [str, ...]} for gate "readiness" or "done"."""


class NullEvaluator:
    """No policy evaluator connected. Fails safe: readiness/done cannot be confirmed."""

    def evaluate(self, gate: str, story: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"passed": False, "missing": [f"no {gate} policy evaluator connected (planning-gates)"]}


class ChangeSetStatusPort(Protocol):
    def statuses(self, change_set_ids: list[str]) -> dict[str, str | None]: ...


class NullChangeSetStatus:
    """Change Management not connected (e.g. Phase 1 forge-native): statuses are unknown."""

    def statuses(self, change_set_ids: list[str]) -> dict[str, str | None]:
        return {cs: None for cs in change_set_ids}


# --------------------------------------------------------------------------- facade
class WorkPlanning:
    def __init__(self, conn: sqlite3.Connection, evaluator: EvaluatorPort | None = None,
                 change_sets: ChangeSetStatusPort | None = None) -> None:
        self._store = PlanningStore(conn)
        self._evaluator = evaluator or NullEvaluator()
        self._cs = change_sets or NullChangeSetStatus()

    def migrate(self) -> list[str]:
        return self._store.migrate()

    # ------------------------------------------------------------ SYSTEM ingestion
    def ingest_plan_commit(
        self,
        identity: Identity,
        *,
        repository: str,
        commit_sha: str,
        items: list[dict[str, Any]],
        full_snapshot: bool = True,
    ) -> dict[str, Any]:
        """SYSTEM-only: ingest a merged plan commit; recompute AC hashes and derived statuses."""
        identity.require("SYSTEM", action="ingest_plan_commit")
        if not repository or not commit_sha:
            raise ValidationError("repository and commit_sha are required")
        prepared = []
        for it in items:
            item_id = it.get("id")
            kind = domain.kind_of(item_id)
            data = it.get("data") or {}
            domain.validate_plan_item(item_id, data)
            prepared.append((item_id, kind, it.get("path"), data))
        ts = now_iso()
        edges: set[tuple[str, str, str]] = set()
        for item_id, kind, path, data in prepared:
            self._store.upsert_item({
                "id": item_id, "kind": kind, "repository": repository, "commit_sha": commit_sha, "path": path,
                "data": data, "ac_hash": domain.ac_hash(data) if kind == "story" else None, "removed": 0,
                "updated_at": ts,
            })
            edges |= domain.edges_for(item_id, kind, data)
        self._store.replace_edges({p[0] for p in prepared}, edges)
        if full_snapshot:
            self._store.mark_removed_except(repository, {p[0] for p in prepared})
        self._store.append_commit({
            "repository": repository, "commit_sha": commit_sha, "item_count": len(prepared),
            "full_snapshot": int(full_snapshot), "ingested_by": identity.actor_id, "timestamp": ts,
        })
        changes = self._recompute_all(f"plan commit {repository}@{commit_sha}")
        return {"ingested": len(prepared), "status_changes": changes}

    def ingest_work_event(
        self, identity: Identity, *, story_id: str, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """SYSTEM-only: record an observed gate result, PR opening, PO acceptance, cancellation or split."""
        identity.require("SYSTEM", action="ingest_work_event")
        self._require_story(story_id)
        domain.validate_work_event(event_type, payload)
        self._store.append_event({"story_id": story_id, "event_type": event_type, "payload": payload,
                                  "ingested_by": identity.actor_id, "timestamp": now_iso()})
        change = self._recompute(story_id, f"{event_type} observed")
        return {"story_id": story_id, "status": self._store.cached_status(story_id), "change": change}

    # ------------------------------------------------------------ agent-callable
    def link_change_set(
        self, identity: Identity, *, story_id: str, change_set_id: str, implements_declaration: str
    ) -> dict[str, Any]:
        """Link a Story to a Change Set, validated against the PR body's ``Implements:`` line."""
        self._require_story(story_id)
        if not change_set_id:
            raise ValidationError("change_set_id is required")
        declared = domain.implemented_ids(implements_declaration)
        if story_id not in declared:
            raise ValidationError(f"the PR's Implements: declaration does not list {story_id} (found {sorted(declared)})")
        self._store.add_link({"story_id": story_id, "change_set_id": change_set_id,
                              "declared_in": implements_declaration.strip()[:500],
                              "linked_by": f"{identity.actor_type}:{identity.actor_id}", "timestamp": now_iso()})
        self._recompute(story_id, f"linked to {change_set_id}")
        return {"story_id": story_id, "change_set_id": change_set_id,
                "links": [l["change_set_id"] for l in self._store.links_for_story(story_id)]}

    def get_work_item(self, identity: Identity, item_id: str) -> dict[str, Any]:
        item = self._store.get_item(item_id)
        if item is None:
            raise NotFound(f"work item {item_id} not found")
        out = dict(item, removed=bool(item["removed"]))
        if item["kind"] == "story":
            derived = self._derive(item)
            out.update(status=derived["status"], status_flags=derived["flags"],
                       links=[l["change_set_id"] for l in self._store.links_for_story(item_id)])
        out["as_of_commit"] = self._store.last_commit()
        return out

    def query_work_graph(
        self, identity: Identity, *, root_id: str, relations: list[str] | None = None, depth: int = 3
    ) -> dict[str, Any]:
        if self._store.get_item(root_id) is None:
            raise NotFound(f"work item {root_id} not found")
        allowed = set(relations or ("scope", "time", "depends_on", "implements"))
        nodes, edges, seen = {}, [], {root_id}
        queue = deque([(root_id, 0)])
        while queue:
            node, d = queue.popleft()
            item = self._store.get_item(node)
            nodes[node] = {"id": node, "kind": item["kind"] if item else "change_set",
                           "title": (item["data"].get("title") if item else None)}
            if d >= max(0, min(depth, 10)):
                continue
            neighbours = []
            for e in self._store.edges_touching(node):
                if e["relation"] in allowed:
                    edges.append(e)
                    neighbours.append(e["dst"] if e["src"] == node else e["src"])
            if "implements" in allowed:
                links = self._store.links_for_story(node) if item else self._store.links_for_change_set(node)
                for l in links:
                    edges.append({"src": l["story_id"], "dst": l["change_set_id"], "relation": "implements"})
                    neighbours.append(l["change_set_id"] if item else l["story_id"])
            for n in neighbours:
                if n not in seen:
                    seen.add(n)
                    queue.append((n, d + 1))
        unique = {(e["src"], e["dst"], e["relation"]): e for e in edges}
        return {"root": root_id, "nodes": list(nodes.values()), "edges": list(unique.values())}

    def evaluate_readiness(self, identity: Identity, *, story_id: str) -> dict[str, Any]:
        """Read-only dry run of the DoR. Never changes status."""
        return self._evaluate("readiness", story_id)

    def evaluate_done(self, identity: Identity, *, story_id: str) -> dict[str, Any]:
        """Read-only dry run of the DoD. Never changes status."""
        return self._evaluate("done", story_id)

    def verify(self) -> list[dict[str, Any]]:
        return self._store.verify()

    # ------------------------------------------------------------ internals
    def _evaluate(self, gate: str, story_id: str) -> dict[str, Any]:
        story = self._require_story(story_id)
        links = [l["change_set_id"] for l in self._store.links_for_story(story_id)]
        statuses = self._cs.statuses(links)
        structural = (domain.structural_readiness(story_id, story["data"]) if gate == "readiness"
                      else domain.structural_done(statuses))
        context = {"ac_hash": story["ac_hash"], "links": statuses, "events": self._store.events_for(story_id),
                   "structural_missing": structural}
        policy = self._evaluator.evaluate(gate, story, context)
        missing = [*structural, *policy.get("missing", [])]
        return {"story_id": story_id, "gate": gate, "dry_run": True,
                "passed": bool(policy.get("passed")) and not structural and not missing,
                "missing": missing, "ac_hash": story["ac_hash"], "current_status": self._derive(story)["status"]}

    def _derive(self, story: dict[str, Any]) -> dict[str, Any]:
        links = [l["change_set_id"] for l in self._store.links_for_story(story["id"])]
        statuses = self._cs.statuses(links) if links else {}
        return domain.derive_status(story["data"], story["ac_hash"], self._store.events_for(story["id"]), statuses)

    def _recompute(self, story_id: str, reason: str) -> dict[str, Any] | None:
        story = self._store.get_item(story_id)
        derived = self._derive(story)
        previous = self._store.cached_status(story_id)
        if derived["status"] != previous:
            why = reason + (f" ({'; '.join(derived['flags'])})" if derived["flags"] else "")
            self._store.set_status(story_id, previous, derived["status"], why)
            return {"story_id": story_id, "from": previous, "to": derived["status"], "flags": derived["flags"]}
        return None

    def _recompute_all(self, reason: str) -> list[dict[str, Any]]:
        return [c for s in self._store.stories() if (c := self._recompute(s["id"], reason))]

    def _require_story(self, story_id: str) -> dict[str, Any]:
        item = self._store.get_item(story_id)
        if item is None or item["kind"] != "story" or item["removed"]:
            raise NotFound(f"story {story_id} not found")
        return item


# --------------------------------------------------------------------------- module wrapper
class WorkPlanningModule:
    name = NAME

    def __init__(self, config: Config, evaluator: EvaluatorPort | None = None,
                 change_sets: ChangeSetStatusPort | None = None) -> None:
        self._conn = db.connect(config.db_path(NAME))
        self._api = WorkPlanning(self._conn, evaluator, change_sets)

    def migrate(self, conn: sqlite3.Connection | None = None) -> None:
        self._api.migrate()

    def register_tools(self, server: Any, identity: Identity) -> list[str]:
        from .tools import register_tools

        return register_tools(server, self._api, identity)

    @property
    def api(self) -> WorkPlanning:
        return self._api

    def close(self) -> None:
        self._conn.close()


def create_module(config: Config, evaluator: EvaluatorPort | None = None,
                  change_sets: ChangeSetStatusPort | None = None) -> WorkPlanningModule:
    module = WorkPlanningModule(config, evaluator, change_sets)
    module.migrate()
    return module
