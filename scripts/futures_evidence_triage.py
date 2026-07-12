#!/usr/bin/env python3
"""Summarize futures research failures into a deterministic next-test queue.

This is research-only. It reads current Bill/Hermes evidence artifacts and
writes a compact handoff for weaker agents and post-market work. It does not
route, size, approve, or submit trades.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
OUT = STATE / "futures-evidence-triage.latest.json"
FUTURES_NO_EDGE = ROOT / ".rumbling-hedge/research/futures-no-edge-ledger/latest.json"
FABERVAALE_ORB_REPLAY = STATE / "futures-nq-fabervaale-orb-replay.latest.json"
FABERVAALE_ORB_LOCAL_REPLAY = STATE / "futures-nq-fabervaale-orb-local-5m-replay.latest.json"
FABERVAALE_ORB_LOCAL_WALKFORWARD = STATE / "futures-nq-fabervaale-orb-local-5m-walkforward.latest.json"
FABERVAALE_ORB_LOCAL_COST_STRESS = STATE / "futures-nq-fabervaale-orb-local-5m-cost-stress.latest.json"
FABERVAALE_ORB_TOPSTEP_REPLAY = STATE / "futures-nq-fabervaale-orb-topstep-1m-replay.latest.json"
DATABENTO_ORDERFLOW_FEATURE_SMOKE = STATE / "databento-orderflow-feature-smoke.latest.json"
CURRENT_FORM_REJECTED_VERDICTS = {"no-edge", "needs-new-feature"}


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def walkforward_failure_counts(walkforward: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for config in walkforward.get("configs") or []:
        for mode in config.get("failureModes") or []:
            counts[str(mode)] += 1
    return dict(counts.most_common())


def walkforward_profile_counts(walkforward: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for config in walkforward.get("configs") or []:
        for window in config.get("windows") or []:
            profile = window.get("selectedProfileId")
            if profile:
                counts[str(profile)] += 1
    return dict(counts.most_common())


def rolling_failure_counts(rolling: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for window in rolling.get("windows") or []:
        for key in ("baseline", "tuned"):
            for check in ((window.get(key) or {}).get("failedChecks") or []):
                counts[str(check)] += 1
    return dict(counts.most_common())


def vol_regime_summary(vol_oos: dict[str, Any]) -> dict[str, Any]:
    aggregate = vol_oos.get("aggregateOos") or {}
    windows = vol_oos.get("windows") or []
    worst = sorted(
        [
            {
                "window": window.get("window"),
                "testStart": window.get("testStart"),
                "testEnd": window.get("testEnd"),
                "netR": num((window.get("test") or {}).get("netR")),
                "trades": int(num((window.get("test") or {}).get("trades"))),
                "profitFactor": num((window.get("test") or {}).get("profitFactor")),
            }
            for window in windows
            if isinstance(window, dict)
        ],
        key=lambda item: item["netR"],
    )[:3]
    return {
        "status": vol_oos.get("status", "missing"),
        "signalMode": vol_oos.get("signalMode", "normal"),
        "aggregate": {
            "trades": int(num(aggregate.get("trades"))),
            "winRate": num(aggregate.get("winRate")),
            "netR": num(aggregate.get("netR")),
            "profitFactor": num(aggregate.get("profitFactor")),
            "maxDrawdownR": num(aggregate.get("maxDrawdownR")),
        },
        "blockers": vol_oos.get("blockers") or [],
        "worstWindows": worst,
    }


def fabervaale_orb_summary(replay: dict[str, Any]) -> dict[str, Any]:
    oos = replay.get("oosStats") if isinstance(replay.get("oosStats"), dict) else {}
    blockers = [str(blocker) for blocker in (replay.get("blockers") or [])]
    decision = str(replay.get("decision") or "missing")
    sample_blocked = any(blocker in blockers for blocker in [
        "too-few-oos-trades",
        "too-few-trades-for-historical-replay",
        "cadence-too-coarse-for-fabervaale-5m-close",
    ])
    return {
        "present": bool(replay),
        "decision": decision,
        "strategy": replay.get("strategy", "missing"),
        "tradeCount": int(num(replay.get("tradeCount"))),
        "oosStats": oos,
        "blockers": blockers,
        "sampleBlocked": sample_blocked,
        "researchOnly": replay.get("researchOnly", True),
        "writesOrders": replay.get("writesOrders", False),
        "touchesBroker": replay.get("touchesBroker", False),
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "promotionDecision": (
            "blocked-thin-sample"
            if sample_blocked
            else "watch-research-only"
            if decision.endswith("-watch")
            else "blocked"
        ),
        "requiredNextEvidence": [
            "larger NQ 5-minute historical sample",
            "purged walk-forward on the exact long-only rule",
            "cost/slippage stress on the exact rule",
            "current data parity and realtime execution-grade data",
            "daily Bill route approval before any demo discussion",
        ],
    }


def fabervaale_broker_grade_summary(replay: dict[str, Any]) -> dict[str, Any]:
    summary = fabervaale_orb_summary(replay)
    summary["sourceRole"] = "broker-grade-current-topstep-readonly"
    summary["inputPath"] = replay.get("inputPath")
    summary["oosTradeCount"] = int(num((replay.get("oosStats") or {}).get("trades")))
    summary["requiredNextEvidence"] = [
        "extend read-only Topstep/ProjectX NQ archive across more RTH sessions",
        "rerun the exact fixed FaberVaale ORB rule with no parameter changes",
        "require at least 50 OOS broker-grade trades before any demo-shadow discussion",
        "then run walk-forward and cost/slippage stress on the same broker-grade replay",
    ]
    return summary


def fabervaale_orb_comparison(primary: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    primary_summary = fabervaale_orb_summary(primary)
    comparison_summary = fabervaale_orb_summary(comparison)
    comparison_watch = comparison_summary["promotionDecision"] == "watch-research-only"
    return {
        "primarySeagate5m": primary_summary,
        "local5m60dResearch": comparison_summary,
        "decision": (
            "research-watch-needs-broker-grade-data-and-larger-clean-sample"
            if comparison_watch
            else "research-only-blocked"
        ),
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "interpretation": (
            "Local 5m research data supports continued investigation, but cannot override Seagate thin sample, current data parity, realtime data, or daily route approval gates."
            if comparison_watch
            else "No FaberVaale replay source currently provides promotion-grade evidence."
        ),
    }


def fabervaale_walkforward_summary(walkforward: dict[str, Any]) -> dict[str, Any]:
    blockers = [str(blocker) for blocker in (walkforward.get("blockers") or [])]
    decision = str(walkforward.get("decision") or "missing")
    sample_blocked = any(blocker in blockers for blocker in [
        "too-few-complete-walkforward-folds",
        "too-few-trades-for-walkforward-folds",
    ])
    return {
        "present": bool(walkforward),
        "decision": decision,
        "foldSize": int(num(walkforward.get("foldSize"))),
        "foldCount": int(num(walkforward.get("foldCount"))),
        "positiveFoldShare": num(walkforward.get("positiveFoldShare")),
        "worstFoldNetR": num(walkforward.get("worstFoldNetR")),
        "aggregateStats": walkforward.get("aggregateStats") if isinstance(walkforward.get("aggregateStats"), dict) else {},
        "blockers": blockers,
        "sampleBlocked": sample_blocked,
        "researchOnly": walkforward.get("researchOnly", True),
        "writesOrders": walkforward.get("writesOrders", False),
        "touchesBroker": walkforward.get("touchesBroker", False),
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "promotionDecision": (
            "blocked-thin-walkforward-sample"
            if sample_blocked
            else "watch-research-only"
            if decision.endswith("-watch")
            else "blocked"
        ),
    }


def fabervaale_cost_stress_summary(cost_stress: dict[str, Any]) -> dict[str, Any]:
    cases = cost_stress.get("cases") if isinstance(cost_stress.get("cases"), list) else []
    blockers = [str(blocker) for blocker in (cost_stress.get("blockers") or [])]
    case_count = int(num(cost_stress.get("caseCount"), len(cases)))
    surviving_count = int(num(cost_stress.get("survivingCaseCount")))
    all_survive = bool(cases) and surviving_count == case_count
    return {
        "present": bool(cost_stress),
        "decision": cost_stress.get("decision", "missing"),
        "caseCount": case_count,
        "survivingCaseCount": surviving_count,
        "allCostCasesSurvive": all_survive,
        "cases": [
            {
                "costPointsRoundTrip": case.get("costPointsRoundTrip"),
                "survives": bool(case.get("survives")),
                "oosStats": case.get("oosStats") if isinstance(case.get("oosStats"), dict) else {},
            }
            for case in cases
            if isinstance(case, dict)
        ],
        "blockers": blockers,
        "researchOnly": cost_stress.get("researchOnly", True),
        "writesOrders": cost_stress.get("writesOrders", False),
        "touchesBroker": cost_stress.get("touchesBroker", False),
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "promotionDecision": (
            "watch-research-only"
            if all_survive and cost_stress.get("decision") == "research-only-historical-session-cost-stress-watch"
            else "blocked"
        ),
        "requiredNextEvidence": [
            "walk-forward sample depth must clear",
            "larger broker-grade/current NQ 5-minute sample",
            "current data parity and realtime execution-grade data",
            "daily Bill route approval before any demo discussion",
        ],
    }


def databento_orderflow_summary(smoke: dict[str, Any]) -> dict[str, Any]:
    features = smoke.get("features") if isinstance(smoke.get("features"), dict) else {}
    rows = features.get("rows") if isinstance(features.get("rows"), list) else []
    return {
        "present": bool(smoke),
        "status": smoke.get("status", "missing"),
        "decision": smoke.get("decision", "missing"),
        "featureFamily": features.get("featureFamily", "missing"),
        "snapshotOnly": features.get("snapshotOnly", True),
        "researchUsable": bool(features.get("researchUsable")),
        "completeBidAsk": bool(features.get("completeBidAsk")),
        "completeDepthSize": bool(features.get("completeDepthSize")),
        "domProxyReplacementReady": False,
        "rowCount": len(rows),
        "rows": rows,
        "reason": features.get("reason", "missing"),
        "researchOnly": smoke.get("researchOnly", True),
        "writesOrders": smoke.get("writesOrders", False),
        "touchesBroker": smoke.get("touchesBroker", False),
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "requiredNextEvidence": [
            "open-session execution-grade Databento MBP/MBP-1 quote with depth sizes",
            "rolling no-lookahead capture, not one snapshot",
            "OOS comparison against no-DOM baseline",
            "cost/slippage, current data parity, broker parity, and daily route approval",
        ],
    }


def no_edge_entry(no_edge: dict[str, Any], entry_id: str) -> dict[str, Any]:
    entries = no_edge.get("entries") if isinstance(no_edge.get("entries"), list) else []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == entry_id:
            return entry
    return {}


def current_form_rejected(no_edge: dict[str, Any], entry_id: str) -> bool:
    entry = no_edge_entry(no_edge, entry_id)
    verdict = str(entry.get("verdict") or "")
    return verdict in CURRENT_FORM_REJECTED_VERDICTS or bool(entry.get("currentFormRejected"))


def lower_timeframe_current_form_rejected(no_edge: dict[str, Any], lower_timeframe: dict[str, Any]) -> bool:
    tested = [
        timeframe
        for timeframe, item in lower_timeframe.items()
        if isinstance(item, dict) and (item.get("status") or "missing") != "missing"
    ]
    return bool(tested) and all(
        current_form_rejected(no_edge, f"wq-vol-regime-{timeframe}-current-form")
        for timeframe in tested
    )


def backtrader_survivors_rejected(no_edge: dict[str, Any]) -> bool:
    return current_form_rejected(
        no_edge,
        "backtrader-full-sample-survivors-with-zero-vol-oos-survivors",
    )


def build_next_tests(
    walkforward_failures: dict[str, int],
    rolling_failures: dict[str, int],
    vol_summary: dict[str, Any],
    inverse_summary: dict[str, Any],
    lower_timeframe: dict[str, Any],
    cost_gate: dict[str, Any],
    no_edge: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    no_edge = no_edge or {}
    tests: list[dict[str, Any]] = []
    if walkforward_failures.get("stitched-oos-sample-too-thin") or rolling_failures.get("testTradeCount"):
        tested_lower = any((item.get("status") or "missing") != "missing" for item in lower_timeframe.values())
        if tested_lower:
            if not lower_timeframe_current_form_rejected(no_edge, lower_timeframe):
                tests.append({
                    "id": "lower-timeframe-vol-regime-current-form-rejected",
                    "track": "futures",
                    "priority": 1,
                    "oneVariable": "timeframe/data-window",
                    "hypothesis": "Lower timeframe sample depth improved, but the current vol-regime rule still failed the promotion contract.",
                    "commandHint": "Do not mine parameters on this same rule. Either add a materially different feature/filter or move to another strategy family.",
                    "promotionRule": "A lower-timeframe branch may continue only if OOS trades >= 80, netR > 0, PF >= 1.25, and at least 67% of windows are profitable.",
                })
        else:
            tests.append({
                "id": "increase-oos-sample-before-parameter-mining",
                "track": "futures",
                "priority": 1,
                "oneVariable": "timeframe/data-window",
                "hypothesis": "The current 60m stack is too sparse for promotion decisions; lower timeframes or longer clean history may separate real edge from no-trade noise.",
                "commandHint": "Run the same OOS contract on 15m and 30m normalized NQ data with fixed costs/slippage, without changing strategy logic.",
                "promotionRule": "Only continue if OOS trades >= 80, netR > 0, PF >= 1.25, and at least 67% of windows are profitable.",
            })
    inverse_rejected = inverse_summary.get("status") == "reject-current-oos" and inverse_summary.get("aggregate", {}).get("netR", 0) <= 0
    if vol_summary["aggregate"]["netR"] < 0 and not inverse_rejected:
        tests.append({
            "id": "retire-or-invert-vol-regime-60m",
            "track": "futures",
            "priority": 2,
            "oneVariable": "signal direction",
            "hypothesis": "The vol-regime 60m candidate may be anti-predictive OOS; test a sign-flipped research replay before spending more parameter-search budget.",
            "commandHint": "Add a research-only inverse mode to vol_regime_oos_replay.py, then compare identical windows/params against the current rejected baseline.",
            "promotionRule": "Inverse mode is only a candidate if it passes the same purged OOS contract and beats the original after costs.",
        })
    elif (
        vol_summary["aggregate"]["netR"] < 0
        and inverse_rejected
        and not current_form_rejected(no_edge, "wq-vol-regime-60m-current-form")
    ):
        tests.append({
            "id": "retire-vol-regime-60m-current-form",
            "track": "futures",
            "priority": 2,
            "oneVariable": "strategy family",
            "hypothesis": "Both normal and inverse vol-regime 60m failed the same purged OOS contract, so this family should be retired until new data or a materially different feature definition exists.",
            "commandHint": "Move the current vol-regime 60m claim to no-edge/retired notes; spend next compute on sample-depth and different feature families.",
            "promotionRule": "Do not rerun this branch with parameter-only changes unless a new data source or structural feature is added.",
        })
    cost_rows_scored = int(num(((cost_gate.get("backtrader") or {}).get("rowsScored")), 0))
    if rolling_failures.get("deflatedExpectancyR") and cost_rows_scored <= 0:
        tests.append({
            "id": "cost-and-slippage-first-filter",
            "track": "futures",
            "priority": 3,
            "oneVariable": "cost model",
            "hypothesis": "Several apparent edges vanish after robustness adjustment; make costs/slippage a first-pass filter before Backtrader sweeps.",
            "commandHint": "Reject any new strategy row unless expectancy remains positive under 1x, 2x, and 3x fee/slippage stress.",
            "promotionRule": "No strategy enters demo-shadow unless deflated expectancy is positive in at least 3 consecutive OOS windows.",
        })
    elif rolling_failures.get("deflatedExpectancyR") and not backtrader_survivors_rejected(no_edge):
        tests.append({
            "id": "cost-slippage-survivor-review",
            "track": "futures",
            "priority": 3,
            "oneVariable": "cost model",
            "hypothesis": "Full-sample rows can survive harsh cost stress while OOS windows still fail; only OOS survivors deserve more compute.",
            "commandHint": "Inspect futures-cost-slippage-gate.latest.json. Treat Backtrader survivors as hypothesis seeds only; continue only with branches that survive purged OOS window stress.",
            "promotionRule": "No strategy enters demo-shadow unless positive under 1x/2x/3x cost stress and at least 3 OOS windows remain deployable.",
        })
    return tests


def build_fabervaale_next_tests(
    comparison: dict[str, Any],
    walkforward: dict[str, Any],
    cost_stress: dict[str, Any],
    orderflow: dict[str, Any],
) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    local = comparison.get("local5m60dResearch") if isinstance(comparison.get("local5m60dResearch"), dict) else {}
    if local.get("promotionDecision") == "watch-research-only":
        tests.append({
            "id": "fabervaale-orb-broker-grade-5m-depth",
            "track": "futures",
            "priority": 1,
            "oneVariable": "data source/depth",
            "hypothesis": "The fixed long-only FaberVaale ORB rule is promising on local 5m research data, but needs a larger broker-grade/current NQ 5m sample before any demo-shadow discussion.",
            "commandHint": "Extend read-only Topstep NQ/MNQ 1m archive, resample to 5m, then rerun the exact same FaberVaale ORB rule with no parameter changes.",
            "promotionRule": "Continue only if broker-grade 5m replay keeps OOS netR > 0, PF >= 1.25, at least 50 OOS trades, and no current-session/realtime data blockers remain.",
        })
    if walkforward.get("promotionDecision") == "blocked-thin-walkforward-sample":
        tests.append({
            "id": "fabervaale-orb-walkforward-depth",
            "track": "futures",
            "priority": 2,
            "oneVariable": "walk-forward sample depth",
            "hypothesis": "The local FaberVaale ORB branch has positive folds but too few complete folds/trades to trust.",
            "commandHint": "Increase clean 5m history and rerun purged walk-forward on the exact fixed rule; do not tune stops, targets, sessions, or filters in this pass.",
            "promotionRule": "Require >= 5 complete folds, >= 80 total OOS trades, positive worst fold, positiveFoldShare >= 0.67, and PF >= 1.25 after costs.",
        })
    if cost_stress.get("promotionDecision") == "watch-research-only":
        tests.append({
            "id": "fabervaale-orb-cost-stress-holdout",
            "track": "futures",
            "priority": 3,
            "oneVariable": "cost/slippage stress holdout",
            "hypothesis": "The FaberVaale ORB branch survives current cost cases, but that only matters after sample-depth and broker-grade data clear.",
            "commandHint": "After broker-grade replay and walk-forward depth clear, rerun 2/3/4/6 point round-trip stress on the held-out broker-grade sample.",
            "promotionRule": "All cost cases must survive with positive OOS netR and PF >= 1.25 before any demo-shadow sizing proposal.",
        })
    if orderflow.get("researchUsable") is False or orderflow.get("completeDepthSize") is False:
        tests.append({
            "id": "orderflow-current-depth-capture",
            "track": "futures",
            "priority": 4,
            "oneVariable": "order-flow data source",
            "hypothesis": "DOM proxy should remain a diagnostic placeholder until real bid/ask/depth data is captured and compared against the no-DOM baseline.",
            "commandHint": "Use the primary available execution-grade source for current depth/quotes; if Databento remains blocked by billing, keep Topstep/ProjectX as the current bar source and do not promote DOM proxy.",
            "promotionRule": "Order-flow overlay needs rolling no-lookahead capture, complete bid/ask/depth, OOS lift versus baseline, and all route gates green.",
        })
    return tests


def main() -> int:
    walkforward = read_json(STATE / "walkforward-matrix.latest.json")
    rolling = read_json(STATE / "oos-rolling.latest.json")
    if not rolling:
        rolling = read_json(STATE / "rolling-oos.latest.json")
    vol_oos = read_json(STATE / "vol-regime-oos-replay.latest.json")
    inverse_vol_oos = read_json(STATE / "vol-regime-oos-replay.inverse.latest.json")
    vol_15m = read_json(STATE / "vol-regime-oos-replay.15m.latest.json")
    vol_30m = read_json(STATE / "vol-regime-oos-replay.30m.latest.json")
    live_gate = read_json(STATE / "live-readiness-gate.latest.json")
    cost_gate = read_json(STATE / "futures-cost-slippage-gate.latest.json")
    no_edge = read_json(FUTURES_NO_EDGE)
    fabervaale_replay = read_json(FABERVAALE_ORB_REPLAY)
    fabervaale_local_replay = read_json(FABERVAALE_ORB_LOCAL_REPLAY)
    fabervaale_local_walkforward = read_json(FABERVAALE_ORB_LOCAL_WALKFORWARD)
    fabervaale_local_cost_stress = read_json(FABERVAALE_ORB_LOCAL_COST_STRESS)
    fabervaale_topstep_replay = read_json(FABERVAALE_ORB_TOPSTEP_REPLAY)
    databento_orderflow = read_json(DATABENTO_ORDERFLOW_FEATURE_SMOKE)

    wf_failures = walkforward_failure_counts(walkforward)
    rolling_failures = rolling_failure_counts(rolling)
    vol_summary = vol_regime_summary(vol_oos)
    inverse_summary = vol_regime_summary(inverse_vol_oos) if inverse_vol_oos else {}
    lower_timeframe = {
        "15m": vol_regime_summary(vol_15m) if vol_15m else {"status": "missing"},
        "30m": vol_regime_summary(vol_30m) if vol_30m else {"status": "missing"},
    }
    faber_comparison = fabervaale_orb_comparison(fabervaale_replay, fabervaale_local_replay)
    faber_walkforward = fabervaale_walkforward_summary(fabervaale_local_walkforward)
    faber_cost_stress = fabervaale_cost_stress_summary(fabervaale_local_cost_stress)
    orderflow_summary = databento_orderflow_summary(databento_orderflow)
    next_tests = build_next_tests(wf_failures, rolling_failures, vol_summary, inverse_summary, lower_timeframe, cost_gate, no_edge)
    next_tests.extend(build_fabervaale_next_tests(
        faber_comparison,
        faber_walkforward,
        faber_cost_stress,
        orderflow_summary,
    ))
    next_tests = sorted(next_tests, key=lambda item: (int(item.get("priority") or 99), str(item.get("id") or "")))

    blockers = list(live_gate.get("blockers") or [])
    payload = {
        "command": "futures-evidence-triage",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "decision": "research-only; no futures strategy is currently demo-expandable",
        "liveReadiness": {
            "readyForLive": live_gate.get("readyForLive", False),
            "readyForDemoExpansion": live_gate.get("readyForDemoExpansion", False),
            "blockers": blockers,
        },
        "walkforward": {
            "status": walkforward.get("status", "missing"),
            "generatedAt": walkforward.get("generatedAt", "missing"),
            "failureCounts": wf_failures,
            "selectedProfileCounts": walkforward_profile_counts(walkforward),
        },
        "rollingOos": {
            "windowCount": len(rolling.get("windows") or []),
            "failureCounts": rolling_failures,
            "deployableWindows": sum(
                1 for window in (rolling.get("windows") or [])
                if (window.get("baseline") or {}).get("deployableNow") or (window.get("tuned") or {}).get("deployableNow")
            ),
        },
        "costSlippageGate": {
            "backtraderSurvivors": (cost_gate.get("backtrader") or {}).get("survivorCount", "missing"),
            "volRegimeOosSurvivors": (cost_gate.get("volRegimeOos") or {}).get("survivorCount", "missing"),
            "failureCounts": cost_gate.get("failureCounts") or {},
            "readyForDemoExpansion": cost_gate.get("readyForDemoExpansion", False),
            "writesOrders": cost_gate.get("writesOrders", False),
        },
        "volRegimeOos": vol_summary,
        "volRegimeInverseOos": inverse_summary,
        "volRegimeLowerTimeframeOos": lower_timeframe,
        "youtubeFaberVaaleOrb": fabervaale_orb_summary(fabervaale_replay),
        "youtubeFaberVaaleOrbComparison": faber_comparison,
        "youtubeFaberVaaleOrbTopstepReplay": fabervaale_broker_grade_summary(fabervaale_topstep_replay),
        "youtubeFaberVaaleOrbLocalWalkforward": faber_walkforward,
        "youtubeFaberVaaleOrbLocalCostStress": faber_cost_stress,
        "databentoOrderflowFeatureSmoke": orderflow_summary,
        "noEdgeMemory": {
            "source": str(FUTURES_NO_EDGE),
            "count": no_edge.get("count", 0),
            "noEdgeCount": no_edge.get("noEdgeCount", 0),
            "needsNewFeatureCount": no_edge.get("needsNewFeatureCount", 0),
        },
        "nextTests": next_tests,
        "hardRules": [
            "Do not promote full-sample Backtrader rows over purged OOS rejection.",
            "Change one variable at a time and write the rejected result to the no-edge ledger.",
            "LLM/Hermes may propose hypotheses, but deterministic code and broker gates route trades.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
