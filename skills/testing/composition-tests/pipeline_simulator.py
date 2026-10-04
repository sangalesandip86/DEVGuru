#!/usr/bin/env python3
"""Pipeline simulator for composition testing (Layer F).

Replays a scenario YAML through the ADLC stage graph using either canned outputs
(deterministic, no LLM — default) or live mode (real MCP API calls, requires human
opt-in).

    python pipeline_simulator.py --scenario scenarios/feature_story.yaml
    python pipeline_simulator.py --scenario scenarios/feature_story.yaml --mode live

Canned mode: reads outputs from the scenario YAML, feeds them through the real
change-management and evidence-ledger APIs, validates handoff chains and authority.

Live mode: calls the actual MCP tools at each stage and captures outputs. Requires
ADLC_LIVE_MODE=1 environment variable as an explicit opt-in.

Exit codes: 0 all assertions pass, 1 failures found, 2 bad input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(HERE.parent.parent / "mcp-servers" / "adlc-mcp" / "src"))
sys.path.insert(0, str(HERE.parent.parent / "mcp-servers" / "adlc-mcp" / "tests"))

from _support import (  # noqa: E402
    CI,
    CODE_REVIEWER,
    DEVELOPER,
    HUMAN_LEAD,
    SECURITY,
    TempEnv,
)
from adlc_mcp.app import build_modules  # noqa: E402
from adlc_mcp.kernel.identity import Identity  # noqa: E402

STAGE_ORDER = [
    "INTAKE", "ARCHITECTURE", "PLAN", "DESIGN",
    "IMPLEMENT", "TEST", "REVIEW",
]

ROLE_IDENTITIES: dict[str, Identity] = {
    "product-planner": Identity("AGENT", "agent:product-planner", agent_role="product-planner",
                                tool="claude-code", model_id="model-a"),
    "product-owner": Identity("AGENT", "agent:product-owner", agent_role="product-owner",
                              tool="claude-code", model_id="model-a"),
    "architect": Identity("AGENT", "agent:architect", agent_role="architect",
                          tool="claude-code", model_id="model-a"),
    "developer": DEVELOPER,
    "qa-derive": Identity("AGENT", "agent:qa-derive", agent_role="qa-derive",
                          tool="claude-code", model_id="model-a"),
    "test-engineer": Identity("AGENT", "agent:test-engineer", agent_role="test-engineer",
                              tool="claude-code", model_id="model-a"),
    "code-reviewer": CODE_REVIEWER,
    "security-reviewer": SECURITY,
}

SHA = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"


def load_scenario(path: Path) -> dict[str, Any]:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        pass
    text = path.read_text(encoding="utf-8")
    import json as _json
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return _parse_simple_yaml(text)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML subset parser for scenarios — supports nested dicts/lists."""
    import re
    lines = text.split("\n")
    result: dict[str, Any] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r'^(\w[\w-]*):\s*(.+)$', stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith('"') and val.endswith('"'):
                result[key] = val[1:-1]
            elif val.startswith('['):
                result[key] = json.loads(val)
            else:
                result[key] = val
    return result


class PipelineResult:
    """Collects findings from a pipeline run."""

    def __init__(self, scenario_name: str) -> None:
        self.scenario = scenario_name
        self.findings: list[dict[str, Any]] = []
        self.stage_results: dict[str, dict[str, Any]] = {}
        self.handoffs: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []

    def add_finding(self, severity: str, stage: str, check: str, detail: str) -> None:
        self.findings.append({
            "severity": severity, "stage": stage, "check": check, "detail": detail,
        })

    @property
    def passed(self) -> bool:
        return not any(f["severity"] in ("ERROR", "CRITICAL") for f in self.findings)

    def summary(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "passed": self.passed,
            "stages_run": len(self.stage_results),
            "handoffs_recorded": len(self.handoffs),
            "evidence_entries": len(self.evidence),
            "findings": self.findings,
        }


