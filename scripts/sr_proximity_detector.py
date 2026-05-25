#!/usr/bin/env python3
"""
S/R Proximity Detector — Support & Resistance Zone Signal
===========================================================
Port of the sagarrathi/AlgoTrading ReversalAction strategy concept.

Identifies price approaching known S/R levels and generates 
reversal or breakout signals based on:
- Distance from S/R (tolerance factor)
- Short-term trend (EMA-50)
- Long-term trend (EMA-200)
- Volume confirmation
- Bar range confirmation

Output: ~/.rumbling-hedge/state/sr-proximity-signal.latest.json
"""

import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple

STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "sr-proximity-signal.latest.json"

DATA_DIR = Path("/Users/brain/hedge/data")

# Default S/R levels for NQ (auto-computed from recent price action)
# In production, compute dynamically from historical pivots
DEFAULT_SR_LEVELS = {
    "NQ": {
        "support": [],  # auto-computed
        "resistance": []  # auto-computed
    }
}

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")

def load_data(symbol: str = "NQ", timeframe: str = "60m") -> Optional[pd.DataFrame]:
    """Load OHLCV data for S/R analysis"""
    patterns = [
        DATA_DIR / f"free/NQ-{timeframe}-60d.csv",
        DATA_DIR / f"free/NQ-{timeframe}-30d.csv",
        DATA_DIR / f"free/{symbol}-{timeframe}-60d.csv",
    ]
    for p in patterns:
        if p.exists():
            df = pd.read_csv(p)
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
            return df
    return None

def compute_sr_levels(df: pd.DataFrame, lookback: int = 100) -> Dict:
    """
    Compute S/R levels using pivot highs/lows.
    Port of swing high/low detection used by professional traders.
    """
    if df is None or len(df) < lookback:
        return {"support": [], "resistance": []}
    
    recent = df.tail(lookback).copy()
    highs = recent["high"].values
    lows = recent["low"].values
    closes = recent["close"].values
    
    # Simple pivot detection: look for local extrema
    pivot_highs = []
    pivot_lows = []
    
    for i in range(2, len(highs) - 2):
        # Pivot high: high[i] is higher than 2 bars on each side
        if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and 
            highs[i] > highs[i+1] and highs[i] > highs[i+2]):
            pivot_highs.append(highs[i])
        
        # Pivot low: low[i] is lower than 2 bars on each side
        if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and 
            lows[i] < lows[i+1] and lows[i] < lows[i+2]):
            pivot_lows.append(lows[i])
    
    if not pivot_highs or not pivot_lows:
        # Fallback: use percentile-based levels
        return {
            "support": [float(np.percentile(lows, 20)), float(np.percentile(lows, 10))],
            "resistance": [float(np.percentile(highs, 80)), float(np.percentile(highs, 90))],
        }
    
    # Cluster nearby levels (within 0.3%)
    def cluster_levels(values, threshold_pct=0.3):
        if not values:
            return []
        values = sorted(values)
        clusters = [[values[0]]]
        for v in values[1:]:
            if abs(v - clusters[-1][0]) / clusters[-1][0] * 100 < threshold_pct:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return [float(np.mean(c)) for c in clusters]
    
    return {
        "support": cluster_levels(pivot_lows),
        "resistance": cluster_levels(pivot_highs),
    }

def compute_ema(values, period: int) -> float:
    """Compute EMA at the current bar"""
    if len(values) < period:
        return values[-1] if len(values) > 0 else 0
    arr = pd.Series(values)
    ema = arr.ewm(span=period, adjust=False).mean().iloc[-1]
    return float(ema)

def tolerance_proximity(price: float, levels: List[float], 
                        tol_factor: float = 0.3) -> Tuple[bool, Optional[float]]:
    """
    Check if price is within tolerance of any S/R level.
    Returns (is_near, nearest_level)
    """
    if not levels:
        return False, None
    
    pcts = [abs(price - lvl) / price * 100 for lvl in levels]
    min_idx = np.argmin(pcts)
    
    if pcts[min_idx] <= tol_factor:
        return True, levels[min_idx]
    return False, None

