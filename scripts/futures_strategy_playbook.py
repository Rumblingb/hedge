#!/usr/bin/env python3
"""Write the Bill/Hermes futures strategy playbook.

This is a deterministic handoff for humans, Hermes, and weaker agents. It does
not generate signals, size trades, touch Topstep, or approve routing. Its job is
to keep the current "gold" strategy claims honest: what can be watched, what is
blocked, and what evidence would be needed before demo expansion.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE / "futures-strategy-playbook.latest.json"
VAULT = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
DEFAULT_MARKDOWN = VAULT / "futures-strategy-playbook.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def gate_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    goal = read_json(Path(args.goal_audit))
    handoff = read_json(Path(args.clearance_handoff))
    premarket = read_json(Path(args.premarket_risk_brief))
    futures = read_json(Path(args.futures_evidence_triage))
    session = read_json(Path(args.topstep_session_safety))
    return {
        "goalDecision": goal.get("decision"),
        "goalBlockedIds": goal.get("blockedIds") if isinstance(goal.get("blockedIds"), list) else [],
        "handoffDecision": handoff.get("decision"),
        "handoffReadyForExecution": bool_value(handoff.get("readyForExecution")),
        "premarketDecision": premarket.get("decision"),
        "premarketAlgoMaxContracts": premarket.get("algoMaxContracts"),
        "futuresDecision": futures.get("decision"),
        "topstepSessionSafetyActive": bool_value(session.get("topstepMultipleSessionsDetected"))
        or bool_value(session.get("pauseBrokerTouchingProofs")),
        "topstepSessionSafetyReason": session.get("reason"),
    }


def strategy_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "orb-breakout-15m",
            "rank": 1,
            "role": "primary candidate, not execution-promoted",
            "instrument": "NQ/MNQ",
            "timeframe": "15m",
            "session": "NY morning only after opening range forms",
            "knownParams": {"rangeWindow": 8, "volumeThreshold": 1.3, "exitOffsetBars": 8},
            "useWhen": [
                "broker-grade Topstep/ProjectX data is fresh and reconciled",
                "no red-folder macro event is inside the active hold window",
                "opening range width is not extreme versus ATR",
                "15m direction agrees with at least one higher timeframe context",
                "daily plan allows futures algo research/demo and the 3-trade cap is not used",
            ],
            "doNotUseWhen": [
                "Topstep session-safety warning is active",
                "first breakout is late, thin, or already extended beyond the planned R",
                "signals cancel to flat or arbitration says NO_TRADE",
                "broker/current data parity or realtime proof is stale",
            ],
            "promotionEvidenceNeeded": [
                "broker-grade 5m/15m replay with at least 50 OOS trades",
                "purged walkforward with positive worst fold and PF >= 1.25 after costs",
                "cost/slippage stress survives 2/3/4/6 point round-trip cases",
                "wrapper emits only through guarded route with OCO proof and 50K sizing",
            ],
            "executionPolicy": "research-only until all gates clear",
        },
        {
            "id": "orb-breakout-30m",
            "rank": 2,
            "role": "slower confirmation / lower-frequency candidate",
            "instrument": "NQ/MNQ",
            "timeframe": "30m",
            "session": "NY morning to afternoon; avoid forced entries",
            "knownParams": {"rangeWindow": 8, "volumeThreshold": 1.3, "exitOffsetBars": 8},
            "useWhen": [
                "15m signal is noisy but 30m structure is clean",
                "trend day context is visible and pullbacks hold VWAP/structure",
                "trade count is below the daily/session cap",
            ],
            "doNotUseWhen": [
                "range is already exhausted before confirmation",
                "30m confirmation arrives into a scheduled macro release",
                "15m and 60m context disagree strongly",
            ],
            "promotionEvidenceNeeded": [
                "same OOS/walkforward/cost gates as ORB 15m",
                "explicit comparison against 15m ORB so it is not duplicate exposure",
            ],
            "executionPolicy": "research-only until all gates clear",
        },
        {
            "id": "wq-trend-mom-30m",
            "rank": 3,
            "role": "afternoon trend continuation candidate",
            "instrument": "NQ/MNQ",
            "timeframe": "30m",
            "session": "NY afternoon only when morning structure created a trend",
            "knownParams": {"shortSma": 20, "longSma": 60, "volumeThreshold": 1.3, "exitOffsetBars": 8},
            "useWhen": [
                "rolling-window/regime context says trend rather than chop",
                "ORB already resolved direction and market is accepting beyond the range",
                "prediction/news/macro overlay is not contradicting the trend",
            ],
            "doNotUseWhen": [
                "morning was two-sided chop",
                "Kalman/ES-NQ relative strength contradicts the NQ leg",
                "late-day liquidity or payout protection makes new risk unnecessary",
            ],
            "promotionEvidenceNeeded": [
                "walkforward OOS specific to NY afternoon",
                "duplicate-signal audit versus ORB so it does not double count the same edge",
            ],
            "executionPolicy": "research-only until all gates clear",
        },
        {
            "id": "wq-vol-regime-60m",
            "rank": 4,
            "role": "contrarian research, currently blocked despite attractive full-sample stats",
            "instrument": "NQ/MNQ",
            "timeframe": "60m",
            "session": "NY afternoon only if squeeze/expansion regime is proven current",
            "knownParams": {"shortLookback": 10, "longLookback": 20, "shortThreshold": 1.6, "longThreshold": 0.8, "exitOffsetBars": 8},
            "useWhen": [
                "only as a post-market/backtest research branch right now",
                "test normal versus inverse/contrarian interpretation one variable at a time",
            ],
            "doNotUseWhen": [
                "using full-sample win rate as live evidence",
                "walkforward OOS remains negative or has weak fold quality",
                "current broker data depth is thin",
            ],
            "promotionEvidenceNeeded": [
                "repair or retire based on rolling OOS, not full-sample R",
                "if inverse works, promote as a new thesis with separate no-edge ledger entry",
            ],
            "executionPolicy": "blocked from demo/live; research-only",
        },
        {
            "id": "fabervaale-orb-5m",
            "rank": 5,
            "role": "new frontier candidate from external strategy intake",
            "instrument": "NQ/MNQ",
            "timeframe": "5m",
            "session": "NY open only",
            "knownParams": {"rule": "fixed long-only ORB branch; no tuning during depth test"},
            "useWhen": [
                "only for broker-grade replay and walkforward depth collection",
                "use Topstep/ProjectX archive as the current broker-grade source after session safety clears",
            ],
            "doNotUseWhen": [
                "sample is thin",
                "using Seagate/local data as broker parity proof",
                "changing stops/targets while testing data-source depth",
            ],
            "promotionEvidenceNeeded": [
                ">= 50 OOS broker-grade trades before demo-shadow discussion",
                ">= 5 complete walkforward folds and >= 80 total OOS trades for challenge readiness",
            ],
            "executionPolicy": "research-only frontier",
        },
    ]


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    gates = gate_snapshot(args)
    hard_blockers = [
        blocker
        for blocker in [
            "topstep-session-safety" if gates["topstepSessionSafetyActive"] else None,
            "goal-audit-blocked" if gates["goalBlockedIds"] else None,
            "clearance-handoff-locked" if gates["handoffReadyForExecution"] is False else None,
            "premarket-no-trade" if gates["premarketDecision"] == "NO_TRADE_ALGO" else None,
        ]
        if blocker
    ]
    return {
        "command": "futures-strategy-playbook",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "research-only-strategy-playbook; no execution approval",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "accountTruth": {
            "liveChallengeAccount": "Topstep 50K",
            "demoCalibrationAccount": "Topstep 100K demo",
            "sizingUnit": "MNQ first unless a separately approved plan says otherwise",
            "maxTradesPolicy": "hard cap 3 trades per session/day; no-trade is a good outcome",
        },
        "gateSnapshot": gates,
        "hardBlockers": hard_blockers,
        "globalRules": [
            "LLMs research, summarize, and update memory; deterministic algos route only after gates clear.",
            "Never average into a loser on a prop challenge.",
            "Protect payout runway first: reduce size after a red-folder event, losing day, stale data, or signal conflict.",
            "Prediction-market signals may be context overlays only; they do not create futures entries by themselves.",
            "Treat price as lagging around news: premarket/news/flow can veto price-only trades.",
        ],
        "strategies": strategy_rows(),
        "nextEvidenceQueue": [
            "Clear Topstep multiple-session safety before any broker-touching proof window.",
            "Extend Topstep/ProjectX NQ/MNQ archive depth, then rerun fixed FaberVaale ORB with no parameter changes.",
            "Run ORB 15m and 30m broker-grade OOS/walkforward separately; compare duplication before combining.",
            "Retest WQ vol-regime normal versus inverse as separate one-variable research branches.",
            "Add every rejected branch to the no-edge ledger so the research loop stops rediscovering dead ideas.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Futures Strategy Playbook",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only strategy map. This page does not approve orders, demo expansion, live trading, funding, or copy trading.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Hard blockers: `{payload.get('hardBlockers')}`",
        f"- Gate snapshot: `{payload.get('gateSnapshot')}`",
        "",
        "## Account Truth",
        "",
    ]
    for key, value in (payload.get("accountTruth") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Global Rules", ""])
    for rule in payload.get("globalRules") or []:
        lines.append(f"- {rule}")
    lines.extend(["", "## Strategy Rows", ""])
    for row in payload.get("strategies") or []:
        lines.append(f"### `{row.get('id')}`")
        lines.append("")
        lines.append(f"- Rank: `{row.get('rank')}`")
        lines.append(f"- Role: {row.get('role')}")
        lines.append(f"- Timeframe/session: `{row.get('timeframe')}` / `{row.get('session')}`")
        lines.append(f"- Params: `{row.get('knownParams')}`")
        lines.append(f"- Execution policy: `{row.get('executionPolicy')}`")
        lines.append(f"- Use when: `{row.get('useWhen')}`")
        lines.append(f"- Do not use when: `{row.get('doNotUseWhen')}`")
        lines.append(f"- Promotion evidence needed: `{row.get('promotionEvidenceNeeded')}`")
        lines.append("")
    lines.extend(["## Next Evidence Queue", ""])
    for item in payload.get("nextEvidenceQueue") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the research-only futures strategy playbook.")
    parser.add_argument("--goal-audit", default=str(STATE / "bill-goal-completion-audit.latest.json"))
    parser.add_argument("--clearance-handoff", default=str(STATE / "bill-clearance-handoff.latest.json"))
    parser.add_argument("--premarket-risk-brief", default=str(STATE / "premarket-risk-brief.latest.json"))
    parser.add_argument("--futures-evidence-triage", default=str(STATE / "futures-evidence-triage.latest.json"))
    parser.add_argument("--topstep-session-safety", default=str(STATE / "topstep-session-safety.latest.json"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()
    payload = build_payload(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
