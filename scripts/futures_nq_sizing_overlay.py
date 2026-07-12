#!/usr/bin/env python3
"""Research-only NQ sizing overlay for fixed-rule session replays.

This changes only position sizing on an existing replay artifact. It does not
change entries, exits, stops, targets, timestamps, or data. The output is a
prop-firm risk fit diagnostic, not execution approval.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
DEFAULT_REPLAY = STATE / "futures-nq-fabervaale-orb-local-5m-replay.latest.json"
DEFAULT_OUT = STATE / "futures-nq-sizing-overlay.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
DEFAULT_MD = VAULT / "Agent-Hermes" / "futures-nq-sizing-overlay-2026-05-31.md"

TOPSTEP_COMBINE_PARAMS = {
    "50K": {
        "profitTarget": 3000.0,
        "maximumLossLimit": 2000.0,
        "dailyLossLimit": 1000.0,
        "maxMinis": 5,
        "maxMicros": 50,
        "bestDayRecommendation": 1500.0,
    },
    "100K": {
        "profitTarget": 6000.0,
        "maximumLossLimit": 3000.0,
        "dailyLossLimit": 2000.0,
        "maxMinis": 10,
        "maxMicros": 100,
        "bestDayRecommendation": 3000.0,
    },
    "150K": {
        "profitTarget": 9000.0,
        "maximumLossLimit": 4500.0,
        "dailyLossLimit": 3000.0,
        "maxMinis": 15,
        "maxMicros": 150,
        "bestDayRecommendation": 4500.0,
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def stats(values: list[float]) -> dict[str, Any]:
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {
        "trades": len(values),
        "netPnl": round(sum(values), 2),
        "avgPnl": round(sum(values) / len(values), 2) if values else None,
        "winRate": round(len(wins) / len(values), 6) if values else None,
        "profitFactor": round(gross_win / gross_loss, 6) if gross_loss else (999.0 if gross_win else None),
        "maxDrawdown": round(max_drawdown, 2),
        "wins": len(wins),
        "losses": len(losses),
    }


def parse_profiles(text: str) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for raw in text.split(","):
        item = raw.strip()
        if not item:
            continue
        if item.startswith("fixed:"):
            profiles.append({"id": f"fixed-{item.split(':', 1)[1]}", "kind": "fixed", "contracts": int(item.split(":", 1)[1])})
        elif item.startswith("risk:"):
            risk = float(item.split(":", 1)[1])
            profiles.append({"id": f"risk-{int(risk)}", "kind": "risk_budget", "riskDollars": risk})
        else:
            raise ValueError(f"unknown sizing profile: {item}")
    return profiles


def contracts_for_trade(
    profile: dict[str, Any],
    *,
    risk_points: float,
    point_value: float,
    max_contracts: int,
) -> int:
    if risk_points <= 0 or point_value <= 0:
        return 0
    if profile["kind"] == "fixed":
        return max(0, min(max_contracts, int(profile["contracts"])))
    risk_dollars = float(profile["riskDollars"])
    contracts = math.floor(risk_dollars / (risk_points * point_value))
    return max(0, min(max_contracts, contracts))


def evaluate_profile(
    replay: dict[str, Any],
    profile: dict[str, Any],
    *,
    point_value: float,
    max_contracts: int,
    daily_loss_limit: float,
    maximum_loss_limit: float,
    consistency_fraction: float,
    best_day_recommendation: float | None = None,
) -> dict[str, Any]:
    trades = [item for item in (replay.get("trades") or []) if isinstance(item, dict)]
    realized: list[dict[str, Any]] = []
    pnl_values: list[float] = []
    daily: dict[str, float] = {}
    skipped = 0
    for trade in trades:
        risk_points = float(trade.get("openingRangePoints") or 0)
        contracts = contracts_for_trade(profile, risk_points=risk_points, point_value=point_value, max_contracts=max_contracts)
        if contracts <= 0:
            skipped += 1
            continue
        pnl = float(trade.get("netR") or 0) * risk_points * point_value * contracts
        pnl = round(pnl, 2)
        pnl_values.append(pnl)
        date = str(trade.get("date", "missing"))
        daily[date] = daily.get(date, 0.0) + pnl
        realized.append({
            "date": date,
            "contracts": contracts,
            "riskPoints": round(risk_points, 4),
            "netR": trade.get("netR"),
            "pnl": pnl,
        })

    daily_values = list(daily.values())
    summary = stats(pnl_values)
    daily_stats = stats(daily_values)
    best_day = max(daily_values, default=0.0)
    total_profit = sum(daily_values)
    consistency_share = (best_day / total_profit) if total_profit > 0 else None
    blockers: list[str] = []
    if not pnl_values:
        blockers.append("no-sized-trades")
    if summary["maxDrawdown"] >= maximum_loss_limit:
        blockers.append("max-loss-limit-breached-in-sequence")
    if any(value <= -abs(daily_loss_limit) for value in daily_values):
        blockers.append("daily-loss-limit-breached")
    if best_day_recommendation is not None and best_day >= best_day_recommendation:
        blockers.append("best-day-above-50k-combine-recommendation")
    if consistency_share is not None and consistency_share > consistency_fraction:
        blockers.append("best-day-consistency-above-contract")
    if skipped:
        blockers.append("some-trades-skipped-by-risk-budget")
    if summary["netPnl"] <= 0:
        blockers.append("non-positive-sized-net-pnl")
    return {
        "id": profile["id"],
        "kind": profile["kind"],
        "profile": profile,
        "summary": summary,
        "dailyStats": daily_stats,
        "bestDayPnl": round(best_day, 2),
        "consistencyShare": round(consistency_share, 6) if consistency_share is not None else None,
        "skippedTrades": skipped,
        "realizedSample": realized[:12],
        "blockers": sorted(set(blockers)),
        "decision": "research-only-sizing-watch" if not blockers else "research-only-sizing-blocked",
    }


def build_overlay(
    *,
    replay: dict[str, Any],
    profiles: list[dict[str, Any]],
    account_size: str = "50K",
    instrument: str = "MNQ",
    point_value: float = 2.0,
    max_contracts: int | None = None,
    daily_loss_limit: float | None = None,
    maximum_loss_limit: float | None = None,
    consistency_fraction: float = 0.5,
) -> dict[str, Any]:
    account = TOPSTEP_COMBINE_PARAMS.get(account_size.upper(), TOPSTEP_COMBINE_PARAMS["50K"])
    account_size = account_size.upper() if account_size.upper() in TOPSTEP_COMBINE_PARAMS else "50K"
    resolved_max_contracts = (
        int(max_contracts)
        if max_contracts is not None
        else int(account["maxMicros"] if instrument.upper().startswith("M") else account["maxMinis"])
    )
    resolved_daily_loss_limit = float(daily_loss_limit if daily_loss_limit is not None else account["dailyLossLimit"])
    resolved_maximum_loss_limit = float(maximum_loss_limit if maximum_loss_limit is not None else account["maximumLossLimit"])
    blockers: list[str] = []
    if replay.get("decision") != "research-only-historical-session-replay-watch":
        blockers.append("source-replay-not-watch")
    profile_results = [
        evaluate_profile(
            replay,
            profile,
            point_value=point_value,
            max_contracts=resolved_max_contracts,
            daily_loss_limit=resolved_daily_loss_limit,
            maximum_loss_limit=resolved_maximum_loss_limit,
            consistency_fraction=consistency_fraction,
            best_day_recommendation=float(account["bestDayRecommendation"]),
        )
        for profile in profiles
    ]
    watch_profiles = [item for item in profile_results if item.get("decision") == "research-only-sizing-watch"]
    if not watch_profiles:
        blockers.append("no-sizing-profile-clears-prop-risk-diagnostic")
    best = max(
        profile_results,
        key=lambda item: (
            item.get("decision") == "research-only-sizing-watch",
            float((item.get("summary") or {}).get("netPnl") or 0),
            -float((item.get("summary") or {}).get("maxDrawdown") or 0),
        ),
        default={},
    )
    return {
        "command": "futures-nq-sizing-overlay",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "sourceReplayDecision": replay.get("decision"),
        "sourceReplayPath": str(DEFAULT_REPLAY),
        "sourceStrategy": replay.get("strategy"),
        "tradeCount": replay.get("tradeCount", len(replay.get("trades") or [])),
        "oneVariable": "position sizing only",
        "assumptions": {
            "accountSize": account_size,
            "instrument": instrument,
            "pointValue": point_value,
            "maxContracts": resolved_max_contracts,
            "profitTarget": account["profitTarget"],
            "dailyLossLimit": resolved_daily_loss_limit,
            "maximumLossLimit": resolved_maximum_loss_limit,
            "bestDayRecommendation": account["bestDayRecommendation"],
            "consistencyFraction": consistency_fraction,
            "topstepRulesChecked": "2026-05-31 official Topstep Help Center",
        },
        "profileResults": profile_results,
        "bestProfileId": best.get("id"),
        "blockers": sorted(set(blockers)),
        "decision": "research-only-sizing-overlay-watch" if not blockers else "research-only-sizing-overlay-blocked",
        "hardRules": [
            "This artifact changes only sizing on an existing replay.",
            "Sizing watch is not Topstep demo approval.",
            "Do not use this to bypass current/broker parity, execution-grade data, daily plan, source hygiene, or OOS promotion gates.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Futures NQ Sizing Overlay - 2026-05-31",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only sizing audit. This page does not approve Topstep demo or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Best profile: `{payload.get('bestProfileId')}`",
        f"- One variable: `{payload.get('oneVariable')}`",
        f"- Source replay: `{payload.get('sourceReplayDecision')}` / `{payload.get('sourceStrategy')}`",
        f"- Assumptions: `{payload.get('assumptions')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Profiles",
        "",
    ]
    for item in payload.get("profileResults") or []:
        lines.append(
            f"- `{item.get('id')}` decision `{item.get('decision')}`, "
            f"summary `{item.get('summary')}`, bestDay `{item.get('bestDayPnl')}`, "
            f"consistency `{item.get('consistencyShare')}`, blockers `{item.get('blockers')}`"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a research-only sizing overlay on an NQ replay.")
    parser.add_argument("--replay", default=str(DEFAULT_REPLAY))
    parser.add_argument("--profiles", default="fixed:1,fixed:2,risk:250,risk:500,risk:1000")
    parser.add_argument("--account-size", choices=sorted(TOPSTEP_COMBINE_PARAMS), default="50K")
    parser.add_argument("--instrument", default="MNQ")
    parser.add_argument("--point-value", type=float, default=2.0)
    parser.add_argument("--max-contracts", type=int, default=None)
    parser.add_argument("--daily-loss-limit", type=float, default=None)
    parser.add_argument("--maximum-loss-limit", type=float, default=None)
    parser.add_argument("--consistency-fraction", type=float, default=0.5)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MD))
    args = parser.parse_args()

    payload = build_overlay(
        replay=read_json(Path(args.replay)),
        profiles=parse_profiles(args.profiles),
        account_size=args.account_size,
        instrument=args.instrument,
        point_value=args.point_value,
        max_contracts=args.max_contracts,
        daily_loss_limit=args.daily_loss_limit,
        maximum_loss_limit=args.maximum_loss_limit,
        consistency_fraction=args.consistency_fraction,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md = Path(args.markdown)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
