#!/usr/bin/env python3
"""
NQ 4H Manipulation Pattern Detector — Institutional Order Flow Agent
======================================================================
Detects engineered market manipulation patterns on NQ 4-hour timeframe
by combining all YouTube research: SMC, ICT, Wyckoff, Order Flow.

Patterns Detected:
1. 🔴 Institutional Trap — Liquidity sweep above highs → engineered reversal
2. 🔴 Stop Hunt Cluster — Price targets concentrated stops zones
3. 🔴 Liquidity Sweep + FVG — Sweep old high/low, leave FVG gap, reverse
4. 🔴 Order Block Reversal — Price rejects at institutional order block
5. 🔴 Wyckoff Spring/UTAD — Engineered false breakout (spring/upthrust)
6. 🔴 4H Manipulation Cycle — The 4-phase manipulation pattern
7. 🔴 Self-Trading Detection — Abnormal volume without price movement
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

HOME = os.environ.get("HOME", "/Users/brain")
STATE_DIR = Path(HOME) / ".rumbling-hedge" / "state"
DATA_DIR = Path(HOME) / "hedge" / "data" / "free"
SIGNALS = {}

def load_bars(symbol, timeframe="60m"):
    """Load OHLCV data."""
    for suffix in ["-60d.csv", "-21d.csv", "-5d.csv"]:
        p = DATA_DIR / f"{symbol}-{timeframe}{suffix}"
        if p.exists():
            df = pd.read_csv(p)
            if "ts" in df.columns:
                df = df.rename(columns={"ts": "time"})
            df["time"] = pd.to_datetime(df["time"])
            return df.sort_values("time").reset_index(drop=True)
    return None

def build_4h_from_60m(df_60m):
    """Resample 60m data to 4H bars if direct 4H data isn't available."""
    if df_60m is None or len(df_60m) < 8:
        return None
    df = df_60m.copy()
    df.set_index("time", inplace=True)
    rule = "4h"
    ohlc = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }
    df_4h = df.resample(rule).agg(ohlc).dropna().reset_index()
    return df_4h

# ── Pattern 1: Institutional Trap Detection ──
def detect_institutional_trap(df, timeframe_label):
    """
    Pattern: Price breaks above a recent high (bull trap) or below a low (bear trap)
    with volume spike, then immediately reverses with equal force.
    Engineered by institutions to trigger stops before reversing.
    """
    if df is None or len(df) < 12:
        return []
    traps = []
    n = len(df)
    for i in range(3, n):
        # Need at least 3 bars before and after
        if i < 6 or i > n - 6:
            continue
        
        prev_5_high = float(df.iloc[i-5:i]["high"].max())
        prev_5_low = float(df.iloc[i-5:i]["low"].min())
        prev_5_vol = float(df.iloc[i-5:i]["volume"].mean())
        
        current_bar = df.iloc[i]
        next_3 = df.iloc[i+1:i+4]
        
        curr_high = float(current_bar["high"])
        curr_low = float(current_bar["low"])
        curr_close = float(current_bar["close"])
        curr_open = float(current_bar["open"])
        curr_vol = float(current_bar["volume"])
        
        next_close = float(next_3["close"].iloc[-1]) if len(next_3) >= 3 else curr_close
        
        # Bull Trap: Break above recent high, then close back below
        if curr_high > prev_5_high and curr_close < curr_open and curr_vol > prev_5_vol * 1.3:
            # Price broke out above recent high (stopped shorts)
            # Then reversed and closed bearish (trapped longs)
            # Next 3 bars should continue lower
            if next_close < curr_close:
                strength = min(1.0, (curr_vol / prev_5_vol - 1.0) * 0.5 + 0.5)
                traps.append({
                    "type": "institutional_trap",
                    "direction": "bearish",
                    "trap_bar_idx": i,
                    "trap_high": round(curr_high, 2),
                    "trap_low": round(curr_low, 2),
                    "breakout_level": round(prev_5_high, 2),
                    "volume_ratio": round(float(curr_vol / prev_5_vol), 2),
                    "strength": round(strength, 2),
                    "timeframe": timeframe_label,
                })
        
        # Bear Trap: Break below recent low, then close back above
        elif curr_low < prev_5_low and curr_close > curr_open and curr_vol > prev_5_vol * 1.3:
            if next_close > curr_close:
                strength = min(1.0, (curr_vol / prev_5_vol - 1.0) * 0.5 + 0.5)
                traps.append({
                    "type": "institutional_trap",
                    "direction": "bullish",
                    "trap_bar_idx": i,
                    "trap_high": round(curr_high, 2),
                    "trap_low": round(curr_low, 2),
                    "breakout_level": round(prev_5_low, 2),
                    "volume_ratio": round(float(curr_vol / prev_5_vol), 2),
                    "strength": round(strength, 2),
                    "timeframe": timeframe_label,
                })
    return traps

