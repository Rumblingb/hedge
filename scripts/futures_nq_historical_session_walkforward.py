#!/usr/bin/env python3
"""Research-only walk-forward robustness audit for NQ session replay."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
REPLAY = STATE / "futures-nq-historical-session-replay.latest.json"
OUT = STATE / "futures-nq-historical-session-walkforward.latest.json"
VAULT = Path.home() / "Documents/memorybrain"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"futures-nq-historical-session-walkforward-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    net = [float(item.get("netR") or 0) for item in trades]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trades": len(trades),
        "netR": round(sum(net), 6),
        "avgR": round(sum(net) / len(net), 6) if net else None,
        "winRate": round(len(wins) / len(net), 6) if net else None,
        "profitFactor": round(gross_win / gross_loss, 6) if gross_loss else (999.0 if gross_win else None),
        "wins": len(wins),
        "losses": len(losses),
    }


def build_walkforward(
    *,
    replay: dict[str, Any],
    fold_size: int = 10,
    min_folds: int = 4,
    min_positive_fold_share: float = 0.6,
    min_profit_factor: float = 1.2,
    max_worst_fold_r: float = -3.0,
) -> dict[str, Any]:
    trades = replay.get("trades") if isinstance(replay.get("trades"), list) else []
    trades = [trade for trade in trades if isinstance(trade, dict)]
    blockers: list[str] = []
    if replay.get("decision") != "research-only-historical-session-replay-watch":
        blockers.append("source-replay-not-watch")
    if len(trades) < fold_size * min_folds:
        blockers.append("too-few-trades-for-walkforward-folds")

    folds: list[dict[str, Any]] = []
    for idx, start in enumerate(range(0, len(trades), fold_size)):
        fold_trades = trades[start:start + fold_size]
        if len(fold_trades) < fold_size:
            continue
        fold_stats = stats(fold_trades)
        folds.append({
            "fold": idx + 1,
            "startDate": fold_trades[0].get("date"),
            "endDate": fold_trades[-1].get("date"),
            "stats": fold_stats,
            "positive": float(fold_stats["netR"]) > 0,
        })

    aggregate = stats(trades)
    positive_folds = sum(1 for fold in folds if fold.get("positive"))
    positive_share = round(positive_folds / len(folds), 6) if folds else 0.0
    worst_fold = min((float((fold.get("stats") or {}).get("netR") or 0) for fold in folds), default=0.0)
    if len(folds) < min_folds:
        blockers.append("too-few-complete-walkforward-folds")
    if positive_share < min_positive_fold_share:
        blockers.append("positive-fold-share-below-contract")
    if (aggregate.get("profitFactor") or 0) < min_profit_factor:
        blockers.append("aggregate-profit-factor-below-contract")
    if worst_fold < max_worst_fold_r:
        blockers.append("worst-fold-drawdown-below-contract")

    return {
        "command": "futures-nq-historical-session-walkforward",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "sourceReplayDecision": replay.get("decision"),
        "source": replay.get("source"),
        "foldSize": fold_size,
        "foldCount": len(folds),
        "positiveFoldCount": positive_folds,
        "positiveFoldShare": positive_share,
        "worstFoldNetR": round(worst_fold, 6),
        "aggregateStats": aggregate,
        "folds": folds,
        "blockers": sorted(set(blockers)),
        "decision": "research-only-historical-session-walkforward-blocked" if blockers else "research-only-historical-session-walkforward-watch",
        "hardRules": [
            "Walk-forward watch is not demo approval.",
            "Do not tune fold size after seeing this result without recording a new one-variable test.",
            "Current data parity, realtime data, cost/slippage, and promotion gates still control demo expansion.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Futures NQ Historical Session Walkforward - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only robustness audit. This page does not approve Topstep demo or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Fold count: `{payload.get('foldCount')}`",
        f"- Positive fold share: `{payload.get('positiveFoldShare')}`",
        f"- Worst fold netR: `{payload.get('worstFoldNetR')}`",
        f"- Aggregate: `{payload.get('aggregateStats')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Hard Rules",
        "",
    ]
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit NQ historical session replay robustness.")
    parser.add_argument("--replay", default=str(REPLAY))
    parser.add_argument("--fold-size", type=int, default=10)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    args = parser.parse_args()
    payload = build_walkforward(replay=read_json(Path(args.replay)), fold_size=args.fold_size)
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
