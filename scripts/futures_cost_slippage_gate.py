#!/usr/bin/env python3
"""Research-only futures cost/slippage first-pass gate.

This gate rejects strategy evidence that only works before realistic fees and
slippage. It reads existing research artifacts and writes a compact stress
summary. It never imports broker code and never writes orders.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE / "futures-cost-slippage-gate.latest.json"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def round4(value: float) -> float:
    return round(value, 4)


def stress_cases(base_slippage_points: float) -> list[dict[str, float]]:
    return [
        {"id": "1x", "feeMultiplier": 1.0, "slippagePointsRoundTrip": base_slippage_points},
        {"id": "2x", "feeMultiplier": 2.0, "slippagePointsRoundTrip": base_slippage_points * 2.0},
        {"id": "3x", "feeMultiplier": 3.0, "slippagePointsRoundTrip": base_slippage_points * 3.0},
    ]


def incremental_haircut_r(
    stop_points: float,
    multiplier: float,
    contracts: float,
    commission_round_turn: float,
    case: dict[str, float],
) -> float:
    risk_dollars = max(0.01, stop_points * multiplier * contracts)
    extra_fee = commission_round_turn * max(0.0, case["feeMultiplier"] - 1.0) * contracts
    extra_slippage = case["slippagePointsRoundTrip"] * multiplier * contracts
    return (extra_fee + extra_slippage) / risk_dollars


def score_backtrader_rows(backtrader: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = backtrader.get("results") if isinstance(backtrader.get("results"), list) else []
    scored: list[dict[str, Any]] = []
    for row in rows:
        trades = int(num(row.get("closedTrades")))
        if trades <= 0:
            continue
        stop_points = num(row.get("stopPoints"), args.default_stop_points)
        contracts = num(row.get("contracts"), 1.0)
        avg_r = num(row.get("avgR"))
        total_r = num(row.get("totalR"))
        cases = []
        survives = True
        for case in stress_cases(args.base_slippage_points):
            haircut = incremental_haircut_r(stop_points, args.multiplier, contracts, args.commission_round_turn, case)
            stressed_avg = avg_r - haircut
            stressed_total = total_r - haircut * trades
            if stressed_avg <= 0 or stressed_total <= 0:
                survives = False
            cases.append({
                "id": case["id"],
                "haircutR": round4(haircut),
                "stressedAvgR": round4(stressed_avg),
                "stressedTotalR": round4(stressed_total),
            })
        scored.append({
            "strategy": row.get("strategy"),
            "timeframeMinutes": row.get("timeframeMinutes"),
            "contracts": contracts,
            "closedTrades": trades,
            "stopPoints": stop_points,
            "targetPoints": row.get("targetPoints"),
            "rawAvgR": avg_r,
            "rawTotalR": total_r,
            "rawWinRate": row.get("winRate"),
            "survivesAllStress": survives,
            "stress": cases,
        })
    return sorted(scored, key=lambda item: item["stress"][-1]["stressedTotalR"], reverse=True)


def independent_backtrader_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("strategy", "missing")),
        str(row.get("timeframeMinutes", "missing")),
        str(row.get("stopPoints", "missing")),
        str(row.get("targetPoints", "missing")),
    )


def dedupe_backtrader_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one contract-size variant per independent strategy configuration."""
    best_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = independent_backtrader_key(row)
        current = best_by_key.get(key)
        current_score = (current or {}).get("stress", [{}])[-1].get("stressedTotalR", float("-inf"))
        row_score = row.get("stress", [{}])[-1].get("stressedTotalR", float("-inf"))
        if current is None or row_score > current_score:
            best_by_key[key] = row
    return sorted(best_by_key.values(), key=lambda item: item["stress"][-1]["stressedTotalR"], reverse=True)