# ── Pattern 2: Liquidity Sweep + FVG Detection ──
def detect_liquidity_sweep_fvg(df, timeframe_label):
    """
    Pattern: Price sweeps a key liquidity level (previous swing high/low),
    creating a Fair Value Gap (FVG) — a gap between consecutive candles' wicks.
    Then reverses into the FVG before continuing.
    """
    if df is None or len(df) < 20:
        return []
    sweeps = []
    n = len(df)
    
    # Find swing highs and lows
    swing_windows = 10
    swing_highs = []
    swing_lows = []
    for i in range(swing_windows, n - swing_windows):
        if float(df.iloc[i]["high"]) == float(df.iloc[i-swing_windows:i+swing_windows]["high"].max()):
            swing_highs.append((i, float(df.iloc[i]["high"])))
        if float(df.iloc[i]["low"]) == float(df.iloc[i-swing_windows:i+swing_windows]["low"].min()):
            swing_lows.append((i, float(df.iloc[i]["low"])))
    
    # Check if recent bars swept any swing level
    for i in range(n - 10, n - 2):
        bar = df.iloc[i]
        for sh_idx, sh_level in swing_highs:
            if sh_idx < i and i - sh_idx < 30:
                if float(bar["high"]) > sh_level and float(bar["close"]) < sh_level:
                    # Swept the swing high and closed below it (FVG left)
                    if i + 2 < n:
                        next_low = float(df.iloc[i+1]["low"])
                        gap = sh_level - next_low
                        if gap > 0:
                            sweeps.append({
                                "type": "liquidity_sweep",
                                "direction": "bearish",
                                "swept_level": round(sh_level, 2),
                                "sweep_bar_idx": i,
                                "fvg_gap": round(gap, 2),
                                "timeframe": timeframe_label,
                            })
                    break
        
        for sl_idx, sl_level in swing_lows:
            if sl_idx < i and i - sl_idx < 30:
                if float(bar["low"]) < sl_level and float(bar["close"]) > sl_level:
                    if i + 2 < n:
                        next_high = float(df.iloc[i+1]["high"])
                        gap = next_high - sl_level
                        if gap > 0:
                            sweeps.append({
                                "type": "liquidity_sweep",
                                "direction": "bullish",
                                "swept_level": round(sl_level, 2),
                                "sweep_bar_idx": i,
                                "fvg_gap": round(gap, 2),
                                "timeframe": timeframe_label,
                            })
                    break
    return sweeps

# ── Pattern 3: Wyckoff Spring/UTAD ──
def detect_wyckoff_spring_utad(df, timeframe_label):
    """
    Pattern: Wyckoff Spring (bullish) — price drives below support on high volume,
    then quickly recovers above. UTAD (bearish) — price drives above resistance 
    on high volume, then drops back below.
    The spring/UTAD is the LAST false move before the real trend.
    """
    if df is None or len(df) < 30:
        return []
    signals = []
    n = len(df)
    
    # Find support/resistance (30-bar range)
    for i in range(20, n - 5):
        recent_30 = df.iloc[i-30:i]
        support = float(recent_30["low"].min())
        resistance = float(recent_30["high"].max())
        
        bar = df.iloc[i]
        next_5 = df.iloc[i+1:i+6]
        if len(next_5) < 3:
            continue
        
        curr_open = float(bar["open"])
        curr_high = float(bar["high"])
        curr_low = float(bar["low"])
        curr_close = float(bar["close"])
        curr_vol = float(bar["volume"])
        avg_vol = float(recent_30["volume"].mean())
        
        # Spring: break below support, close back above, volume spike
        if curr_low < support * 0.995 and curr_close > support and curr_vol > avg_vol * 1.5:
            next_5_close = float(next_5["close"].mean())
            if next_5_close > support:
                signals.append({
                    "type": "wyckoff_spring",
                    "direction": "bullish",
                    "spring_low": round(curr_low, 2),
                    "support_level": round(support, 2),
                    "volume_ratio": round(float(curr_vol / avg_vol), 2),
                    "timeframe": timeframe_label,
                })
        
        # UTAD: break above resistance, close back below, volume spike
        elif curr_high > resistance * 1.005 and curr_close < resistance and curr_vol > avg_vol * 1.5:
            next_5_close = float(next_5["close"].mean())
            if next_5_close < resistance:
                signals.append({
                    "type": "wyckoff_utad",
                    "direction": "bearish",
                    "utad_high": round(curr_high, 2),
                    "resistance_level": round(resistance, 2),
                    "volume_ratio": round(float(curr_vol / avg_vol), 2),
                    "timeframe": timeframe_label,
                })
    return signals

