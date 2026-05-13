#!/usr/bin/env python3
"""
Quick strategy v3 signal test — generates a sample of signals to verify
the v3 strategy actually fires on real ES/NQ data during NY RTH.
"""
import csv, json
from pathlib import Path

data_path = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv"
rows = []

with open(data_path) as f:
    for r in csv.DictReader(f):
        rows.append(r)

# Filter to active sessions: NY morning (12:30-15:30 UTC) + NY afternoon (17:00-19:30 UTC)
def is_active_session(ts):
    from datetime import datetime
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    h, m = dt.hour, dt.minute
    total = h * 60 + m
    morning = (12*60+30) <= total <= (15*60+30)
    afternoon = (17*60) <= total <= (19*60+30)
    return morning or afternoon

# Symbol counts
by_sym = {}
for r in rows:
    by_sym.setdefault(r["symbol"], []).append(r)

print(f"=== Data Overview ===")
print(f"Total bars: {len(rows)}")
print(f"Symbols: {', '.join(by_sym.keys())}")
print()

for sym, bars in by_sym.items():
    print(f"=== {sym}: {len(bars)} bars ===")
    
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    ts_list = [b["ts"] for b in bars]
    
    # Count bars in active session
    session_bars = sum(1 for t in ts_list if is_active_session(t))
    print(f"  NY RTH bars: {session_bars}/{len(bars)} ({session_bars/len(bars)*100:.1f}%)")
    
    # v3: 30-bar lookback, ATR > 1.5, volume > 1.5x avg
    rev_signals = []
    for i in range(30, len(closes)):
        ts = ts_list[i]
        if not is_active_session(ts):
            continue
        
        lookback = closes[i] - closes[i - 30]
        
        # ATR 14
        trs = []
        for j in range(max(1, i-14), i):
            tr = max(highs[j] - lows[j], abs(highs[j] - closes[j-1]), abs(lows[j] - closes[j-1]))
            trs.append(tr)
        atr = sum(trs) / len(trs) if trs else 0
        if atr <= 0:
            continue
        
        abs_ret = abs(lookback)
        if abs_ret < 1.5 * atr:
            continue
        
        # Volume
        vols = [float(bars[k].get("volume", 0) or 0) for k in range(i-30, i)]
        avg_vol = sum(vols) / len(vols) if vols else 0
        curr_vol = float(bars[i].get("volume", 0) or 0)
        if curr_vol < 1.5 * avg_vol:
            continue
        
        direction = "long" if lookback < 0 else "short"
        rev_signals.append({
            "ts": ts,
            "close": closes[i],
            "lookbackPct": round(lookback / closes[i] * 100, 2),
            "atr": round(atr, 2),
            "direction": direction,
        })
    
    print(f"  v3 reversal signals: {len(rev_signals)}")
    print(f"  Est. trades/day: {len(rev_signals)/5:.1f}")
    
    if rev_signals:
        longs = sum(1 for s in rev_signals if s["direction"] == "long")
        shorts = sum(1 for s in rev_signals if s["direction"] == "short")
        print(f"  Long: {longs}, Short: {shorts}")
        
        # Show a few example signals
        print(f"  Sample signals:")
        for s in rev_signals[:5]:
            print(f"    {s['ts']} | {s['direction']:6s} | close={s['close']:<8.2f} | ret={s['lookbackPct']:>6.2f}% | atr={s['atr']:.2f}")
    
    print()

# Total
print(f"=== TOTAL v3 Signals ===")
print(f"Signals generated across both markets.")
