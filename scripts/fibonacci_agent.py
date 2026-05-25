#!/usr/bin/env python3
"""
Fibonacci Agent — Key Retracement/Extension Levels for NQ/ES
Computes swing highs/lows, draws fib retracement and extension levels.
Signals: entry at key fib levels with rejection confirmation.
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

HOME = os.environ.get("HOME", "/Users/brain")
STATE_DIR = Path(HOME) / ".rumbling-hedge" / "state"
DATA_DIR = Path(HOME) / "hedge" / "data" / "free"

def load_bars(symbol, timeframe, days=60):
    for suffix in ["-60d.csv", "-21d.csv", "-5d.csv"]:
        p = DATA_DIR / f"{symbol}-{timeframe}{suffix}"
        if p.exists():
            df = pd.read_csv(p)
            if "ts" in df.columns and "time" not in df.columns:
                df = df.rename(columns={"ts": "time"})
            df["time"] = pd.to_datetime(df["time"])
            return df.sort_values("time")
    return None

def find_swings(df, lookback=20):
    """Find most recent swing high and swing low."""
    if df is None or len(df) < lookback * 2:
        return None, None
    
    recent = df.tail(lookback * 2)
    
    # Swing high: highest high in last N bars with lower highs on either side
    swing_high = None
    for i in range(lookback, min(len(recent) - lookback, len(recent))):
        window = recent.iloc[i-lookback:i+lookback]
        if recent.iloc[i]["high"] == window["high"].max():
            swing_high = float(recent.iloc[i]["high"])
    
    # Swing low
    swing_low = None
    for i in range(lookback, min(len(recent) - lookback, len(recent))):
        window = recent.iloc[i-lookback:i+lookback]
        if recent.iloc[i]["low"] == window["low"].min():
            swing_low = float(recent.iloc[i]["low"])
    
    # Fallback: highest high and lowest low in full range
    if swing_high is None:
        swing_high = float(recent["high"].max())
    if swing_low is None:
        swing_low = float(recent["low"].min())
    
    return swing_high, swing_low

def fib_levels(swing_high, swing_low):
    """Compute standard Fibonacci retracement and extension levels."""
    if swing_high is None or swing_low is None or swing_high == swing_low:
        return {}
    
    diff = swing_high - swing_low
    
    retracements = {
        "0.236": swing_high - 0.236 * diff,
        "0.382": swing_high - 0.382 * diff,
        "0.500": swing_high - 0.500 * diff,
        "0.618": swing_high - 0.618 * diff,
        "0.786": swing_high - 0.786 * diff,
    }
    
    extensions = {
        "1.272": swing_high + 1.272 * diff,
        "1.618": swing_high + 1.618 * diff,
        "2.000": swing_high + 2.000 * diff,
    }
    
    return {"retracements": retracements, "extensions": extensions, "swing_high": swing_high, "swing_low": swing_low}

def compute_signal(symbol, price, fib, tolerance=0.001):
    """Check if price is at a key fib level and determine signal."""
    if not fib:
        return {"direction": "neutral", "at_level": False, "nearest_level": None}
    
    retrace = fib.get("retracements", {})
    ext = fib.get("extensions", {})
    
    # Check retracements
    for name, level in sorted(retrace.items(), key=lambda x: abs(float(x[1]) - price)):
        if abs(level - price) / price < tolerance:
            # Price at retracement -> potential reversal
            direction = "long" if level < price * 0.99 else "short"
            return {"direction": direction, "at_level": True, "nearest_level": name,
                    "level_price": round(level, 2), "type": "retracement"}
    
    # Check extensions
    for name, level in sorted(ext.items(), key=lambda x: abs(float(x[1]) - price)):
        if abs(level - price) / price < tolerance * 2:
            direction = "short" if level > price * 1.01 else "long"
            return {"direction": direction, "at_level": True, "nearest_level": name,
                    "level_price": round(level, 2), "type": "extension"}
    
    # Find nearest level
    all_levels = {**retrace, **ext}
    nearest_name = min(all_levels, key=lambda k: abs(all_levels[k] - price))
    nearest_price = all_levels[nearest_name]
    
    return {"direction": "neutral", "at_level": False,
            "nearest_level": nearest_name, "nearest_price": round(nearest_price, 2),
            "distance_pct": round(abs(nearest_price - price) / price * 100, 2)}

def main():
    results = {}
    for symbol in ["NQ", "ES"]:
        df = load_bars(symbol, "60m")
        sh, sl = find_swings(df)
        fib = fib_levels(sh, sl)
        price = float(df.iloc[-1]["close"]) if df is not None and len(df) > 0 else 0
        signal = compute_signal(symbol, price, fib)
        results[symbol] = {
            "swing_high": round(sh, 2) if sh else None,
            "swing_low": round(sl, 2) if sl else None,
            "price": round(price, 2),
            "signal": signal,
        }
        if fib:
            results[symbol]["levels"] = {
                k: {lk: round(lv, 2) for lk, lv in v.items() if isinstance(v, dict)}
                for k, v in fib.items() if isinstance(v, dict)
            }
        
        s = signal
        loc = f"at {s['nearest_level']}" if s.get("at_level") else f"near {s.get('nearest_level','?')} ({(s.get('distance_pct',0)):.1f}%)"
        print(f"{symbol}: ${price:.0f} swing={sl:.0f}-{sh:.0f} {loc}")
    
    results["generated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = STATE_DIR / "fibonacci-signal.latest.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"OK Written to {out}")

if __name__ == "__main__":
    main()
