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
        "premarketAlgoMaxContracts": (premarket.get("sizingPosture") or {}).get("algoMaxContracts"),
        "premarketManualWatchMaxContractsIfCleared": (premarket.get("sizingPosture") or {}).get("manualWatchMaxContractsIfDailyPlanClears"),
        "premarketRiskCounts": premarket.get("riskCounts") if isinstance(premarket.get("riskCounts"), dict) else {},
        "futuresDecision": futures.get("decision"),
        "topstepSessionSafetyActive": bool_value(session.get("topstepMultipleSessionsDetected"))
        or bool_value(session.get("pauseBrokerTouchingProofs")),
        "topstepSessionSafetyReason": session.get("reason"),
    }


def best_one_variable_watch(one_variable: dict[str, Any]) -> dict[str, Any]:
    summary = one_variable.get("resultSummary") if isinstance(one_variable.get("resultSummary"), dict) else {}
    best = summary.get("bestObserved") if isinstance(summary.get("bestObserved"), dict) else {}
    if not best:
        return {}
    return {
        "experimentId": best.get("experimentId"),
        "baselineId": best.get("baselineId"),
        "strategy": best.get("strategy"),
        "timeframe": best.get("timeframe"),
        "oosTradeCount": best.get("oosTradeCount"),
        "oosNetPoints": best.get("oosNetPoints"),
        "oosProfitFactor": best.get("oosProfitFactor"),
        "oosWinRate": best.get("oosWinRate"),
        "walkforwardPositiveFoldShare": best.get("walkforwardPositiveFoldShare"),
        "blockers": best.get("blockers") if isinstance(best.get("blockers"), list) else [],
        "researchCandidate": bool_value(best.get("researchCandidate")),
    }


def sizing_watch(sizing: dict[str, Any]) -> dict[str, Any]:
    profiles = sizing.get("profileResults") if isinstance(sizing.get("profileResults"), list) else []
    best_id = sizing.get("bestProfileId")
    best = next((row for row in profiles if isinstance(row, dict) and row.get("id") == best_id), {})
    return {
        "decision": sizing.get("decision"),
        "bestProfileId": best_id,
        "assumptions": sizing.get("assumptions") if isinstance(sizing.get("assumptions"), dict) else {},
        "bestProfile": {
            "id": best.get("id"),
            "blockers": best.get("blockers") if isinstance(best.get("blockers"), list) else [],
            "summary": best.get("summary") if isinstance(best.get("summary"), dict) else {},
            "dailyStats": best.get("dailyStats") if isinstance(best.get("dailyStats"), dict) else {},
            "bestDayPnl": best.get("bestDayPnl"),
            "consistencyShare": best.get("consistencyShare"),
        } if best else {},
    }