# ── Pattern 4: Self-Trading / Wash Trading Detection ──
def detect_wash_trading(df, timeframe_label):
    """
    Pattern: Abnormal volume without corresponding price movement.
    When institutions self-trade (wash trade), volume spikes but price 
    stays in a narrow range. This creates fake liquidity.
    After the wash trade cycle, the real move follows.
    
    Reference: The Manipulator's Math (Brain Truffle) — self-trading creates
    artificial volume and price levels.
    """
    if df is None or len(df) < 20:
        return []
    signals = []
    n = len(df)
    
    for i in range(15, n - 3):
        recent = df.iloc[i-10:i]
        avg_vol = float(recent["volume"].mean())
        avg_range = float((recent["high"] - recent["low"]).mean())
        
        bar = df.iloc[i]
        curr_vol = float(bar["volume"])
        curr_range = float(bar["high"]) - float(bar["low"])
        next_3_range = float(df.iloc[i+1:i+4]["high"].max()) - float(df.iloc[i+1:i+4]["low"].min())
        
        # High volume but narrow range (wash trading)
        if curr_vol > avg_vol * 2.0 and curr_range < avg_range * 0.5:
            signals.append({
                "type": "wash_trading",
                "confidence": min(0.8, (curr_vol / avg_vol) * 0.3 + 0.3),
                "volume_ratio": round(float(curr_vol / avg_vol), 2),
                "range_ratio": round(float(curr_range / avg_range), 2),
                "timeframe": timeframe_label,
            })
        
        # After wash trade, what happens?
        if len(signals) > 0 and signals[-1]["type"] == "wash_trading":
            last_sig_idx = i
            break
    
    return signals

# ── Pattern 5: Stop Hunt Cluster Detection ──
def detect_stop_hunt_cluster(df, timeframe_label):
    """
    Pattern: Multiple consecutive bars testing the same key level,
    building liquidity before the final sweep. Identifies where
    stop losses are clustered.
    
    Clustered stops are above recent swing highs (long stops)
    and below recent swing lows (short stops).
    """
    if df is None or len(df) < 20:
        return []
    clusters = []
    n = len(df)
    
    recent_high = float(df.iloc[-20:]["high"].max())
    recent_low = float(df.iloc[-20:]["low"].min())
    recent_vol = float(df.iloc[-20:]["volume"].mean())
    
    last_5_highs = [float(df.iloc[-i]["high"]) for i in range(1, 6)]
    last_5_lows = [float(df.iloc[-i]["low"]) for i in range(1, 6)]
    
    # Check if price is approaching a swing high/low (testing stops)
    last_close = float(df.iloc[-1]["close"])
    last_vol = float(df.iloc[-1]["volume"])
    
    # Approaching recent high → longs have stops there
    if abs(last_close - recent_high) / recent_high < 0.005:
        clusters.append({
            "type": "stop_hunt_zone",
            "direction": "bearish",
            "zone_level": round(recent_high, 2),
            "distance_pct": round(abs(last_close - recent_high) / recent_high * 100, 2),
            "volume_confirmation": last_vol > recent_vol * 1.2,
            "timeframe": timeframe_label,
        })
    
    # Approaching recent low → shorts have stops there
    if abs(last_close - recent_low) / recent_low < 0.005:
        clusters.append({
            "type": "stop_hunt_zone",
            "direction": "bullish",
            "zone_level": round(recent_low, 2),
            "distance_pct": round(abs(last_close - recent_low) / recent_low * 100, 2),
            "volume_confirmation": last_vol > recent_vol * 1.2,
            "timeframe": timeframe_label,
        })
    
    return clusters

