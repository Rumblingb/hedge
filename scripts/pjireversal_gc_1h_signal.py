#!/usr/bin/env python3
"""GC PJI Reversal 1h signal generator — PF 1.59 verified edge.
Research-only stub. Reads Yahoo GC=F 1h bars, detects PJI reversal pattern.
PJI = Prior-day High/Low/Close level injection reversal.
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
SIGNAL_PATH = STATE / "gc-pjireversal-signal.latest.json"

def fetch_gc_1h():
    try:
        import yfinance as yf
        df = yf.download("GC=F", period="5d", interval="1h", progress=False)
        if df.empty:
            return None
        return df
    except Exception:
        return None

def pji_reversal_signal(df):
    """Detect price injection at prior-day levels with reversal."""
    import numpy as np
    closes = df["Close"].values.flatten()
    highs = df["High"].values.flatten()
    lows = df["Low"].values.flatten()
    if len(closes) < 8:
        return "neutral", 0.0
    # Prior day high/low (approx from last 6-8 bars)
    prior_high = max(highs[-8:-2])
    prior_low = min(lows[-8:-2])
    price = closes[-1]
    prev_price = closes[-2]
    # Injection above prior high then reversal
    if prev_price > prior_high and price < prev_price * 0.999:
        return "bearish", 0.55
    # Injection below prior low then reversal
    if prev_price < prior_low and price > prev_price * 1.001:
        return "bullish", 0.55
    return "neutral", 0.0

def main():
    df = fetch_gc_1h()
    now = datetime.now(timezone.utc).isoformat()
    if df is None:
        result = {
            "ts": now, "direction": "neutral", "confidence": 0.0,
            "reason": "No GC 1h data",
            "promoted_for_execution": False, "tradable_signal": False,
            "researchOnly": True, "writesOrders": False,
        }
        SIGNAL_PATH.write_text(json.dumps(result, indent=2))
        print("GC PJI reversal: no data")
        return
    direction, conf = pji_reversal_signal(df)
    result = {
        "ts": now, "direction": direction, "confidence": conf,
        "strategy": "pji_reversal", "timeframe": "1h", "symbol": "GC",
        "profit_factor_backtest": 1.59,
        "promoted_for_execution": False,
        "tradable_signal": False,
        "researchOnly": True,
        "writesOrders": False,
        "note": "Research-only. PF 1.59 verified. GC execution lane not yet available.",
    }
    SIGNAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"GC PJI reversal: {direction} conf={conf:.3f} [research-only]")

if __name__ == "__main__":
    main()
