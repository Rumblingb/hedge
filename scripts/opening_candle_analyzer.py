#!/usr/bin/env python3
"""
Opening Candle Spike Analyzer — NQ/ES Session Startup
=======================================================
Analyzes the first 1-3 candles of each trading session for gap/run patterns.
Key hypothesis: The opening 15-30m creates 40%+ of the day's range.
If we can detect direction from the open, we have a major timing edge.

Patterns detected:
1. GAP UP + HOLD → Trend day (trend-follow strategies favored)
2. GAP UP + REVERSAL → Trap day (manipulation, fade signals favored)
3. GAP DOWN + HOLD → Trend day
4. GAP DOWN + REVERSAL → Trap day
5. FLAT OPEN + SPIKE → Volatility expansion (ORB strategies)
6. FLAT OPEN + RANGE → Low vol day (mean-reversion, VWAP)

Output: session_type signal for the decision bridge.
"""
import json, os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

HOME = os.environ.get("HOME", "/Users/brain")
STATE_DIR = Path(HOME) / ".rumbling-hedge" / "state"
DATA_DIR = Path(HOME) / "hedge" / "data" / "free"

def load_recent_60m(symbol):
    for suffix in ["-60d.csv", "-21d.csv"]:
        p = DATA_DIR / f"{symbol}-60m{suffix}"
        if p.exists():
            df = pd.read_csv(p)
            if "ts" in df.columns:
                df = df.rename(columns={"ts": "time"})
            df["time"] = pd.to_datetime(df["time"])
            return df.sort_values("time").reset_index(drop=True)
    return None

def detect_sessions(df):
    """Detect US session opens from 60m data and classify them."""
    if df is None or len(df) < 20:
        return []
    
    results = []
    df = df.copy()
    df['hour_et'] = (df['time'].dt.hour - 4) % 24
    df['date'] = df['time'].dt.date
    df['range'] = df['high'] - df['low']
    
    # US session open = 9:30 ET (hour 9 or 10 in 60m data)
    US_OPEN_HOURS = [9, 10]  # 9:00-9:59 or 10:00-10:59 ET
    
    for date, group in df.groupby("date"):
        open_bars = group[group["hour_et"].isin(US_OPEN_HOURS)]
        if len(open_bars) < 2:
            continue
        
        # First 2 bars of session
        b1 = open_bars.iloc[0]
        b2 = open_bars.iloc[1] if len(open_bars) > 1 else None
        
        # Previous day's close
        prev_day = group[group["hour_et"] < 9]
        prev_close = float(prev_day.iloc[-1]["close"]) if len(prev_day) > 0 else float(b1["open"])
        
        # Gap calculation
        gap = float(b1["open"]) - prev_close
        gap_pct = gap / prev_close * 100
        
        # First bar range
        b1_range = float(b1["high"]) - float(b1["low"])
        b1_dir = "up" if float(b1["close"]) > float(b1["open"]) else "down"
        b1_vol_ratio = float(b1["volume"]) / df["volume"].mean() if df["volume"].mean() > 0 else 1
        
        # Second bar direction (confirmation)
        b2_dir = None
        if b2 is not None:
            b2_dir = "up" if float(b2["close"]) > float(b2["open"]) else "down"
        
        # Classify session
        if abs(gap_pct) > 0.3:
            # GAP day
            gap_dir = "up" if gap > 0 else "down"
            if b1_dir == gap_dir and (b2_dir is None or b2_dir == gap_dir):
                session_type = "trend_day"
            elif b1_dir != gap_dir:
                session_type = "trap_day"
            else:
                session_type = "gap_neutral"
        else:
            # FLAT open
            if b1_range > df["range"].mean() * 1.5:
                session_type = "vol_expansion"
            else:
                session_type = "low_vol_day"
        
        results.append({
            "date": str(date),
            "gap_pct": round(gap_pct, 2),
            "first_bar_direction": b1_dir,
            "first_bar_range": round(b1_range, 2),
            "first_bar_vol_ratio": round(b1_vol_ratio, 2),
            "second_bar_direction": b2_dir,
            "session_type": session_type,
        })
    
    return results

def main():
    df_nq = load_recent_60m("NQ")
    sessions = detect_sessions(df_nq)
    
    # Analyze last 10 sessions for current bias
    recent = sessions[-10:] if len(sessions) >= 10 else sessions
    trend_days = sum(1 for s in recent if s["session_type"] == "trend_day")
    trap_days = sum(1 for s in recent if s["session_type"] == "trap_day")
    low_vol_days = sum(1 for s in recent if s["session_type"] == "low_vol_day")
    vol_expansions = sum(1 for s in recent if s["session_type"] == "vol_expansion")
    
    print("=== OPENING CANDLE ANALYSIS (Last 10 Sessions) ===")
    print(f"  Trend days:   {trend_days}/10 ({trend_days*10}%)")
    print(f"  Trap days:    {trap_days}/10 ({trap_days*10}%)")
    print(f"  Low vol days: {low_vol_days}/10 ({low_vol_days*10}%)")
    print(f"  Vol expand:   {vol_expansions}/10 ({vol_expansions*10}%)")
    print()
    
    # Most recent session
    if sessions:
        last = sessions[-1]
        print(f"  Last session: {last['date']} — {last['session_type']}")
        print(f"    Gap: {last['gap_pct']:+.2f}%")
        print(f"    1st bar: {last['first_bar_direction']} (range={last['first_bar_range']:.0f})")
        print(f"    2nd bar: {last['second_bar_direction']}")
    
    # Strategy recommendation for next session
    print()
    print("=== NEXT SESSION STRATEGY RECOMMENDATION ===")
    if trend_days >= 6:
        print("  → Favor TREND-FOLLOW (Vol-Regime, Trend-Mom)")
        print("  → Let profits run, wider stops")
    elif trap_days >= 4:
        print("  → Favor MEAN-REVERSION (VWAP, S/R Proximity)")
        print("  → Take profits quickly, tight stops")
    elif low_vol_days >= 5:
        print("  → Favor RANGE-BREAKOUT (ORB, Donchian)")
        print("  → Wait for expansion before entering")
    else:
        print("  → MIXED — wait for first 30m to confirm")
    
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recent_types": {"trend": trend_days, "trap": trap_days, "low_vol": low_vol_days, "vol_exp": vol_expansions},
        "last_session": sessions[-1] if sessions else {},
        "sessions": sessions[-20:] if sessions else [],
    }
    
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = STATE_DIR / "opening-candle-signal.latest.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\n  OK Written to {out}")

if __name__ == "__main__":
    main()