def strategy_rows(one_variable: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    one_variable = one_variable or {}
    best_watch = best_one_variable_watch(one_variable)
    rows = [
        {
            "id": "orb-breakout-15m",
            "rank": 1,
            "role": "primary watch candidate, not execution-promoted",
            "instrument": "NQ/MNQ",
            "timeframe": "15m",
            "session": "NY morning only after opening range forms",
            "knownParams": {"rangeWindow": 8, "volumeThreshold": 1.3, "exitOffsetBars": 8},
            "currentEvidence": (
                best_watch
                if best_watch.get("baselineId") == "orb-breakout-15m"
                else {"status": "no-current-one-variable-watch"}
            ),
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
    return rows


def session_instrument_matrix(one_variable: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    one_variable = one_variable or {}
    best_watch = best_one_variable_watch(one_variable)
    orb_watch = best_watch if best_watch.get("baselineId") == "orb-breakout-15m" else {}
    return [
        {
            "session": "Asia",
            "nqUse": "stand-down",
            "esUse": "stand-down",
            "strategy": None,
            "evidence": "No current promoted NQ/ES Asia edge. Older Asia/London session gates reduced total edge on short 21d tests and are not enough for prop-risk.",
            "founderAction": "Do not force overnight trades. Use Asia only for context: prior range, overnight inventory, and red-folder setup into London/NY.",
            "demoTradeAllowed": False,
        },
        {
            "session": "London",
            "nqUse": "stand-down or context only",
            "esUse": "stand-down or context only",
            "strategy": None,
            "evidence": "London breakout notes are forex-derived/mixed and current vault says ignore for direct futures. No OOS futures promotion evidence.",
            "founderAction": "Record London high/low, liquidity sweep, and macro tone. Do not route NQ/ES futures solely from London breakout.",
            "demoTradeAllowed": False,
        },
        {
            "session": "NY morning",
            "nqUse": "primary manual-watch research lane",
            "esUse": "confirmation/context before separate ES route",
            "strategy": "orb-breakout-15m / FaberVaale ORB depth lane",
            "evidence": orb_watch or "15m ORB is the strongest current watch lane, but no candidate is promoted.",
            "founderAction": "If daily plan and broker gates are GREEN, observe/consider only the ORB 15m lane first; otherwise run read-only replay, cost stress, and demo-learning capture.",
            "demoTradeAllowed": False,
        },
        {
            "session": "NY afternoon",
            "nqUse": "secondary watch only after morning trend acceptance",
            "esUse": "relative-strength / confirmation context",
            "strategy": "wq-trend-mom-30m candidate, not promoted",
            "evidence": "WQ trend momentum needs NY-afternoon-specific OOS and duplicate-signal audit versus ORB.",
            "founderAction": "Use only as a research branch. Do not add late-day risk after target, loss, red-folder, or unresolved demo-learning issue.",
            "demoTradeAllowed": False,
        },
        {
            "session": "All sessions",
            "nqUse": "research/no-edge memory",
            "esUse": "training and regime context",
            "strategy": "wq-vol-regime-60m current form",
            "evidence": "Full-sample rows looked attractive, but purged OOS and cost-stress evidence rejected promotion.",
            "founderAction": "Retire current form from demo routing. Only retest if a materially new feature/filter is introduced one variable at a time.",
            "demoTradeAllowed": False,
        },
    ]


def demo_trade_readiness_path(gates: dict[str, Any]) -> dict[str, Any]:
    return {
        "currentState": "locked-ready-to-observe" if gates.get("premarketDecision") == "NO_TRADE_ALGO" else "review-needed",
        "canTakeActualAlgoDemoTradeNow": False,
        "whyNotNow": [
            "daily plan route approval is not APPROVED",
            "broker reconciliation is not GREEN in the daily plan",
            "goal audit still has futures-demo-not-cleared",
            "clearance handoff is not CLEAR_FOR_EXECUTION",
        ],
        "minimumArmSequence": [
            "Refresh premarket risk brief and confirm no hard risks.",
            "Refresh Topstep broker reconciliation and write BROKER_RECONCILIATION: GREEN in the daily plan only if broker-native state proves it.",
            "Clear futures-demo-not-cleared via current-session broker-depth/freshness evidence.",
            "Set daily BILL_ROUTE_APPROVAL: APPROVED only for one named strategy, side, instrument, max size, and time window.",
            "Keep deterministic route through the guarded bridge only; LLM/Hermes may not submit orders.",
            "Submit at most the 50K policy size, OCO attached, then immediately log fills, MAE/MFE, exit reason, and mistake tags.",
        ],
        "firstEligibleLaneIfGatesClear": "NQ/MNQ NY-morning ORB 15m watch lane, 1 MNQ dry-run/manual-watch first unless the 50K policy explicitly says otherwise.",
    }


def build_daily_tactical_plan(
    *,
    gates: dict[str, Any],
    premarket: dict[str, Any],
    sizing: dict[str, Any],
    one_variable: dict[str, Any],
    topstep_learning: dict[str, Any],
) -> dict[str, Any]:
    hard_blocked = gates.get("premarketDecision") == "NO_TRADE_ALGO" or bool(gates.get("goalBlockedIds"))
    risk_counts = premarket.get("riskCounts") if isinstance(premarket.get("riskCounts"), dict) else {}
    hard_risks = [row for row in (premarket.get("risks") or []) if isinstance(row, dict) and row.get("severity") == "hard"]
    reduce_risks = [row for row in (premarket.get("risks") or []) if isinstance(row, dict) and row.get("severity") == "reduce"]
    demo_issues = topstep_learning.get("issues") if isinstance(topstep_learning.get("issues"), list) else []
    best_watch = best_one_variable_watch(one_variable)
    size_watch = sizing_watch(sizing)
    if hard_blocked:
        decision = "stand-down"
        max_algo_contracts = 0
        max_manual_watch_contracts = 0
    elif reduce_risks:
        decision = "reduced-size-watch"
        max_algo_contracts = 0
        max_manual_watch_contracts = 1
    else:
        decision = "clean-watch-no-route-approval"
        max_algo_contracts = 0
        max_manual_watch_contracts = min(2, int(gates.get("premarketManualWatchMaxContractsIfCleared") or 2))
    return {
        "decision": decision,
        "operatorRead": "Daily tactical plan is a control-plane watch list. It cannot approve orders; daily plan and deterministic gates still own routing.",
        "maxAlgoContracts": max_algo_contracts,
        "maxManualWatchContractsIfHumanClearsDailyPlan": max_manual_watch_contracts,
        "preferredWatch": (
            {
                "strategyId": "orb-breakout-15m",
                "session": "NY morning only",
                "why": "strongest one-variable watch result, still blocked from promotion",
                "evidence": best_watch,
            }
            if best_watch.get("baselineId") == "orb-breakout-15m"
            else None
        ),
        "sizePolicyWatch": size_watch,
        "redFolderAndRiskDownRules": [
            "Stand down while any hard premarket risk is active.",
            "Use 0 algo contracts until daily route approval is explicit and broker reconciliation is GREEN.",
            "Use 1 MNQ max for manual watch after red-folder, losing day, source/data warning, signal conflict, or unresolved demo reconciliation issue.",
            "Do not copy 100K demo sizing to the 50K challenge; 50K policy is MNQ-first.",
            "No-trade is a valid payout-preserving outcome.",
        ],
        "hardRiskCount": risk_counts.get("hard", len(hard_risks)),
        "reduceRiskCount": risk_counts.get("reduce", len(reduce_risks)),
        "topHardRisks": hard_risks[:6],
        "topReduceRisks": reduce_risks[:6],
        "demoLearningIssues": demo_issues[:6],
        "mustFixBeforeDemoExpansion": [
            "broker-verify operator-reported 100K demo P&L before using it for promotion or sizing",
            "keep source hygiene clean and do not reintroduce sibling/canonical dirty execution drift",
            "clear prediction paper and futures demo gates separately",
            "prove current-session broker data depth and freshness without frequent Topstep sessions",
            "daily plan must name the exact strategy, instrument, size, time window, and route approval before any algo demo trade",
        ],
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    gates = gate_snapshot(args)
    premarket = read_json(Path(args.premarket_risk_brief))
    one_variable = read_json(Path(args.strategy_factory_one_variable))
    sizing = read_json(Path(args.sizing_overlay))
    topstep_learning = read_json(Path(args.topstep_learning))
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
        "dailyTacticalPlan": build_daily_tactical_plan(
            gates=gates,
            premarket=premarket,
            sizing=sizing,
            one_variable=one_variable,
            topstep_learning=topstep_learning,
        ),
        "sessionInstrumentMatrix": session_instrument_matrix(one_variable),
        "demoTradeReadinessPath": demo_trade_readiness_path(gates),
        "latestResearchWatch": {
            "oneVariable": best_one_variable_watch(one_variable),
            "sizing": sizing_watch(sizing),
        },
        "strategies": strategy_rows(one_variable),
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
    tactical = payload.get("dailyTacticalPlan") or {}
    lines.extend(["", "## Daily Tactical Plan", ""])
    lines.append(f"- Decision: `{tactical.get('decision')}`")
    lines.append(f"- Max algo contracts: `{tactical.get('maxAlgoContracts')}`")
    lines.append(f"- Max manual watch contracts if human clears daily plan: `{tactical.get('maxManualWatchContractsIfHumanClearsDailyPlan')}`")
    lines.append(f"- Preferred watch: `{tactical.get('preferredWatch')}`")
    lines.append(f"- Demo learning issues: `{tactical.get('demoLearningIssues')}`")
    lines.extend(["", "### Risk-Down Rules", ""])
    for rule in tactical.get("redFolderAndRiskDownRules") or []:
        lines.append(f"- {rule}")
    readiness = payload.get("demoTradeReadinessPath") or {}
    lines.extend(["", "## Demo Trade Readiness Path", ""])
    lines.append(f"- Current state: `{readiness.get('currentState')}`")
    lines.append(f"- Can take actual algo demo trade now: `{readiness.get('canTakeActualAlgoDemoTradeNow')}`")
    lines.append(f"- First eligible lane if gates clear: `{readiness.get('firstEligibleLaneIfGatesClear')}`")
    lines.append("- Why not now:")
    for item in readiness.get("whyNotNow") or []:
        lines.append(f"  - {item}")
    lines.append("- Minimum arm sequence:")
    for item in readiness.get("minimumArmSequence") or []:
        lines.append(f"  - {item}")
    lines.extend(["", "## Session / Instrument Matrix", ""])
    for row in payload.get("sessionInstrumentMatrix") or []:
        lines.append(f"### {row.get('session')}")
        lines.append(f"- NQ use: `{row.get('nqUse')}`")
        lines.append(f"- ES use: `{row.get('esUse')}`")
        lines.append(f"- Strategy: `{row.get('strategy')}`")
        lines.append(f"- Evidence: {row.get('evidence')}")
        lines.append(f"- Founder action: {row.get('founderAction')}")
        lines.append(f"- Demo trade allowed: `{row.get('demoTradeAllowed')}`")
    lines.extend(["", "## Strategy Rows", ""])
    for row in payload.get("strategies") or []:
        lines.append(f"### `{row.get('id')}`")
        lines.append("")
        lines.append(f"- Rank: `{row.get('rank')}`")
        lines.append(f"- Role: {row.get('role')}")
        lines.append(f"- Timeframe/session: `{row.get('timeframe')}` / `{row.get('session')}`")
        lines.append(f"- Params: `{row.get('knownParams')}`")
        lines.append(f"- Current evidence: `{row.get('currentEvidence')}`")
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
    parser.add_argument("--strategy-factory-one-variable", default=str(STATE / "strategy-factory-one-variable-research.latest.json"))
    parser.add_argument("--sizing-overlay", default=str(STATE / "futures-nq-sizing-overlay.latest.json"))
    parser.add_argument("--topstep-learning", default=str(STATE / "topstep-daily-learning.latest.json"))
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
