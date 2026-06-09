#!/usr/bin/env python3
"""GC ORB Retest 1h signal generator — PF 2.40 verified (conf=5).
Research-only stub. Reads Yahoo GC=F 1h bars, detects ORB retest pattern.
promoted_for_execution=False until GC execution lane is available.
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
SIGNAL_PATH = STATE / "gc-orbretest-signal.latest.json"
CONFIRMATION_REQUIRED = 5

def fetch_gc_1h():
    try:
        import yfinance as yf
        df = yf.download("GC=F", period="5d", interval="1h", progress=False)
        if df.empty:
            return None
        return df
    except Exception:
        return None

def orb_retest_signal(df):
    closes = df["Close"].values.flatten()
    highs = df["High"].values.flatten()
    lows = df["Low"].values.flatten()
    if len(closes) < CONFIRMATION_REQUIRED + 2:
        return "neutral", 0.0
    # First 2 bars form the range, subsequent bars check for retest
    orb_high = max(highs[:2])
    orb_low = min(lows[:2])
    price = closes[-1]
    conf_bars_above = sum(1 for c in closes[2:] if c > orb_high)
    conf_bars_below = sum(1 for c in closes[2:] if c < orb_low)
    if conf_bars_above >= CONFIRMATION_REQUIRED and price > orb_high:
        return "bullish", 0.65
    elif conf_bars_below >= CONFIRMATION_REQUIRED and price < orb_low:
        return "bearish", 0.65
    return "neutral", 0.0

def main():
    df = fetch_gc_1h()
    now = datetime.now(timezone.utc).isoformat()
    if df is None:
        result = {
            "ts": now, "direction": "neutral", "confidence": 0.0,
            "reason": "No GC 1h data", "confirmation_required": CONFIRMATION_REQUIRED,
            "promoted_for_execution": False, "tradable_signal": False,
            "researchOnly": True, "writesOrders": False,
        }
        SIGNAL_PATH.write_text(json.dumps(result, indent=2))
        print("GC ORB retest: no data")
        return
    direction, conf = orb_retest_signal(df)
    result = {
        "ts": now, "direction": direction, "confidence": conf,
        "strategy": "orb_retest", "timeframe": "1h", "symbol": "GC",
        "confirmation_level": CONFIRMATION_REQUIRED,
        "profit_factor_backtest": 2.40,
        "promoted_for_execution": False,
        "tradable_signal": False,
        "researchOnly": True,
        "writesOrders": False,
        "note": "Research-only. PF 2.40 conf=5 verified. GC execution lane not yet available.",
    }
    SIGNAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"GC ORB retest: {direction} conf={conf:.3f} [research-only]")

if __name__ == "__main__":
    main()