def score_vol_oos(path: Path, args: argparse.Namespace) -> dict[str, Any]:
    artifact = read_json(path)
    windows = artifact.get("windows") if isinstance(artifact.get("windows"), list) else []
    aggregate = artifact.get("aggregateOos") or {}
    rows: list[dict[str, Any]] = []
    for window in windows:
        test = window.get("test") or {}
        selected = window.get("selected") or {}
        trades = int(num(test.get("trades")))
        if trades <= 0:
            continue
        stop_points = num(selected.get("stopPoints"), args.default_stop_points)
        avg_r = num(test.get("avgR"))
        net_r = num(test.get("netR"))
        cases = []
        survives = True
        for case in stress_cases(args.base_slippage_points):
            haircut = incremental_haircut_r(stop_points, args.multiplier, 1.0, args.commission_round_turn, case)
            stressed_avg = avg_r - haircut
            stressed_net = net_r - haircut * trades
            if stressed_avg <= 0 or stressed_net <= 0:
                survives = False
            cases.append({
                "id": case["id"],
                "haircutR": round4(haircut),
                "stressedAvgR": round4(stressed_avg),
                "stressedNetR": round4(stressed_net),
            })
        rows.append({
            "window": window.get("window"),
            "testStart": window.get("testStart"),
            "testEnd": window.get("testEnd"),
            "trades": trades,
            "stopPoints": stop_points,
            "rawAvgR": avg_r,
            "rawNetR": net_r,
            "survivesAllStress": survives,
            "stress": cases,
        })
    surviving_windows = sum(1 for row in rows if row["survivesAllStress"])
    return {
        "path": str(path.resolve()),
        "status": artifact.get("status", "missing"),
        "strategy": artifact.get("strategy", "missing"),
        "signalMode": artifact.get("signalMode", "missing"),
        "timeframeHint": path.name.replace("vol-regime-oos-replay.", "").replace(".latest.json", ""),
        "aggregateRaw": {
            "trades": int(num(aggregate.get("trades"))),
            "avgR": num(aggregate.get("avgR")),
            "netR": num(aggregate.get("netR")),
            "profitFactor": num(aggregate.get("profitFactor")),
        },
        "windowsEvaluated": len(rows),
        "survivingWindows": surviving_windows,
        "survivingWindowRatio": round4(surviving_windows / len(rows)) if rows else 0.0,
        "survivesGate": surviving_windows >= 3 and len(rows) >= 3 and surviving_windows / len(rows) >= 0.67,
        "windows": rows,
    }