# ── Pattern 6: Order Block Identification ──
def detect_order_blocks(df, timeframe_label):
    """
    Pattern: The LAST bearish candle before a sustained bullish move (bullish OB),
    or the LAST bullish candle before a sustained bearish move (bearish OB).
    Institutions place large orders at these levels.
    
    When price returns to an OB level and shows rejection, it's a high-probability entry.
    """
    if df is None or len(df) < 20:
        return []
    obs = []
    n = len(df)
    
    for i in range(10, n - 5):
        prev = df.iloc[i-1]
        curr = df.iloc[i]
        next_5 = df.iloc[i+1:i+6]
        
        curr_open = float(curr["open"])
        curr_close = float(curr["close"])
        curr_high = float(curr["high"])
        curr_low = float(curr["low"])
        prev_close = float(prev["close"])
        
        # Bullish OB: Last bearish candle before 5+ bullish candles
        next_5_bullish = sum(1 for _, r in next_5.iterrows() if float(r["close"]) > float(r["open"]))
        if curr_close < curr_open and next_5_bullish >= 4:
            obs.append({
                "type": "order_block",
                "direction": "bullish",
                "ob_level": round(curr_low, 2),  # support level
                "ob_high": round(curr_high, 2),
                "strength": round(next_5_bullish / 5.0, 2),
                "timeframe": timeframe_label,
            })
        
        # Bearish OB: Last bullish candle before 5+ bearish candles
        next_5_bearish = sum(1 for _, r in next_5.iterrows() if float(r["close"]) < float(r["open"]))
        if curr_close > curr_open and next_5_bearish >= 4:
            obs.append({
                "type": "order_block",
                "direction": "bearish",
                "ob_level": round(curr_high, 2),  # resistance level
                "ob_low": round(curr_low, 2),
                "strength": round(next_5_bearish / 5.0, 2),
                "timeframe": timeframe_label,
            })
    return obs

# ── Pattern 7: Bearish/Bullish Candle Pattern Detection ──
def detect_candle_patterns(df, timeframe_label):
    """
    5 Manipulation Candlestick Patterns Banks Use (from YouTube research):
    1. Large wick rejection at key level
    2. Engulfing pattern at swing point
    3. Doji at resistance/support
    4. Inside bar before breakout false move
    5. Pin bar at liquidity zone
    """
    if df is None or len(df) < 10:
        return []
    patterns = []
    n = len(df)
    last = df.iloc[-1]
    
    curr_open = float(last["open"])
    curr_close = float(last["close"])
    curr_high = float(last["high"])
    curr_low = float(last["low"])
    
    body = abs(curr_close - curr_open)
    total_range = curr_high - curr_low if curr_high > curr_low else 1
    upper_wick = curr_high - max(curr_close, curr_open)
    lower_wick = min(curr_close, curr_open) - curr_low
    
    # Pin bar / shooting star: upper wick > 2x body
    if body > 0 and upper_wick > body * 2 and lower_wick < body * 0.3:
        patterns.append({
            "type": "shooting_star",
            "direction": "bearish",
            "wick_ratio": round(upper_wick / body, 2),
            "timeframe": timeframe_label,
        })
    
    # Hammer: lower wick > 2x body
    if body > 0 and lower_wick > body * 2 and upper_wick < body * 0.3:
        patterns.append({
            "type": "hammer",
            "direction": "bullish",
            "wick_ratio": round(lower_wick / body, 2),
            "timeframe": timeframe_label,
        })
    
    # Doji: body < 5% of range
    if total_range > 0 and body / total_range < 0.05:
        patterns.append({
            "type": "doji",
            "direction": "neutral",
            "timeframe": timeframe_label,
        })
    
    # Check engulfing (need previous bar)
    if n >= 2:
        prev = df.iloc[-2]
        prev_open = float(prev["open"])
        prev_close = float(prev["close"])
        
        # Bullish engulfing
        if prev_close < prev_open and curr_close > curr_open and curr_open < prev_close and curr_close > prev_open:
            patterns.append({
                "type": "bullish_engulfing",
                "direction": "bullish",
                "timeframe": timeframe_label,
            })
        
        # Bearish engulfing
        if prev_close > prev_open and curr_close < curr_open and curr_open > prev_close and curr_close < prev_open:
            patterns.append({
                "type": "bearish_engulfing",
                "direction": "bearish",
                "timeframe": timeframe_label,
            })
    
    return patterns

