#!/usr/bin/env python3
"""
DOM Proxy from OHLCV — Order Flow Imbalance Estimation

We don't have a real DOM feed for NQ futures. This module approximates
order flow imbalance using OHLCV bar data, producing:

1. CLV (Close Location Value): Where close sits within the bar's range
   CLV = (Close - Low - (High - Close)) / (High - Low)  → range [-1, +1]
   Positive = buying pressure, Negative = selling pressure

2. Volume-weighted CLV: CLV * Volume → signed volume proxy
   Approximates cumulative delta from bar data

3. Divergence signal: When price makes new high but VWAP-CLV diverges →
   exhaustion signal (fade the move)

4. Hidden divergence: When cumulative delta fails to confirm price
   movement → highest conviction mean-reversion signal

Output: ~/.rumbling-hedge/state/dom-proxy-signal.latest.json
"""

import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────────────────
STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/state"))
STATE_FILE = STATE_DIR / "dom-proxy-signal.latest.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Lookback for cumulative delta normalization
DELTA_LOOKBACK = 50
# Thresholds for signal generation
DIVERGENCE_THRESHOLD = 2.0  # z-score
CLV_EXTREME = 0.7  # |CLV| > 0.7 = extreme buying/selling


def load_bars() -> pd.DataFrame:
    """Load recent NQ bar data from available CSVs."""
    data_dir = Path("/Users/brain/hedge/data/free")
    # Try 15m first (good balance of recency and reliability)
    for pattern in ["*15m*60d*", "*15m*5d*", "*60m*60d*"]:
        candidates = list(data_dir.glob(pattern))
        for c in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
            if "NQ" in c.name or "ALL" in c.name:
                df = pd.read_csv(c)
                if "symbol" in df.columns:
                    df = df[df["symbol"] == "NQ"] if "NQ" in df["symbol"].values else df
                df["ts"] = pd.to_datetime(df["ts"])
                df = df.sort_values("ts")
                if len(df) >= 30:
                    print(f"Loaded {len(df)} bars from {c.name}")
                    return df
    raise ValueError("No suitable data found")


def compute_clv(bar) -> float:
    """Close Location Value: where close sits within the bar."""
    hl = bar["high"] - bar["low"]
    if hl == 0:
        return 0.0
    return (bar["close"] - bar["low"] - (bar["high"] - bar["close"])) / hl


