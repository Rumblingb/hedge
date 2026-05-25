#!/usr/bin/env python3
"""
Heiken Ashi Agent — Smoothed Trend Detection + Candle Confirmation
Transforms standard OHLCV into Heiken Ashi candles.
Used as confirmation gate: long trade only if HA bar is green.
"""
import json, os
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

HOME = os.environ.get("HOME", "/Users/brain")
STATE_DIR = Path(HOME) / ".rumbling-hedge" / "state"
DATA_DIR = Path(HOME) / "hedge" / "data" / "free"

def load_bars(symbol, timeframe):
    for suffix in ["-60d.csv", "-21d.csv", "-5d.csv"]:
        p = DATA_DIR / f"{symbol}-{timeframe}{suffix}"
        if p.exists():
            df = pd.read_csv(p)
            if "ts" in df.columns and "time" not in df.columns:
                df = df.rename(columns={"ts": "time"})
            df["time"] = pd.to_datetime(df["time"])
            return df.sort_values("time")
    return None

def heiken_ashi(df):
    if df is None or len(df) < 3:
        return None
    ha = df.copy()
    ha["ha_close"] = (ha["open"] + ha["high"] + ha["low"] + ha["close"]) / 4
    ha_open = [float(ha["open"].iloc[0])]
    for i in range(1, len(ha)):
        ha_open.append((ha_open[i-1] + float(ha["ha_close"].iloc[i-1])) / 2)
    ha["ha_open"] = ha_open
    cols = ["high", "ha_open", "ha_close"]
    ha["ha_high"] = ha[cols].max(axis=1)
    cols2 = ["low", "ha_open", "ha_close"]
    ha["ha_low"] = ha[cols2].min(axis=1)
    ha["ha_bullish"] = ha["ha_close"] > ha["ha_open"]
    ha["ha_flip_up"] = (~ha["ha_bullish"].shift(1).fillna(False)) & ha["ha_bullish"]
    ha["ha_flip_down"] = ha["ha_bullish"].shift(1).fillna(False) & (~ha["ha_bullish"])
    return ha

def compute_signal(ha):
    if ha is None or len(ha) < 5:
        return {"trend": "neutral", "color": "unknown", "flip": False}
    last = ha.iloc[-1]
    recent = ha.tail(5)
    bullish_bars = int(recent["ha_bullish"].sum())
    if bullish_bars >= 4:
        trend = "bullish"
    elif bullish_bars <= 1:
        trend = "bearish"
    else:
        trend = "neutral"
    color = "green" if last["ha_bullish"] else "red"
    return {
        "trend": trend,
        "color": color,
        "flip": bool(last.get("ha_flip_up", False) or last.get("ha_flip_down", False)),
        "flip_up": bool(last.get("ha_flip_up", False)),
        "flip_down": bool(last.get("ha_flip_down", False)),
        "close": round(float(last.get("close", 0)), 2),
        "ha_close": round(float(last.get("ha_close", 0)), 2),
        "ha_open": round(float(last.get("ha_open", 0)), 2),
    }

def main():
    results = {}
    for symbol in ["NQ", "ES"]:
        df = load_bars(symbol, "60m")
        ha = heiken_ashi(df)
        signal = compute_signal(ha)
        results[symbol] = signal
        print(f"{symbol}: {signal['trend']} (color={signal['color']}, flip={signal['flip']})")
    results["generated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = STATE_DIR / "heiken-ashi-signal.latest.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"OK Written to {out}")

if __name__ == "__main__":
    main()
