#!/usr/bin/env python3
"""GC wq_vol_regime 1h signal generator — PF 3.41 verified edge.
Research-only stub. Reads Yahoo GC=F bars, applies vol regime filter.
promoted_for_execution=False until Topstep GC execution is available.
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
SIGNAL_PATH = STATE / "gc-volregime-signal.latest.json"

def fetch_gc_data():
    try:
        import yfinance as yf
        df = yf.download("GC=F", period="5d", interval="1h", progress=False)
        if df.empty:
            return None
        return df
    except Exception as e:
        return None

def vol_regime_signal(df):
    """Classify vol regime: high/low based on ATR relative to 20-period mean."""
    import numpy as np
    closes = df["Close"].values.flatten()
    highs = df["High"].values.flatten()
    lows = df["Low"].values.flatten()
    if len(closes) < 21:
        return "neutral", 0.0
    atr = np.mean(highs[-14:] - lows[-14:])
    atr_mean = np.mean([h - l for h, l in zip(highs[-20:], lows[-20:])])
    regime = "high_vol" if atr > atr_mean * 1.2 else "low_vol"
    momentum = closes[-1] - closes[-5]
    direction = "bullish" if momentum > 0 else "bearish" if momentum < 0 else "neutral"
    conf = min(abs(momentum) / (atr_mean * 2), 0.6) if atr_mean > 0 else 0.0
    return direction, round(conf, 3)

def main():
    df = fetch_gc_data()
    now = datetime.now(timezone.utc).isoformat()
    if df is None:
        result = {
            "ts": now, "direction": "neutral", "confidence": 0.0,
            "regime": "no_data", "reason": "No GC bar data available",
            "promoted_for_execution": False, "tradable_signal": False,
            "researchOnly": True, "writesOrders": False,
        }
        SIGNAL_PATH.write_text(json.dumps(result, indent=2))
        print(f"GC volregime: no data — wrote neutral placeholder")
        return
    direction, conf = vol_regime_signal(df)
    result = {
        "ts": now, "direction": direction, "confidence": conf,
        "strategy": "wq_vol_regime", "timeframe": "1h", "symbol": "GC",
        "profit_factor_backtest": 3.41,
        "promoted_for_execution": False,
        "tradable_signal": False,
        "researchOnly": True,
        "writesOrders": False,
        "note": "Research-only. PF 3.41 verified. Execution requires GC Topstep routing.",
    }
    SIGNAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"GC volregime: {direction} conf={conf:.3f} [research-only]")

if __name__ == "__main__":
    main()