def compute_dom_proxy(bars: pd.DataFrame) -> dict:
    """Compute DOM proxy signals from OHLCV data."""
    df = bars.copy()
    
    # 1. CLV per bar
    df["clv"] = df.apply(compute_clv, axis=1)
    
    # 2. Signed volume proxy
    df["signed_vol"] = df["clv"] * df.get("volume", pd.Series(np.ones(len(df))))
    
    # 3. Cumulative delta (normalized)
    df["cum_delta"] = df["signed_vol"].cumsum()
    df["cum_delta_norm"] = (df["cum_delta"] - df["cum_delta"].rolling(DELTA_LOOKBACK).mean()) / \
                           df["cum_delta"].rolling(DELTA_LOOKBACK).std()
    
    # 4. Price position
    df["price_z"] = (df["close"] - df["close"].rolling(DELTA_LOOKBACK).mean()) / \
                    df["close"].rolling(DELTA_LOOKBACK).std()
    
    # 5. Divergence detection
    df["divergence"] = df["price_z"] - df["cum_delta_norm"]
    
    # 6. CLV extreme detection
    df["clv_extreme"] = df["clv"].abs() > CLV_EXTREME
    
    # Recent statistics (last 20 bars)
    recent = df.tail(20)
    
    # Current state
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Signal logic
    signals = []
    
    # Bullish divergences
    if current["price_z"] < -DIVERGENCE_THRESHOLD and current["cum_delta_norm"] > -DIVERGENCE_THRESHOLD:
        signals.append({
            "type": "bullish_divergence",
            "strength": abs(current["price_z"]) - abs(current["cum_delta_norm"]),
            "desc": "Price makes new low but delta doesn't confirm → buying exhaustion upward"
        })
    
    if current["divergence"] < -DIVERGENCE_THRESHOLD:
        signals.append({
            "type": "hidden_bullish",
            "strength": abs(current["divergence"]),
            "desc": "Hidden bullish divergence — delta improving relative to price"
        })
    
    # Bearish divergences
    if current["price_z"] > DIVERGENCE_THRESHOLD and current["cum_delta_norm"] < DIVERGENCE_THRESHOLD:
        signals.append({
            "type": "bearish_divergence",
            "strength": abs(current["price_z"]) - abs(current["cum_delta_norm"]),
            "desc": "Price makes new high but delta doesn't confirm → buying exhaustion, short"
        })
    
    if current["divergence"] > DIVERGENCE_THRESHOLD:
        signals.append({
            "type": "hidden_bearish",
            "strength": abs(current["divergence"]),
            "desc": "Hidden bearish divergence — delta weakening relative to price"
        })
    
    # CLV extreme (immediate flow imbalance)
    if current["clv_extreme"]:
        signals.append({
            "type": "bullish_clv_spike" if current["clv"] > 0 else "bearish_clv_spike",
            "strength": abs(current["clv"]),
            "desc": f"CLV={current['clv']:.3f} — extreme {'buying' if current['clv'] > 0 else 'selling'} pressure this bar"
        })
    
    # Compute overall bias
    bullish_count = sum(1 for s in signals if "bullish" in s["type"])
    bearish_count = sum(1 for s in signals if "bearish" in s["type"])
    total_strength = sum(s["strength"] for s in signals if "bullish" in s["type"]) - \
                     sum(s["strength"] for s in signals if "bearish" in s["type"])
    
    if total_strength > 1.0:
        direction = "bullish"
        confidence = min(total_strength / 3.0, 1.0)
    elif total_strength < -1.0:
        direction = "bearish"
        confidence = min(abs(total_strength) / 3.0, 1.0)
    else:
        direction = "neutral"
        confidence = 0.0
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "confidence": round(confidence, 4),
        "score": round(total_strength, 4),
        "current_clv": round(current["clv"], 4),
        "current_price_z": round(current["price_z"], 2),
        "current_delta_z": round(current["cum_delta_norm"], 2),
        "divergence": round(current["divergence"], 2),
        "signals": signals,
        "method": "OHLCV_DOM_proxy",
        "bar_count": len(df),
        "last_bar_time": str(current["ts"]),
    }


def main():
    print("📊 DOM Proxy from OHLCV — Order Flow Imbalance Estimator")
    print("=" * 55)
    
    try:
        bars = load_bars()
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    signal = compute_dom_proxy(bars)
    
    print(f"\nCurrent CLV: {signal['current_clv']:.4f}")
    print(f"Price z-score: {signal['current_price_z']:.2f}")
    print(f"Delta z-score: {signal['current_delta_z']:.2f}")
    print(f"Divergence: {signal['divergence']:.2f}")
    print(f"\nDirection: {signal['direction'].upper()}")
    print(f"Confidence: {signal['confidence']:.1%}")
    print(f"Active signals: {len(signal['signals'])}")
    
    for s in signal["signals"]:
        print(f"  • {s['type']:25s} (strength={s['strength']:.2f}) — {s['desc'][:60]}")
    
    with open(STATE_FILE, "w") as f:
        json.dump(signal, f, indent=2)
    
    print(f"\n✅ Written to {STATE_FILE}")
    print(f"  → Consumed by: strategy-fusion engine (pre-trade confirmation)")
    print(f"  → Bulls get: DOMPROXY=bullish.confirm, Bears get: DOMPROXY=bearish.confirm")


if __name__ == "__main__":
    main()
