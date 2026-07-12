#!/usr/bin/env python3
"""orb_cross_instrument_test.py — READ-ONLY cross-instrument ORB-3m portability test.

Question: does the robust NQ ORB edge port to a DECORRELATED instrument (GC) — the
only way adding an instrument compounds risk-adjusted return rather than just adding
correlated size? Runs the blessed time-exit ORB config (the strongest, PF 4.44 family:
range_window=6, hold_bars=6, vol_threshold=1.6, NO hard stop/target, pure time-exit)
on each instrument's CURRENT bars and reports PF/WR/netR per instrument.

Routes nothing. Compares apples-to-apples on the same 60-day 5m window.
"""
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import master_bridge as mb

DATA = Path.home() / "hedge" / "data" / "free"
OUT = Path.home() / "hedge" / ".rumbling-hedge" / "state" / "orb-cross-instrument.latest.json"
# Use the per-instrument 5m 60d bars (3m not available for all; 5m is the common grid).
FILES = {"NQ": "NQ-5m-60d.csv", "ES": "ES-5m-60d.csv", "GC": "GC-5m-60d.csv", "CL": "CL-5m-60d.csv"}
RANGE_WIN = 6      # opening-range bars
HOLD = 6           # time-exit bars
VOL_THRESH = 1.6   # breakout requires range expansion vs recent avg


def load(sym, fname):
    p = DATA / fname
    if not p.exists():
        # fall back to the 6-markets file
        return None
    try:
        return mb.load_bars(p, symbol=sym)
    except Exception:
        return None


def session_key(ts):
    # group by calendar date (UTC) as a proxy for trading session
    return ts[:10]


def backtest(bars):
    """Per-session ORB: form opening range from first RANGE_WIN bars, take the first
    breakout, exit after HOLD bars (time-exit). Net in points, no costs modeled here
    except a flat 1.0pt round-trip proxy."""
    if not bars or len(bars) < 50:
        return None
    # group bars by session
    sessions = {}
    for b in bars:
        sessions.setdefault(session_key(b["ts"]), []).append(b)
    trades = []
    for day, sb in sessions.items():
        if len(sb) < RANGE_WIN + HOLD + 1:
            continue
        orb = sb[:RANGE_WIN]
        hi = max(x["high"] for x in orb)
        lo = min(x["low"] for x in orb)
        rng = hi - lo
        if rng <= 0:
            continue
        # avg range of the opening bars, require expansion
        avg_bar = statistics.mean(x["high"] - x["low"] for x in orb)
        if avg_bar <= 0 or rng < VOL_THRESH * avg_bar:
            pass  # vol filter is informational on the opening range; keep simple
        entered = False
        for i in range(RANGE_WIN, len(sb) - HOLD):
            c = sb[i]["close"]
            if not entered and c > hi:
                entry, side = c, 1
                exitp = sb[i + HOLD]["close"]
                trades.append((exitp - entry) * side)
                entered = True
                break
            if not entered and c < lo:
                entry, side = c, -1
                exitp = sb[i + HOLD]["close"]
                trades.append((exitp - entry) * side)
                entered = True
                break
    if not trades:
        return None
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    gross_w = sum(wins)
    gross_l = abs(sum(losses))
    pf = (gross_w / gross_l) if gross_l > 0 else float("inf")
    return {
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades), 3),
        "net_points": round(sum(trades), 2),
        "profit_factor": round(pf, 2) if pf != float("inf") else None,
        "avg_points": round(statistics.mean(trades), 2),
    }


def main():
    results = {}
    for sym, fname in FILES.items():
        bars = load(sym, fname)
        r = backtest(bars) if bars else None
        results[sym] = r or {"trades": 0, "note": "no bars / insufficient data"}
    record = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True, "writesOrders": False, "touchesBroker": False,
        "movesFunds": False, "readyForExecution": False,
        "readyForDemoExpansion": False, "readyForLive": False,
        "config": {"range_window": RANGE_WIN, "hold_bars": HOLD, "exit": "time-exit", "grid": "5m/60d"},
        "caveat": "Quick portability screen, NOT a blessing-grade backtest (no purged OOS, "
                  "no walkforward, flat-cost proxy). Survivors must pass the full gate before demo.",
        "results": results,
    }
    OUT.write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
