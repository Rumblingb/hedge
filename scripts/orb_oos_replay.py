#!/usr/bin/env python3
"""Research-only OOS replay artifact for the verified NQ ORB 3m edge.

Converts the AI Scientist post-fix walkforward folds
(run_n4_vt1.6_postfix/final_info.json) into the vol-regime-oos-replay
schema consumed by futures_cost_slippage_gate.py, so the cost/slippage
gate can stress the verified edge instead of only the dead
wq-vol-regime-60m artifact.

R definition: stopPoints per fold = average losing-trade magnitude in
points derived from fold PF and net (gross_loss = net / (PF - 1)).
This is conservative for a hold-bar-exit strategy with no hard stop.

Never routes, sizes, or submits orders.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
SOURCE = ROOT / "ai-scientist-templates/financial_strategy/run_n4_vt1.6_postfix/final_info.json"
OUTPUT = STATE / "vol-regime-oos-replay.orb3m.latest.json"


def fold_stop_points(oos: dict) -> float:
    pf = float(oos.get("profit_factor") or 0)
    net = float(oos.get("total_net_points") or 0)
    n = int(oos.get("trade_count") or 0)
    wr = float(oos.get("win_rate") or 0)
    losses = max(1, round(n * (1 - wr)))
    if pf <= 1 or net <= 0:
        return 16.0  # fallback proxy
    gross_loss = net / (pf - 1)
    return max(4.0, gross_loss / losses)


def main() -> None:
    info = json.loads(SOURCE.read_text())
    tmpl = info["AlphaStrategyTemplate"]
    folds = tmpl["experiment"]["walkforward_folds"]
    args_used = info.get("args", {})

    windows = []
    total_trades = 0
    total_net_r = 0.0
    for f in folds:
        oos = f.get("oos") or {}
        n = int(oos.get("trade_count") or 0)
        if n <= 0:
            continue
        stop = fold_stop_points(oos)
        net_points = float(oos.get("total_net_points") or 0)
        avg_points = float(oos.get("avg_net_points") or 0)
        net_r = net_points / stop
        avg_r = avg_points / stop
        dr = oos.get("date_range") or {}
        total_trades += n
        total_net_r += net_r
        windows.append({
            "window": f.get("fold"),
            "testStart": dr.get("start"),
            "testEnd": dr.get("end"),
            "test": {"trades": n, "avgR": round(avg_r, 4), "netR": round(net_r, 4)},
            "selected": {"stopPoints": round(stop, 2)},
            "sourceFoldMetrics": {
                "profitFactor": oos.get("profit_factor"),
                "winRate": oos.get("win_rate"),
                "netPoints": net_points,
                "maxDrawdownPoints": oos.get("max_drawdown_points"),
            },
        })

    artifact = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "command": "orb-oos-replay",
        "status": "oos-replay-from-verified-walkforward",
        "strategy": "nq-orb-3m-vt16",
        "signalMode": "normal",
        "sourceArtifact": str(SOURCE),
        "sourceArgs": {k: args_used.get(k) for k in (
            "strategy", "symbol", "timeframe", "range_window_bars", "hold_bars",
            "volume_threshold", "rth_only") if k in args_used},
        "rDefinition": "stopPoints = avg losing-trade points per fold (gross_loss/(n_losses)); conservative proxy for hold-bar exits",
        "aggregateOos": {
            "trades": total_trades,
            "netR": round(total_net_r, 4),
            "avgR": round(total_net_r / total_trades, 4) if total_trades else 0.0,
            "profitFactor": tmpl["means"].get("oos_profit_factor"),
        },
        "windows": windows,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }
    tmp = OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(artifact, indent=2))
    tmp.replace(OUTPUT)
    print(f"wrote {OUTPUT}: {len(windows)} windows, {total_trades} trades, netR {artifact['aggregateOos']['netR']}")


if __name__ == "__main__":
    main()
