#!/usr/bin/env python3
"""Build the Topstep demo observation posture for Bill/Hermes.

This artifact exists because a human can be actively demo-trading while the
agentic system remains execution-locked. It turns local control artifacts into
a one-week observation plan: premarket risk, intraday read-only capture, EOD
learning/dreaming, and promotion blockers. It never touches broker APIs,
submits orders, changes flags, or treats operator P&L as broker proof.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "topstep-demo-observation-posture.latest.json"
DEFAULT_MARKDOWN = HERMES / f"topstep-demo-observation-posture-{datetime.now(timezone.utc).date().isoformat()}.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "pass", "green", "approved"}
    return False


def maybe_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def top_risk_kinds(premarket: dict[str, Any], severity: str) -> list[str]:
    risks = premarket.get("risks") if isinstance(premarket.get("risks"), list) else []
    return [
        str(item.get("kind"))
        for item in risks
        if isinstance(item, dict) and item.get("severity") == severity and item.get("kind")
    ][:8]


def build_posture(
    *,
    goal: dict[str, Any],
    clearance: dict[str, Any],
    handoff: dict[str, Any],
    session_clearance: dict[str, Any],
    premarket: dict[str, Any],
    topstep_learning: dict[str, Any],
    runtime_architecture: dict[str, Any],
    source_hygiene: dict[str, Any],
    prediction_gate: dict[str, Any],
    operator_demo_pnl: float | None = None,
    operator_account: str = "Topstep 100K demo",
    observation_days: int = 7,
) -> dict[str, Any]:
    clearance_pass = bool_value(clearance.get("allCommandsPassed")) or clearance.get("status") == "PASS"
    machine_session_ok = bool_value(session_clearance.get("machineChecksPassed"))
    runtime_visible = runtime_architecture.get("decision") == "runtime-architecture-visible-execution-locked"
    learning_visible = topstep_learning.get("decision") == "demo-learning-visible-execution-locked"
    premarket_visible = premarket.get("command") == "premarket-risk-brief"
    handoff_locked = handoff.get("decision") in {"KEEP_EXECUTION_LOCKED", None, ""}
    goal_blocked = goal.get("blockedIds") if isinstance(goal.get("blockedIds"), list) else []
    canonical_source_clean = bool_value(source_hygiene.get("sourceClean"))
    source_hygiene_cleared = bool_value(source_hygiene.get("sourceHygieneCleared"))
    source_clean_blockers = (
        source_hygiene.get("sourceCleanBlockers")
        if isinstance(source_hygiene.get("sourceCleanBlockers"), list)
        else []
    )
    prediction_blocked = prediction_gate.get("decision") == "research-only-paper-promotion-blocked"

    observation_blockers: list[str] = []
    if not clearance_pass:
        observation_blockers.append("clearance-evidence-not-pass")
    if not machine_session_ok:
        observation_blockers.append("topstep-session-machine-checks-not-pass")
    if not learning_visible:
        observation_blockers.append("topstep-daily-learning-missing-or-stale")
    if not premarket_visible:
        observation_blockers.append("premarket-risk-brief-missing")
    if not runtime_visible:
        observation_blockers.append("runtime-architecture-audit-missing")

    ready_for_human_demo_observation = not observation_blockers
    hard_risks = top_risk_kinds(premarket, "hard")
    reduce_risks = top_risk_kinds(premarket, "reduce")
    operator_confirmation_required = bool_value(session_clearance.get("operatorConfirmationRequired"))
    ready_for_read_only_proof_window = bool_value(session_clearance.get("readyForReadOnlyProofWindow"))

    return {
        "command": "topstep-demo-observation-posture",
        "generatedAt": now_iso(),
        "decision": (
            "demo-observation-ready-execution-locked"
            if ready_for_human_demo_observation
            else "demo-observation-blocked-execution-locked"
        ),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForHumanDemoObservation": ready_for_human_demo_observation,
        "readyForReadOnlyProofWindow": ready_for_read_only_proof_window,
        "readyForAlgoDemoExpansion": False,
        "readyForExecution": False,
        "readyForLive": False,
        "observationBlockers": observation_blockers,
        "algoExpansionBlockers": list(goal_blocked),
        "operatorDemoContext": {
            "account": operator_account,
            "reportedPnlDollars": operator_demo_pnl,
            "brokerProof": False,
            "promotionUse": "context-and-learning-only-until-broker-reconciled",
        },
        "canonicalTruthOrder": [
            "TopstepX/ProjectX broker-native account, fills, positions, and market data",
            "read-only local state artifacts under .rumbling-hedge/state",
            "trade journal rows when reconciled to broker timestamps",
            "Obsidian daily/control notes for human intent and mistakes",
            "operator claims as context only, never promotion proof",
        ],
        "authorityBoundaries": {
            "humanMayDemoTrade": True,
            "agentsMayObserveAndSummarize": ready_for_human_demo_observation,
            "agentsMayRouteOrders": False,
            "agentsMayChangeSizing": False,
            "dailyPlanMustApproveBeforeAnyAlgoRoute": True,
            "brokerReconciliationMustBeGreenBeforeAnyAlgoRoute": True,
        },
        "oneWeekDemoPlan": {
            "days": observation_days,
            "premarket": [
                "Run premarket risk brief before the first trade idea.",
                "Hard risks mean NO_TRADE_ALGO and human-only discretion.",
                "Red-folder macro, stale data, source hygiene, and session-safety warnings reduce or block size.",
            ],
            "intraday": [
                "Observe manual/demo trades, fills, positions, screenshots, and state freshness.",
                "Do not let Hermes, n8n, cron, or Codex submit orders.",
                "Capture strategy intent, setup, entry reason, exit reason, MAE/MFE, and mistake tags.",
            ],
            "eodDreaming": [
                "Run Topstep daily learning and Obsidian sync.",
                "Summarize what worked, what failed, what was luck, and one next-day rule change.",
                "Feed lessons into research queue/no-edge memory, not direct execution.",
            ],
        },
        "premarketGate": {
            "decision": premarket.get("decision", "missing"),
            "algoMaxContracts": (premarket.get("sizingPosture") or {}).get("algoMaxContracts")
            if isinstance(premarket.get("sizingPosture"), dict) else None,
            "manualWatchMaxContractsIfDailyPlanClears": (
                (premarket.get("sizingPosture") or {}).get("manualWatchMaxContractsIfDailyPlanClears")
                if isinstance(premarket.get("sizingPosture"), dict) else None
            ),
            "hardRiskKinds": hard_risks,
            "reduceRiskKinds": reduce_risks,
        },
        "topstepSession": {
            "machineChecksPassed": machine_session_ok,
            "operatorConfirmationRequired": operator_confirmation_required,
            "readyForReadOnlyProofWindow": ready_for_read_only_proof_window,
            "blockers": session_clearance.get("blockers") if isinstance(session_clearance.get("blockers"), list) else [],
        },
        "sourceAndPromotion": {
            "canonicalSourceClean": canonical_source_clean,
            "sourceHygieneCleared": source_hygiene_cleared,
            "sourceBlockerCount": len(source_clean_blockers),
            "sourceBlockers": source_clean_blockers,
            "goalBlockedIds": list(goal_blocked),
            "predictionPaperBlocked": prediction_blocked,
            "clearanceEvidencePassed": clearance_pass,
            "handoffDecision": handoff.get("decision"),
            "handoffLocked": handoff_locked,
        },
        "aiScientistFit": {
            "fit": "research-loop-only",
            "useFor": [
                "hypothesis generation",
                "one-variable experiment specs",
                "walk-forward/OOS experiment code",
                "result critique and no-edge memory updates",
            ],
            "neverUseFor": [
                "daily route approval",
                "order placement",
                "position sizing authority",
                "broker reconciliation",
                "live/payout claims",
            ],
        },
        "nextSafeCommands": [
            "npm run --silent bill:premarket-risk-brief",
            "npm run --silent bill:topstep-daily-learning",
            "npm run --silent bill:runtime-architecture-audit",
            "npm run --silent bill:clearance-evidence-fast",
            "npm run --silent bill:obsidian-sync",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Topstep Demo Observation Posture",
        "",
        f"Generated: `{payload.get('generatedAt')}`",
        f"Decision: `{payload.get('decision')}`",
        "",
        "## Authority",
        "",
    ]
    for key, value in (payload.get("authorityBoundaries") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Operator Demo Context", ""])
    for key, value in (payload.get("operatorDemoContext") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Blockers", ""])
    lines.append(f"- Observation blockers: `{payload.get('observationBlockers')}`")
    lines.append(f"- Algo expansion blockers: `{payload.get('algoExpansionBlockers')}`")
    lines.extend(["", "## Canonical Truth Order", ""])
    for item in payload.get("canonicalTruthOrder", []):
        lines.append(f"- {item}")
    lines.extend(["", "## One Week Demo Plan", ""])
    plan = payload.get("oneWeekDemoPlan") if isinstance(payload.get("oneWeekDemoPlan"), dict) else {}
    for section in ("premarket", "intraday", "eodDreaming"):
        lines.append(f"### {section}")
        for item in plan.get(section, []):
            lines.append(f"- {item}")
    lines.extend(["", "## Next Safe Commands", ""])
    for command in payload.get("nextSafeCommands", []):
        lines.append(f"- `{command}`")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Topstep demo observation posture.")
    parser.add_argument("--goal", default=str(STATE / "bill-goal-completion-audit.latest.json"))
    parser.add_argument("--clearance", default=str(STATE / "bill-clearance-evidence.latest.json"))
    parser.add_argument("--handoff", default=str(STATE / "bill-clearance-handoff.latest.json"))
    parser.add_argument("--session-clearance", default=str(STATE / "topstep-session-safety-clearance.latest.json"))
    parser.add_argument("--premarket", default=str(STATE / "premarket-risk-brief.latest.json"))
    parser.add_argument("--topstep-learning", default=str(STATE / "topstep-daily-learning.latest.json"))
    parser.add_argument("--runtime-architecture", default=str(STATE / "bill-runtime-architecture-audit.latest.json"))
    parser.add_argument("--source-hygiene", default=str(STATE / "bill-source-hygiene-plan.latest.json"))
    parser.add_argument("--prediction-gate", default=str(STATE / "prediction-event-paper-promotion-gate.latest.json"))
    parser.add_argument("--operator-demo-pnl", default=os.environ.get("BILL_TOPSTEP_OPERATOR_REPORTED_PNL"))
    parser.add_argument("--operator-account", default=os.environ.get("BILL_TOPSTEP_OPERATOR_ACCOUNT", "Topstep 100K demo"))
    parser.add_argument("--observation-days", type=int, default=7)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_posture(
        goal=read_json(Path(args.goal)),
        clearance=read_json(Path(args.clearance)),
        handoff=read_json(Path(args.handoff)),
        session_clearance=read_json(Path(args.session_clearance)),
        premarket=read_json(Path(args.premarket)),
        topstep_learning=read_json(Path(args.topstep_learning)),
        runtime_architecture=read_json(Path(args.runtime_architecture)),
        source_hygiene=read_json(Path(args.source_hygiene)),
        prediction_gate=read_json(Path(args.prediction_gate)),
        operator_demo_pnl=maybe_float(args.operator_demo_pnl),
        operator_account=args.operator_account,
        observation_days=args.observation_days,
    )
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown.write_text(render_markdown(payload))
    if args.compact:
        print(json.dumps({
            "decision": payload["decision"],
            "readyForHumanDemoObservation": payload["readyForHumanDemoObservation"],
            "readyForAlgoDemoExpansion": payload["readyForAlgoDemoExpansion"],
            "observationBlockers": payload["observationBlockers"],
            "algoExpansionBlockers": payload["algoExpansionBlockers"],
        }, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