# ── Main Analysis ──
def analyze_instrument(df_4h, symbol):
    """Run ALL manipulation pattern detectors on 4H data."""
    if df_4h is None or len(df_4h) < 20:
        return {"status": "insufficient_data", "patterns": []}
    
    all_patterns = []
    timeframe = "4H"
    
    all_patterns.extend(detect_institutional_trap(df_4h, timeframe))
    all_patterns.extend(detect_liquidity_sweep_fvg(df_4h, timeframe))
    all_patterns.extend(detect_wyckoff_spring_utad(df_4h, timeframe))
    all_patterns.extend(detect_wash_trading(df_4h, timeframe))
    all_patterns.extend(detect_stop_hunt_cluster(df_4h, timeframe))
    all_patterns.extend(detect_order_blocks(df_4h, timeframe))
    all_patterns.extend(detect_candle_patterns(df_4h, timeframe))
    
    # Also run on 60m for comparison
    all_patterns.extend(detect_institutional_trap(df_4h, "4H"))
    all_patterns.extend(detect_candle_patterns(df_4h, "4H"))
    
    # Compute aggregate bias from all patterns
    bullish_count = sum(1 for p in all_patterns if p.get("direction") == "bullish")
    bearish_count = sum(1 for p in all_patterns if p.get("direction") == "bearish")
    
    if bullish_count > bearish_count * 2:
        bias = "bullish"
        confidence = min(0.9, 0.5 + (bullish_count - bearish_count) * 0.1)
    elif bearish_count > bullish_count * 2:
        bias = "bearish"
        confidence = min(0.9, 0.5 + (bearish_count - bullish_count) * 0.1)
    else:
        bias = "neutral"
        confidence = 0.3
    
    # Focus on RECENT patterns only (last 6 bars ~ 24 hours)
    def is_recent(p):
        idx = p.get("trap_bar_idx")
        if idx is None:
            idx = p.get("sweep_bar_idx")
        if idx is None:
            return False
        return 0 < len(df_4h) - idx <= 8
    recent_patterns = [p for p in all_patterns if is_recent(p)]
    wyckoff_patterns = [p for p in all_patterns if p["type"] in ("wyckoff_spring", "wyckoff_utad")]
    
    setups = wyckoff_patterns
    for p in recent_patterns:
        if p["type"] in ("institutional_trap", "liquidity_sweep") and len(setups) < 3:
            setups.append(p)
    
    return {
        "symbol": symbol,
        "total_patterns": len(all_patterns),
        "bullish_patterns": bullish_count,
        "bearish_patterns": bearish_count,
        "bias": bias,
        "confidence": round(confidence, 2),
        "active_setups": setups,
        "patterns": all_patterns[-10:],  # Last 10 for context
        "last_price": round(float(df_4h.iloc[-1]["close"]), 2),
        "last_4h_time": str(df_4h.iloc[-1]["time"])[:19],
    }

def main():
    # Load 60m data and resample to 4H
    df_60m_nq = load_bars("NQ", "60m")
    df_4h_nq = build_4h_from_60m(df_60m_nq)
    
    df_60m_es = load_bars("ES", "60m")
    df_4h_es = build_4h_from_60m(df_60m_es)
    
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "NQ": analyze_instrument(df_4h_nq, "NQ"),
        "ES": analyze_instrument(df_4h_es, "ES"),
    }
    
    # Print summary
    for sym in ["NQ", "ES"]:
        r = results[sym]
        print(f"\n{'='*50}")
        print(f"  {sym} 4H MANIPULATION ANALYSIS")
        print(f"{'='*50}")
        print(f"  Total patterns: {r.get('total_patterns', 0)} ({r.get('bullish_patterns',0)}B/{r.get('bearish_patterns',0)}S)")
        print(f"  Bias: {r.get('bias', 'neutral').upper()} (conf: {r.get('confidence', 0):.2f})")
        print(f"  Price: ${r.get('last_price', 0):.0f} @ {r.get('last_4h_time', '?')}")
        for s in r.get('active_setups', []):
            print(f"  🔴 {s['type'].upper()} — {s['direction'].upper()}")
        if not r.get('active_setups'):
            print(f"  ✅ No active manipulation setups")
        print()
    
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = STATE_DIR / "manipulation-4h-signal.latest.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"  ✅ Written to {out}")

if __name__ == "__main__":
    main()