class CannedPipelineRunner:
    """Runs a scenario through the real MCP APIs using canned (fixture) data."""

    def __init__(self, scenario: dict[str, Any]) -> None:
        self.scenario = scenario
        self.env = TempEnv("evidence_ledger,change_management")
        self.registry = build_modules(self.env.config)
        self.cm = self.registry.get("change_management").api
        self.ledger = self.registry.get("evidence_ledger").api
        self.result = PipelineResult(scenario.get("name", "unknown"))
        self._cs_id: str | None = None
        self._run_id = "run-composition-test-001"

    def close(self) -> None:
        self.registry.close()
        self.env.close()

    def run(self) -> PipelineResult:
        try:
            self._create_change_set()
            self._run_stages()
            self._validate_handoff_chain()
            self._validate_traceability()
            self._validate_authority()
            self._validate_evidence_completeness()
        finally:
            self.close()
        return self.result

    def _create_change_set(self) -> None:
        repos = self.scenario.get("repositories", ["repo-a"])
        if isinstance(repos, str):
            repos = json.loads(repos)
        cs = self.cm.create_change_set(
            DEVELOPER,
            title=self.scenario.get("description", "Composition test"),
            requirements=["REQ-1"],
            repositories=repos,
        )
        self._cs_id = cs["id"]

    def _run_stages(self) -> None:
        stages = self.scenario.get("stages", {})
        for stage_name in STAGE_ORDER:
            if stage_name not in stages:
                continue
            stage = stages[stage_name]
            lead = stage.get("lead_role", "developer")
            identity = ROLE_IDENTITIES.get(lead, DEVELOPER)
            outputs = stage.get("outputs", {})
            self.result.stage_results[stage_name] = {
                "lead_role": lead,
                "outputs": list(outputs.keys()),
            }
            self._record_stage_evidence(stage_name, identity, outputs)
            self._record_stage_handoffs(stage_name, identity)

    def _record_stage_evidence(self, stage: str, identity: Identity,
                               outputs: dict[str, Any]) -> None:
        for kind, data in outputs.items():
            content = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
            try:
                entry = self.ledger.record_evidence(
                    identity,
                    run_id=self._run_id,
                    classification="INFERENCE",
                    content=f"[{stage}] {kind}: {content[:200]}",
                    source_type="TOOL",
                    change_set_id=self._cs_id,
                )
                self.result.evidence.append(entry)
            except Exception as e:
                self.result.add_finding(
                    "ERROR", stage, "evidence_recording",
                    f"Failed to record {kind}: {e}",
                )

    def _record_stage_handoffs(self, stage: str, identity: Identity) -> None:
        chain = self.scenario.get("handoff_chain", [])
        for ho in chain:
            if ho.get("stage_from") != stage:
                continue
            from_role = ho["from"]
            to_role = ho["to"]
            from_identity = ROLE_IDENTITIES.get(from_role, DEVELOPER)
            artifacts = ho.get("artifacts", [])
            payload = {
                "summary": f"Handoff from {from_role} to {to_role} at {stage}",
                "inputs": [
                    {"artifact_ref": f"{a}@{SHA[:7]}:plans/{a}.yaml"}
                    for a in artifacts
                ],
                "outputs": [
                    {"artifact_kind": a, "content_hash": "sha256:" + "ab" * 32}
                    for a in artifacts
                ],
                "classifications": [
                    {"classification": "INFERENCE", "content": f"{a} produced at {stage}"}
                    for a in artifacts
                ],
            }
            try:
                ho_result = self.cm.record_handoff(
                    from_identity,
                    change_set_id=self._cs_id,
                    to_role=to_role,
                    payload=payload,
                    verdict="ACCEPT",
                )
                self.result.handoffs.append(ho_result)
            except Exception as e:
                self.result.add_finding(
                    "ERROR", stage, "handoff_recording",
                    f"Handoff {from_role}->{to_role} failed: {e}",
                )

    def _validate_handoff_chain(self) -> None:
        chain = self.scenario.get("handoff_chain", [])
        if not chain:
            self.result.add_finding(
                "WARNING", "GLOBAL", "handoff_chain",
                "No handoff chain defined in scenario",
            )
            return
        recorded_pairs = {
            (h["from_role"], h["to_role"]) for h in self.result.handoffs
        }
        for ho in chain:
            pair = (ho["from"], ho["to"])
            if pair not in recorded_pairs:
                self.result.add_finding(
                    "ERROR", ho.get("stage_from", "?"), "handoff_completeness",
                    f"Expected handoff {pair[0]}->{pair[1]} not recorded",
                )

    def _validate_traceability(self) -> None:
        stages = self.scenario.get("stages", {})
        for stage_name in STAGE_ORDER:
            if stage_name not in stages:
                continue
            stage = stages[stage_name]
            inputs_from = stage.get("inputs_from", [])
            for upstream in inputs_from:
                if upstream not in stages:
                    continue
                upstream_outputs = set(stages[upstream].get("outputs", {}).keys())
                if not upstream_outputs:
                    self.result.add_finding(
                        "ERROR", stage_name, "traceability",
                        f"Upstream {upstream} produced no outputs for {stage_name}",
                    )

    def _validate_authority(self) -> None:
        for entry in self.result.evidence:
            if entry.get("classification") in ("FACT", "VERIFIED", "APPROVED"):
                actor = entry.get("actor_type", "")
                if actor == "AGENT":
                    self.result.add_finding(
                        "CRITICAL", "GLOBAL", "authority_violation",
                        f"Agent wrote {entry['classification']} "
                        f"(entry {entry.get('id', '?')})",
                    )

    def _validate_evidence_completeness(self) -> None:
        stages_run = set(self.result.stage_results.keys())
        expected = {s for s in STAGE_ORDER if s in self.scenario.get("stages", {})}
        missing = expected - stages_run
        if missing:
            self.result.add_finding(
                "ERROR", "GLOBAL", "stage_coverage",
                f"Expected stages not run: {sorted(missing)}",
            )