def run_analysis(symbol: str = "NQ", timeframe: str = "60m") -> Dict:
    """Run the S/R proximity detector"""
    log(f"S/R Proximity Detector — {symbol} {timeframe}")
    
    # 1. Load data
    df = load_data(symbol, timeframe)
    if df is None:
        log(f"❌ No data found for {symbol} {timeframe}")
        return None
    
    log(f"Loaded {len(df)} bars")
    
    # 2. Compute S/R levels
    sr_levels = compute_sr_levels(df)
    supports = sr_levels["support"]
    resistances = sr_levels["resistance"]
    log(f"Support levels: {[f'{lvl:,.1f}' for lvl in supports]}")
    log(f"Resistance levels: {[f'{lvl:,.1f}' for lvl in resistances]}")
    
    # 3. Current bar data
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    close = float(last["close"])
    high = float(last["high"])
    low = float(last["low"])
    open_p = float(last["open"])
    volume = float(last.get("volume", 0))
    
    prev_close = float(prev["close"])
    prev_open = float(prev["open"])
    prev_volume = float(prev.get("volume", 0))
    
    # 4. EMAs
    closes = df["close"].values
    ema_short = compute_ema(closes, 50)
    ema_long = compute_ema(closes, 200)
    
    bar_mid = (high + low) / 2
    long_trend = "up" if bar_mid > ema_long else "down"
    short_trend = "up" if bar_mid > ema_short else "down"
    
    # 5. Volume confirmation
    volume_support = volume > prev_volume
    
    # 6. Bar range confirmation (current bar bigger than previous)
    bar_range = abs(close - open_p)
    prev_bar_range = abs(prev_close - prev_open)
    bar_range_support = bar_range > prev_bar_range
    
    # 7. Candle color
    bar_green = close > open_p
    prev_green = prev_close > prev_open
    trend_change = ""
    if volume_support and bar_range_support:
        if prev_green and not bar_green:
            trend_change = "bullish_to_bearish"
        elif not prev_green and bar_green:
            trend_change = "bearish_to_bullish"
        elif prev_green and bar_green:
            trend_change = "bullish_continuation"
        else:
            trend_change = "bearish_continuation"
    
    # 8. Check proximity to S/R levels
    tol_factor = 0.3  # 0.3% tolerance
    
    # For resistance: check if high is near resistance (breakout or rejection)
    near_resistance, nearest_res = tolerance_proximity(high, resistances, tol_factor)
    # For support: check if low is near support
    near_support, nearest_sup = tolerance_proximity(low, supports, tol_factor)
    # Also check close proximity for breakouts
    near_close_res, _ = tolerance_proximity(close, resistances, tol_factor * 0.5)
    near_close_sup, _ = tolerance_proximity(close, supports, tol_factor * 0.5)
    
    # 9. Generate signals
    signals = []
    confidence = 0.0
    
    # REVERSAL SIGNAL (sagarrathi pattern)
    if long_trend == "up" and short_trend == "down" and near_support:
        if trend_change == "bearish_to_bullish":
            signals.append({
                "type": "REVERSAL_LONG",
                "reason": f"Long↑ Short↓ near support {nearest_sup:,.1f} + bear→bull reversal",
                "sr_level": round(nearest_sup, 2),
            })
            confidence = max(confidence, 0.60)
    
    if long_trend == "down" and short_trend == "up" and near_resistance:
        if trend_change == "bullish_to_bearish":
            signals.append({
                "type": "REVERSAL_SHORT",
                "reason": f"Long↓ Short↑ near resistance {nearest_res:,.1f} + bull→bear reversal",
                "sr_level": round(nearest_res, 2),
            })
            confidence = max(confidence, 0.60)
    
    # BREAKOUT SIGNAL (sagarrathi pattern)
    if long_trend == "up" and short_trend == "up" and near_resistance:
        if trend_change == "bullish_continuation" and near_close_res:
            signals.append({
                "type": "BREAKOUT_LONG",
                "reason": f"Long↑ Short↑ breaking resistance {nearest_res:,.1f}",
                "sr_level": round(nearest_res, 2),
            })
            confidence = max(confidence, 0.55)
    
    if long_trend == "down" and short_trend == "down" and near_support:
        if trend_change == "bearish_continuation" and near_close_sup:
            signals.append({
                "type": "BREAKOUT_SHORT",
                "reason": f"Long↓ Short↓ breaking support {nearest_sup:,.1f}",
                "sr_level": round(nearest_sup, 2),
            })
            confidence = max(confidence, 0.55)
    
    # BOUNCE SIGNAL (price bounced off S/R within the bar)
    if not signals:
        # Price touched S/R and reversed within the bar
        body = abs(close - open_p)
        upper_wick = high - max(close, open_p)
        lower_wick = min(close, open_p) - low
        
        if near_resistance and upper_wick > body * 1.5 and close < nearest_res:
            signals.append({
                "type": "BOUNCE_SHORT",
                "reason": f"Rejected at resistance {nearest_res:,.1f} with long upper wick",
                "sr_level": round(nearest_res, 2),
            })
            confidence = max(confidence, 0.50)
        
        if near_support and lower_wick > body * 1.5 and close > nearest_sup:
            signals.append({
                "type": "BOUNCE_LONG",
                "reason": f"Bounced off support {nearest_sup:,.1f} with long lower wick",
                "sr_level": round(nearest_sup, 2),
            })
            confidence = max(confidence, 0.50)
    
    # 10. Build output
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "price": {
            "close": round(close, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "open": round(open_p, 2),
        },
        "trends": {
            "long": long_trend,
            "short": short_trend,
            "ema_50": round(ema_short, 2),
            "ema_200": round(ema_long, 2),
        },
        "sr_levels": {
            "support": [round(s, 2) for s in supports],
            "resistance": [round(r, 2) for r in resistances],
        },
        "proximity": {
            "near_support": near_support,
            "near_resistance": near_resistance,
            "nearest_support": round(nearest_sup, 2) if near_support else None,
            "nearest_resistance": round(nearest_res, 2) if near_resistance else None,
        },
        "confirmation": {
            "volume": bool(volume_support),
            "bar_range": bool(bar_range_support),
            "trend_change": trend_change,
        },
        "signals": signals,
        "max_confidence": round(confidence, 3),
        "action": "HOLD",
        "direction": "neutral",
        "source": "sr-proximity-sagarrathi-port",
    }
    
    # Determine overall action
    if signals:
        best_signal = max(signals, key=lambda s: 
                         0 if "LONG" in s["type"] or "BOUNCE_LONG" in s["type"] 
                         else 1)
        output["action"] = "ENTER" if confidence >= 0.50 else "MONITOR"
        output["direction"] = "long" if any("LONG" in s["type"] for s in signals) else "short"
        
        if confidence >= 0.55:
            output["action"] = "ENTRY_CONFIRMED"
    
    with open(STATE_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    log(f"✅ Written to {STATE_FILE}")
    log(f"  → Signals: {len(signals)}")
    for s in signals:
        log(f"    {s['type']}: {s['reason']}")
    log(f"  → Confidence: {confidence:.2f}")
    log(f"  → Action: {output['action']}")
    
    return output

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "60m"
    run_analysis(symbol, timeframe)
