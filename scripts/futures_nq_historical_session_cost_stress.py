#!/usr/bin/env python3
"""Research-only cost/slippage stress for the NQ historical session replay."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
REPLAY = STATE / "futures-nq-historical-session-replay.latest.json"
OUT = STATE / "futures-nq-historical-session-cost-stress.latest.json"
VAULT = Path.home() / "Documents/memorybrain"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"futures-nq-historical-session-cost-stress-{current_utc_date()}.md"


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
    return {
        "trades": len(values),
        "netR": round(sum(values), 6),
        "avgR": round(sum(values) / len(values), 6) if values else None,
        "winRate": round(len(wins) / len(values), 6) if values else None,
        "profitFactor": round(gross_win / gross_loss, 6) if gross_loss else (999.0 if gross_win else None),
        "wins": len(wins),
        "losses": len(losses),
    }


def restress_trade(trade: dict[str, Any], cost_points: float) -> float | None:
    try:
        gross_r = float(trade["grossR"])
        risk = float(trade["openingRangePoints"])
        if risk <= 0:
            return None
        return gross_r - (cost_points / risk)
    except Exception:
        return None


def build_cost_stress(
    *,
    replay: dict[str, Any],
    cost_points_cases: list[float] | None = None,
    train_fraction: float = 0.6,
    min_oos_trades: int = 10,
    min_oos_profit_factor: float = 1.2,
    min_oos_net_r: float = 1.0,
) -> dict[str, Any]:
    cost_points_cases = cost_points_cases or [2.0, 3.0, 4.0, 6.0]
    trades = replay.get("trades") if isinstance(replay.get("trades"), list) else []
    trades = [trade for trade in trades if isinstance(trade, dict)]
    split_idx = max(1, min(len(trades), int(len(trades) * train_fraction))) if trades else 0
    blockers: list[str] = []
    if replay.get("decision") != "research-only-historical-session-replay-watch":
        blockers.append("source-replay-not-watch")
    if not trades:
        blockers.append("missing-source-trades")

    cases: list[dict[str, Any]] = []
    surviving_cases = 0
    for cost_points in cost_points_cases:
        stressed = [value for trade in trades if (value := restress_trade(trade, cost_points)) is not None]
        train = stressed[:split_idx]
        oos = stressed[split_idx:]
        aggregate_stats = stats(stressed)
        train_stats = stats(train)
        oos_stats = stats(oos)
        survives = (
            oos_stats["trades"] >= min_oos_trades
            and float(oos_stats["netR"] or 0) >= min_oos_net_r
            and float(oos_stats["profitFactor"] or 0) >= min_oos_profit_factor
        )
        surviving_cases += int(survives)
        cases.append({
            "costPointsRoundTrip": cost_points,
            "aggregateStats": aggregate_stats,
            "trainStats": train_stats,
            "oosStats": oos_stats,
            "survives": survives,
        })

    if surviving_cases < len(cases):
        blockers.append("not-all-cost-cases-survive-oos-contract")
    if not cases:
        blockers.append("no-cost-cases-evaluated")
    return {
        "command": "futures-nq-historical-session-cost-stress",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "sourceReplayDecision": replay.get("decision"),
        "source": replay.get("source"),
        "costPointsCases": cost_points_cases,
        "survivingCaseCount": surviving_cases,
        "caseCount": len(cases),
        "cases": cases,
        "blockers": sorted(set(blockers)),
        "decision": "research-only-historical-session-cost-stress-watch" if not blockers else "research-only-historical-session-cost-stress-blocked",
        "hardRules": [
            "Cost-stress watch is not demo approval.",
            "Do not lower cost cases after seeing results.",
            "Current broker/local parity and execution-grade realtime data still gate demo expansion.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Futures NQ Historical Session Cost Stress - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only cost/slippage stress. This page does not approve Topstep demo or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Surviving cases: `{payload.get('survivingCaseCount')}/{payload.get('caseCount')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Cases",
        "",
    ]
    for case in payload.get("cases") or []:
        lines.append(
            f"- `{case.get('costPointsRoundTrip')}` points: survives `{case.get('survives')}`, "
            f"OOS `{case.get('oosStats')}`"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stress NQ historical session replay under wider costs.")
    parser.add_argument("--replay", default=str(REPLAY))
    parser.add_argument("--cost-points", default="2,3,4,6")
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    args = parser.parse_args()
    cases = [float(item.strip()) for item in args.cost_points.split(",") if item.strip()]
    payload = build_cost_stress(replay=read_json(Path(args.replay)), cost_points_cases=cases)
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