def build_survivor_review(
    backtrader_survivors: list[dict[str, Any]],
    vol_oos_survivors: list[dict[str, Any]],
    vol_scores: list[dict[str, Any]],
) -> dict[str, Any]:
    """Make full-sample survivor status unambiguous for downstream agents."""
    strategy_families = sorted({
        f"{row.get('strategy')}:{row.get('timeframeMinutes')}m"
        for row in backtrader_survivors
    })
    if backtrader_survivors and not vol_oos_survivors:
        status = "blocked-full-sample-only"
        decision = "do-not-promote-backtrader-survivors-without-oos-survivors"
    elif vol_oos_survivors:
        status = "candidate-review-required"
        decision = "review-oos-survivors-before-demo-shadow"
    else:
        status = "no-cost-survivors"
        decision = "reject-current-cost-stress"
    return {
        "status": status,
        "decision": decision,
        "backtraderSurvivorCount": len(backtrader_survivors),
        "volOosSurvivorCount": len(vol_oos_survivors),
        "strategyFamilies": strategy_families,
        "parameterMiningRisk": (
            "high" if len(strategy_families) <= 2 and len(backtrader_survivors) >= 5 else "normal"
        ),
        "oosArtifactsReviewed": [
            {
                "timeframeHint": item.get("timeframeHint"),
                "status": item.get("status"),
                "aggregateNetR": (item.get("aggregateRaw") or {}).get("netR"),
                "aggregateProfitFactor": (item.get("aggregateRaw") or {}).get("profitFactor"),
                "survivingWindowRatio": item.get("survivingWindowRatio"),
                "survivesGate": item.get("survivesGate"),
            }
            for item in vol_scores
        ],
        "blockedSurvivorExamples": [
            {
                "strategy": row.get("strategy"),
                "timeframeMinutes": row.get("timeframeMinutes"),
                "stopPoints": row.get("stopPoints"),
                "targetPoints": row.get("targetPoints"),
                "stressedTotalR3x": (row.get("stress") or [{}])[-1].get("stressedTotalR"),
                "reviewDecision": "hypothesis-seed-only",
            }
            for row in backtrader_survivors[:5]
        ],
        "requiredNextEvidence": [
            "purged OOS artifact with at least 3 deployable windows",
            "positive aggregate OOS netR after costs",
            "profit factor >= 1.25 after costs",
            "profitable OOS window ratio >= 67%",
            "live-readiness gate still green for data/source/risk before any demo-shadow",
        ],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    backtrader = read_json(STATE / "backtrader-research.latest.json")
    backtrader_rows = score_backtrader_rows(backtrader, args)
    independent_backtrader_rows = dedupe_backtrader_rows(backtrader_rows)
    bt_survivors = [row for row in independent_backtrader_rows if row["survivesAllStress"]]
    vol_paths = [
        STATE / "vol-regime-oos-replay.latest.json",
        STATE / "vol-regime-oos-replay.inverse.latest.json",
        STATE / "vol-regime-oos-replay.15m.latest.json",
        STATE / "vol-regime-oos-replay.30m.latest.json",
    ]
    vol_scores = [score_vol_oos(path, args) for path in vol_paths if path.exists()]
    vol_survivors = [row for row in vol_scores if row["survivesGate"]]
    failure_counts: Counter[str] = Counter()
    if not bt_survivors:
        failure_counts["no-backtrader-row-survives-1x-2x-3x-stress"] += 1
    if not vol_survivors:
        failure_counts["no-vol-regime-oos-artifact-survives-window-stress"] += 1
    for score in vol_scores:
        if (score.get("aggregateRaw") or {}).get("netR", 0) <= 0:
            failure_counts[f"{score.get('timeframeHint')}-raw-oos-netR-not-positive"] += 1
        if score.get("survivingWindowRatio", 0) < 0.67:
            failure_counts[f"{score.get('timeframeHint')}-stressed-window-ratio-below-contract"] += 1

    return {
        "command": "futures-cost-slippage-gate",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "readyForDemoExpansion": False,
        "inputs": {
            "baseSlippagePointsRoundTrip": args.base_slippage_points,
            "commissionRoundTurn": args.commission_round_turn,
            "multiplier": args.multiplier,
            "defaultStopPoints": args.default_stop_points,
            "stressCases": stress_cases(args.base_slippage_points),
        },
        "decision": "research-only; no futures strategy may pass demo-shadow until positive under 1x/2x/3x cost and slippage stress",
        "backtrader": {
            "rowsScored": len(backtrader_rows),
            "independentRowsScored": len(independent_backtrader_rows),
            "dedupeKey": ["strategy", "timeframeMinutes", "stopPoints", "targetPoints"],
            "duplicateRowsRemoved": max(0, len(backtrader_rows) - len(independent_backtrader_rows)),
            "survivorCount": len(bt_survivors),
            "rawSurvivorCount": sum(1 for row in backtrader_rows if row["survivesAllStress"]),
            "topRows": independent_backtrader_rows[:10],
        },
        "volRegimeOos": {
            "artifactsScored": len(vol_scores),
            "survivorCount": len(vol_survivors),
            "items": vol_scores,
        },
        "survivorReview": build_survivor_review(bt_survivors, vol_survivors, vol_scores),
        "failureCounts": dict(failure_counts.most_common()),
        "hardRules": [
            "Full-sample survivors are not deployable without purged OOS and live-readiness.",
            "A row must stay positive at 1x, 2x, and 3x cost/slippage before it deserves more compute.",
            "Contract-size variants are not independent edge evidence; Backtrader survivors are deduplicated by strategy/timeframe/stop/target.",
            "This artifact writes no orders and cannot approve Topstep demo expansion.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only futures cost/slippage gate.")
    parser.add_argument("--base-slippage-points", type=float, default=0.25)
    parser.add_argument("--commission-round-turn", type=float, default=1.48)
    parser.add_argument("--multiplier", type=float, default=2.0)
    parser.add_argument("--default-stop-points", type=float, default=8.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    payload = build_report(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
