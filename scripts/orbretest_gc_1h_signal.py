#!/usr/bin/env python3
"""GC ORB Retest 1h signal generator — HEURISTIC STUB.

AI Scientist verified PF 2.398 for orb_retest with conf=5 (GC 1h, conf_bars=5).
Artifact: Agent-Hermes/ai-scientist-p3-orb-retest-2026-06-08.md
Strategy: breakout of first 2 bars, wait conf_bars for price to hold above/below,
then enter. 3/3 positive WF folds, 5/5 shuffle seeds positive.

THIS implementation is NOT a replication — different logic, wrong data source.
GC Topstep bars not yet in archive — exits non-zero until available.
promoted_for_execution=False always.
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
BAR_ARCHIVE = ROOT / ".rumbling-hedge/research/topstep-readonly-bars"
SIGNAL_PATH = STATE / "gc-orbretest-signal.latest.json"
GC_CSV = BAR_ARCHIVE / "GC-1m-topstep-readonly.csv"


def load_gc_1h():
    if not GC_CSV.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_csv(GC_CSV, parse_dates=["ts"]).sort_values("ts")
        h1 = df.set_index("ts")[["open","high","low","close","volume"]].resample("1h").agg(
            {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
        ).dropna()
        return h1 if len(h1) >= 10 else None
    except Exception:
        return None


def main():
    now = datetime.now(timezone.utc).isoformat()
    h1 = load_gc_1h()

    if h1 is None:
        print("GC orbretest: no GC Topstep bars — exiting without writing signal", file=sys.stderr)
        sys.exit(1)

    closes = h1["close"].values
    highs = h1["high"].values
    lows = h1["low"].values
    CONF_BARS = 5
    if len(closes) < CONF_BARS + 2:
        print("GC orbretest: insufficient bars", file=sys.stderr)
        sys.exit(1)

    orb_high = max(highs[:2])
    orb_low = min(lows[:2])
    price = closes[-1]
    bars_above = sum(1 for c in closes[2:] if c > orb_high)
    bars_below = sum(1 for c in closes[2:] if c < orb_low)

    if bars_above >= CONF_BARS and price > orb_high:
        direction, conf = "bullish", 0.6
    elif bars_below >= CONF_BARS and price < orb_low:
        direction, conf = "bearish", 0.6
    else:
        direction, conf = "neutral", 0.0

    result = {
        "ts": now, "direction": direction, "confidence": conf,
        "strategy": "orb_retest_stub", "timeframe": "1h", "symbol": "GC",
        "confirmation_level": CONF_BARS,
        "implementation_status": "HEURISTIC_STUB",
        "claimed_edge_source": "Agent-Hermes/ai-scientist-p3-orb-retest-2026-06-08.md",
        "claimed_edge_pf": 2.398, "verified": False,
        "promoted_for_execution": False, "tradable_signal": False,
        "researchOnly": True, "writesOrders": False,
        "note": "STUB: not a replication of AI Scientist orb_retest. 2.398 PF is AI Scientist claim, not this implementation.",
    }
    SIGNAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"GC orbretest stub: {direction} conf={conf:.2f} [HEURISTIC_STUB]")


if __name__ == "__main__":
    main()
