#!/usr/bin/env python3
"""Plan or run the research-only NQ futures evidence cycle.

This cycle keeps the promising Seagate/current-local NQ research lane separate
from execution. Default mode is a dry-run plan; ``--run-local-research`` runs
only local research/audit commands and refreshes handoff artifacts. It never
routes orders, sizes trades, or touches broker execution.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"

HISTORICAL_COVERAGE = STATE / "futures-nq-historical-coverage-audit.latest.json"
HISTORICAL_REPLAY = STATE / "futures-nq-historical-session-replay.latest.json"
HISTORICAL_WALKFORWARD = STATE / "futures-nq-historical-session-walkforward.latest.json"
HISTORICAL_COST_STRESS = STATE / "futures-nq-historical-session-cost-stress.latest.json"
CURRENT_PARITY = STATE / "futures-nq-current-data-parity.latest.json"
SESSION_STRUCTURE = STATE / "futures-nq-session-structure-audit.latest.json"
DATA_REQUIREMENTS = STATE / "futures-data-requirements.latest.json"
BROKER_PARITY_PLAN = STATE / "futures-broker-parity-plan.latest.json"
HANDOFF = STATE / "bill-clearance-handoff.latest.json"
FABERVAALE_LOCAL_5M_REPLAY = STATE / "futures-nq-fabervaale-orb-local-5m-replay.latest.json"
FABERVAALE_LOCAL_5M_WALKFORWARD = STATE / "futures-nq-fabervaale-orb-local-5m-walkforward.latest.json"
FABERVAALE_LOCAL_5M_COST_STRESS = STATE / "futures-nq-fabervaale-orb-local-5m-cost-stress.latest.json"
OUT = STATE / "futures-nq-research-cycle.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"futures-nq-research-cycle-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def compact_output(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def command_text(argv: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in argv)


def npm_cmd(script: str) -> list[str]:
    return ["npm", "run", "--silent", script]


def safe_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
        "RH_TOPSTEP_READ_ONLY": "true",
        "RH_LIVE_EXECUTION_ENABLED": "false",
    })
    return env


def planned_steps() -> list[dict[str, Any]]:
    raw_steps = [
        ("audit-external-alpha-data", npm_cmd("bill:external-alpha-data-audit")),
        ("audit-historical-coverage", npm_cmd("bill:futures-nq-historical-coverage-audit")),
        ("replay-historical-session-edge", npm_cmd("bill:futures-nq-historical-session-replay")),
        ("walkforward-historical-session-edge", npm_cmd("bill:futures-nq-historical-session-walkforward")),
        ("stress-historical-session-costs", npm_cmd("bill:futures-nq-historical-session-cost-stress")),
        ("check-current-local-parity", npm_cmd("bill:futures-nq-current-data-parity")),
        ("audit-session-structure", npm_cmd("bill:futures-nq-session-structure-audit")),
        ("refresh-data-requirements", npm_cmd("bill:futures-data-requirements")),
        ("refresh-broker-parity-plan", npm_cmd("bill:futures-broker-parity-plan")),
        ("refresh-alpha-frontier", npm_cmd("bill:alpha-frontier-queue")),
        ("refresh-next-research-actions", npm_cmd("bill:next-research-actions")),
        ("refresh-clearance-evidence", npm_cmd("bill:clearance-evidence")),
        ("refresh-clearance-handoff", npm_cmd("bill:clearance-handoff")),
        ("sync-obsidian-memory", npm_cmd("bill:obsidian-sync")),
    ]
    return [
        {
            "id": step_id,
            "argv": argv,
            "command": command_text(argv),
            "writesOrders": False,
            "touchesBroker": False,
        }
        for step_id, argv in raw_steps
    ]


def run_step(step: dict[str, Any], *, timeout_sec: int) -> dict[str, Any]:
    argv = step.get("argv") if isinstance(step.get("argv"), list) else []
    try:
        proc = subprocess.run(
            [str(part) for part in argv],
            cwd=str(ROOT),
            env=safe_env(),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **step,
            "status": "timeout",
            "returnCode": None,
            "stdoutTail": compact_output(exc.stdout or ""),
            "stderrTail": compact_output(exc.stderr or ""),
        }
    return {
        **step,
        "status": "pass" if proc.returncode == 0 else "fail",
        "returnCode": proc.returncode,
        "stdoutTail": compact_output(proc.stdout),
        "stderrTail": compact_output(proc.stderr),
    }


def best_candidate_id(coverage: dict[str, Any]) -> str | None:
    candidate = coverage.get("bestHistoricalOosCandidate")
    if isinstance(candidate, dict):
        return str(candidate.get("datasetId")) if candidate.get("datasetId") else None
    return None


def historical_current_parity_summary(coverage: dict[str, Any]) -> dict[str, Any]:
    candidate = coverage.get("bestHistoricalOosCandidate")
    if not isinstance(candidate, dict):
        return {
            "checked": False,
            "cleared": False,
            "reason": "missing-best-historical-candidate",
            "operatorRead": "No historical candidate is available, so no current/local parity comparison exists.",
        }
    parity = candidate.get("currentLocalCsvParity") if isinstance(candidate.get("currentLocalCsvParity"), dict) else {}
    feature_range = parity.get("featureRange") if isinstance(parity.get("featureRange"), dict) else {}
    local_range = parity.get("localCsvRange") if isinstance(parity.get("localCsvRange"), dict) else {}
    overlap_rows = int(parity.get("overlapRows") or 0)
    cleared = parity.get("ok") is True
    reason = str(parity.get("reason") or "missing-current-local-csv-parity")
    return {
        "candidate": candidate.get("datasetId"),
        "checked": bool(parity.get("checked")),
        "cleared": cleared,
        "overlapRows": overlap_rows,
        "reason": reason,
        "featureRange": feature_range,
        "localCsvRange": local_range,
        "localCsv": parity.get("localCsv"),
        "operatorRead": (
            "Historical source is usable for research/OOS only; it has no overlapping bars with the current local CSV and cannot prove broker/current parity."
            if not cleared and overlap_rows == 0
            else "Historical/current local parity is clean for this candidate, but broker and realtime proof are still separate execution gates."
            if cleared
            else "Historical/current local parity is incomplete or mismatched; keep this out of demo evidence."
        ),
    }


def build_cycle(
    *,
    coverage: dict[str, Any],
    replay: dict[str, Any],
    walkforward: dict[str, Any],
    cost_stress: dict[str, Any],
    current_parity: dict[str, Any],
    session_structure: dict[str, Any],
    data_requirements: dict[str, Any],
    broker_parity_plan: dict[str, Any],
    handoff: dict[str, Any],
    local_5m_replay: dict[str, Any] | None = None,
    local_5m_walkforward: dict[str, Any] | None = None,
    local_5m_cost_stress: dict[str, Any] | None = None,
    run_local_research: bool = False,
    ran_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    handoff_gates = handoff.get("gates") if isinstance(handoff.get("gates"), dict) else {}
    blockers: list[str] = []
    if not best_candidate_id(coverage):
        blockers.append("no-historical-oos-candidate")
    if coverage.get("currentLocalCsvParityCheckedCount") and not coverage.get("currentLocalCsvParityClearedCount"):
        blockers.append("historical-current-local-csv-parity-not-cleared")
    if data_requirements.get("decision") != "research-only-data-requirements-cleared":
        blockers.append("futures-data-requirements-not-cleared")
    if broker_parity_plan.get("decision") != "research-only-futures-broker-parity-proof-plan-clear":
        blockers.append("futures-broker-parity-proof-missing")
    if current_parity.get("brokerParityChecked") is not True:
        blockers.append("broker-parity-not-checked")
    if handoff_gates.get("realtimeDataReady") is not True:
        blockers.append("execution-grade-realtime-not-cleared")
    if (handoff.get("obsidian") or {}).get("dailyRouteApproval") != "ALLOW":
        blockers.append("daily-route-approval-not-allow")
    if not run_local_research:
        blockers.append("dry-run-only; pass --run-local-research to refresh local futures evidence")

    steps = ran_steps if ran_steps is not None else [
        {**step, "status": "planned" if run_local_research else "skipped-dry-run"}
        for step in planned_steps()
    ]
    failed_steps = [
        str(step.get("id"))
        for step in steps
        if step.get("status") in {"fail", "timeout"}
    ]
    if failed_steps:
        blockers.append("cycle-step-failed")
    local_5m_replay = local_5m_replay or {}
    local_5m_walkforward = local_5m_walkforward or {}
    local_5m_cost_stress = local_5m_cost_stress or {}

    return {
        "command": "futures-nq-research-cycle",
        "generatedAt": now_iso(),
        "mode": "run-local-research" if run_local_research else "dry-run",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "safeEnv": {
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
            "RH_TOPSTEP_READ_ONLY": "true",
            "RH_LIVE_EXECUTION_ENABLED": "false",
        },
        "historical": {
            "coverageDecision": coverage.get("decision"),
            "coverageBlockers": coverage.get("blockers") if isinstance(coverage.get("blockers"), list) else [],
            "bestCandidate": best_candidate_id(coverage),
            "currentParitySummary": historical_current_parity_summary(coverage),
            "usableHistoricalOosCount": coverage.get("usableHistoricalOosCount"),
            "preferredPromotionDepthCount": coverage.get("preferredPromotionDepthCount"),
            "currentLocalCsvParityCheckedCount": coverage.get("currentLocalCsvParityCheckedCount"),
            "currentLocalCsvParityClearedCount": coverage.get("currentLocalCsvParityClearedCount"),
            "replayDecision": replay.get("decision"),
            "tradeCount": replay.get("tradeCount"),
            "walkforwardDecision": walkforward.get("decision"),
            "foldCount": walkforward.get("foldCount"),
            "positiveFoldShare": walkforward.get("positiveFoldShare"),
            "worstFoldNetR": walkforward.get("worstFoldNetR"),
            "costStressDecision": cost_stress.get("decision"),
            "survivingCaseCount": cost_stress.get("survivingCaseCount"),
            "caseCount": cost_stress.get("caseCount"),
            "local5mOneVariable": {
                "id": "futures-youtube-fabervaale-orb-vol-target-oos",
                "oneVariable": "local 5m source/cadence with fixed FaberVaale ORB rules",
                "replayDecision": local_5m_replay.get("decision"),
                "tradeCount": local_5m_replay.get("tradeCount"),
                "oosStats": local_5m_replay.get("oosStats") if isinstance(local_5m_replay.get("oosStats"), dict) else {},
                "walkforwardDecision": local_5m_walkforward.get("decision"),
                "foldCount": local_5m_walkforward.get("foldCount"),
                "positiveFoldShare": local_5m_walkforward.get("positiveFoldShare"),
                "walkforwardBlockers": (
                    local_5m_walkforward.get("blockers")
                    if isinstance(local_5m_walkforward.get("blockers"), list)
                    else []
                ),
                "worstFoldNetR": local_5m_walkforward.get("worstFoldNetR"),
                "costStressDecision": local_5m_cost_stress.get("decision"),
                "survivingCostCases": local_5m_cost_stress.get("survivingCaseCount"),
                "readyForDemoExpansion": False,
                "researchOnly": True,
                "promotionRead": "Promising replay/cost context only; blocked by walk-forward depth, broker/current parity, execution-grade realtime data, and daily route approval.",
            },
        },
        "current": {
            "currentParityDecision": current_parity.get("decision"),
            "cleanLocalResearchPairCount": current_parity.get("cleanLocalResearchPairCount"),
            "brokerParityChecked": current_parity.get("brokerParityChecked"),
            "sessionStructureDecision": session_structure.get("decision"),
            "sessionCount": session_structure.get("sessionCount"),
            "dataRequirementsDecision": data_requirements.get("decision"),
            "dataRequirementsBlockedCount": data_requirements.get("blockedCount"),
            "brokerParityPlanDecision": broker_parity_plan.get("decision"),
            "missingProofs": broker_parity_plan.get("missingProofs") if isinstance(broker_parity_plan.get("missingProofs"), list) else [],
        },
        "handoff": {
            "decision": handoff.get("decision"),
            "readyForExecution": handoff.get("readyForExecution"),
            "readyForDemoExpansion": handoff.get("readyForDemoExpansion"),
            "realtimeDataDecision": handoff_gates.get("realtimeDataDecision"),
            "realtimeDataReady": handoff_gates.get("realtimeDataReady"),
            "databentoStatus": handoff_gates.get("databentoStatus"),
        },
        "steps": steps,
        "failedStepIds": failed_steps,
        "blockers": blockers,
        "decision": (
            "research-only-futures-cycle-ran"
            if run_local_research and not blockers
            else "research-only-futures-cycle-ran-still-blocked"
            if run_local_research
            else "research-only-futures-cycle-dry-run-ready"
        ),
        "limitations": [
            "Historical watch status is not demo approval.",
            "Current local parity is not broker parity; broker/realtime proof remains a separate gate.",
            "This cycle sets execution-safe env flags and cannot approve route controls.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    historical = payload.get("historical") if isinstance(payload.get("historical"), dict) else {}
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    local_5m = historical.get("local5mOneVariable") if isinstance(historical.get("local5mOneVariable"), dict) else {}
    lines = [
        f"# Futures NQ Research Cycle - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only loop for Seagate/current-local NQ evidence. This page does not approve demo, live, sizing, routing, or orders.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Mode: `{payload.get('mode')}`",
        f"- Best historical candidate: `{historical.get('bestCandidate')}`",
        f"- Current-local CSV parity for historical sources: `{historical.get('currentLocalCsvParityClearedCount')}/{historical.get('currentLocalCsvParityCheckedCount')}`, blockers `{historical.get('coverageBlockers')}`",
        f"- Replay: `{historical.get('replayDecision')}` trades `{historical.get('tradeCount')}`",
        f"- Walk-forward: `{historical.get('walkforwardDecision')}` folds `{historical.get('foldCount')}` positive share `{historical.get('positiveFoldShare')}` worst fold `{historical.get('worstFoldNetR')}`",
        f"- Cost stress: `{historical.get('costStressDecision')}` survivors `{historical.get('survivingCaseCount')}/{historical.get('caseCount')}`",
        f"- Current parity: `{current.get('currentParityDecision')}` broker checked `{current.get('brokerParityChecked')}`",
        f"- Data requirements: `{current.get('dataRequirementsDecision')}` blocked `{current.get('dataRequirementsBlockedCount')}`",
        f"- Ready for demo expansion: `{payload.get('readyForDemoExpansion')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        "",
    ]
    if local_5m:
        lines.extend([
            f"- Local 5m FaberVaale replay: `{local_5m.get('replayDecision')}` trades `{local_5m.get('tradeCount')}` OOS `{local_5m.get('oosStats')}`",
            f"- Local 5m FaberVaale walk-forward: `{local_5m.get('walkforwardDecision')}` folds `{local_5m.get('foldCount')}` blockers `{local_5m.get('walkforwardBlockers')}`",
            f"- Local 5m FaberVaale read: {local_5m.get('promotionRead')}",
            "",
        ])
    lines.extend(["## Steps", ""])
    for step in payload.get("steps") or []:
        lines.append(f"- `{step.get('id')}`: `{step.get('status')}`")
        if step.get("command"):
            lines.append(f"  - `{step.get('command')}`")
    lines.extend(["", "## Blockers", ""])
    for blocker in payload.get("blockers") or ["none"]:
        lines.append(f"- {blocker}")
    lines.extend(["", "## Limitations", ""])
    for item in payload.get("limitations") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or run the research-only NQ futures evidence cycle.")
    parser.add_argument("--run-local-research", action="store_true")
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(default_markdown_path()))
    args = parser.parse_args()

    artifacts = {
        "coverage": read_json(HISTORICAL_COVERAGE),
        "replay": read_json(HISTORICAL_REPLAY),
        "walkforward": read_json(HISTORICAL_WALKFORWARD),
        "cost_stress": read_json(HISTORICAL_COST_STRESS),
        "current_parity": read_json(CURRENT_PARITY),
        "session_structure": read_json(SESSION_STRUCTURE),
        "data_requirements": read_json(DATA_REQUIREMENTS),
        "broker_parity_plan": read_json(BROKER_PARITY_PLAN),
        "handoff": read_json(HANDOFF),
        "local_5m_replay": read_json(FABERVAALE_LOCAL_5M_REPLAY),
        "local_5m_walkforward": read_json(FABERVAALE_LOCAL_5M_WALKFORWARD),
        "local_5m_cost_stress": read_json(FABERVAALE_LOCAL_5M_COST_STRESS),
    }
    ran_steps: list[dict[str, Any]] | None = None
    if args.run_local_research:
        ran_steps = [run_step(step, timeout_sec=240) for step in planned_steps()]
        artifacts = {
            "coverage": read_json(HISTORICAL_COVERAGE),
            "replay": read_json(HISTORICAL_REPLAY),
            "walkforward": read_json(HISTORICAL_WALKFORWARD),
            "cost_stress": read_json(HISTORICAL_COST_STRESS),
            "current_parity": read_json(CURRENT_PARITY),
            "session_structure": read_json(SESSION_STRUCTURE),
            "data_requirements": read_json(DATA_REQUIREMENTS),
            "broker_parity_plan": read_json(BROKER_PARITY_PLAN),
            "handoff": read_json(HANDOFF),
            "local_5m_replay": read_json(FABERVAALE_LOCAL_5M_REPLAY),
            "local_5m_walkforward": read_json(FABERVAALE_LOCAL_5M_WALKFORWARD),
            "local_5m_cost_stress": read_json(FABERVAALE_LOCAL_5M_COST_STRESS),
        }

    payload = build_cycle(run_local_research=args.run_local_research, ran_steps=ran_steps, **artifacts)
    out = Path(args.output)
    md = Path(args.markdown_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
