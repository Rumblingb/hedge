#!/usr/bin/env python3
"""Quick ORB signal test — does opening-range-reversal v2 fire at all?"""
import csv
from datetime import datetime

DATA = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv"

def session_minute(ts, start_ct="08:30"):
    """Minutes from session start (CT). 08:30 CT = 13:30 UTC"""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    # ES/NQ RTH opens 8:30 CT = 13:30 UTC
    session_start_h, session_start_m = 13, 30  # UTC for 8:30 CT
    total_now = dt.hour * 60 + dt.minute
    total_start = session_start_h * 60 + session_start_m
    return total_now - total_start

def wick_ratio(open_p, high, low, close):
    body = max(abs(close - open_p), 0.0001)
    upper = (high - max(open_p, close)) / body
    lower = (min(open_p, close) - low) / body
    return upper, lower

with open(DATA) as f:
    rows = list(csv.DictReader(f))

by_sym = {}
for r in rows:
    by_sym.setdefault(r["symbol"], []).append(r)

for sym in ["ES", "NQ"]:
    bars = by_sym[sym]
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    opens = [float(b["open"]) for b in bars]
    ts_list = [b["ts"] for b in bars]
    vols = [float(b.get("volume", 0) or 0) for b in bars]

    print(f"=== {sym} ({len(bars)} bars) ===")

    short_signals = 0
    long_signals = 0

    for i in range(15, len(bars)):
        smin = session_minute(ts_list[i])
        if smin < 15 or smin > 90:
            continue  # Only ORB window

        opening_high = max(highs[i-15:i])
        opening_low = min(lows[i-15:i])
        upper, lower = wick_ratio(opens[i], highs[i], lows[i], closes[i])

        avg_vol = sum(vols[i-15:i]) / 15
        vol_ratio = vols[i] / avg_vol if avg_vol > 0 else 0
        if vol_ratio < 0.3:
            continue

        if highs[i] > opening_high and closes[i] < opening_high and upper >= 1.2:
            short_signals += 1
        if lows[i] < opening_low and closes[i] > opening_low and lower >= 1.2:
            long_signals += 1

    print(f"  ORB short signals: {short_signals}")
    print(f"  ORB long signals:  {long_signals}")
    print(f"  Total:             {short_signals + long_signals}")
    print(f"  Est/day:           {(short_signals + long_signals) / 5:.1f}")
    print()