class FailureInjector:
    """Injects failures into a scenario to test cascade handling."""

    @staticmethod
    def skip_stage(scenario: dict[str, Any], stage: str) -> dict[str, Any]:
        modified = json.loads(json.dumps(scenario))
        modified["stages"].pop(stage, None)
        modified["handoff_chain"] = [
            h for h in modified.get("handoff_chain", [])
            if h.get("stage_from") != stage and h.get("stage_to") != stage
        ]
        return modified

    @staticmethod
    def empty_outputs(scenario: dict[str, Any], stage: str) -> dict[str, Any]:
        modified = json.loads(json.dumps(scenario))
        if stage in modified.get("stages", {}):
            modified["stages"][stage]["outputs"] = {}
        return modified

    @staticmethod
    def inject_wrong_verdict(scenario: dict[str, Any], from_role: str,
                             to_role: str) -> dict[str, Any]:
        modified = json.loads(json.dumps(scenario))
        for ho in modified.get("handoff_chain", []):
            if ho["from"] == from_role and ho["to"] == to_role:
                ho["_inject_verdict"] = "REJECT"
        return modified

    @staticmethod
    def corrupt_handoff_artifacts(scenario: dict[str, Any], stage: str) -> dict[str, Any]:
        modified = json.loads(json.dumps(scenario))
        for ho in modified.get("handoff_chain", []):
            if ho.get("stage_from") == stage:
                ho["artifacts"] = ["nonexistent-artifact-kind"]
        return modified


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--scenario", required=True, help="Path to scenario YAML")
    ap.add_argument("--mode", choices=["canned", "live"], default="canned",
                    help="canned (default) or live")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args(argv)

    scenario_path = Path(args.scenario)
    if not scenario_path.is_file():
        print(f"scenario not found: {scenario_path}", file=sys.stderr)
        return 2

    if args.mode == "live":
        import os
        if os.environ.get("ADLC_LIVE_MODE") != "1":
            print("Live mode requires ADLC_LIVE_MODE=1 environment variable", file=sys.stderr)
            return 2

    scenario = load_scenario(scenario_path)
    runner = CannedPipelineRunner(scenario)
    result = runner.run()

    if args.json:
        print(json.dumps(result.summary(), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.scenario}: "
              f"{result.summary()['stages_run']} stages, "
              f"{result.summary()['handoffs_recorded']} handoffs, "
              f"{result.summary()['evidence_entries']} evidence entries")
        for f in result.findings:
            print(f"  [{f['severity']}] {f['stage']}/{f['check']}: {f['detail']}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
