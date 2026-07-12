#!/usr/bin/env python3
"""
Quick strategy smoke test — runs a simple reversal/donchian check on CSV data.
Much lighter than the full strategy-factory pipeline.
Usage: python3 scripts/quick-strategy-test.py <data-file>
"""
import csv, sys, math
from pathlib import Path

csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv"

# Load
with open(csv_path) as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"Loaded {len(rows)} bars from {csv_path}")

# Group by symbol
by_sym = {}
for r in rows:
    sym = r["symbol"]
    by_sym.setdefault(sym, []).append(r)

print(f"Symbols: {', '.join(by_sym.keys())}\n")

total_signals_short_rev = 0
total_signals_donchian = 0

for sym, bars in by_sym.items():
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    vols = [float(b.get("volume", 0) or 0) for b in bars]
    
    print(f"=== {sym}: {len(bars)} bars ===")
    
    # === SHORT-TERM REVERSAL CHECK ===
    rev_signals = 0
    rev_long = 0
    rev_short = 0
    for i in range(60, len(closes)):
        lookback = closes[i] - closes[i - 60]
        atr_vals = []
        for j in range(max(0, i - 14), i):
            tr = max(highs[j] - lows[j], abs(highs[j] - closes[j-1]) if j > 0 else 0, abs(lows[j] - closes[j-1]) if j > 0 else 0)
            atr_vals.append(tr)
        atr = sum(atr_vals) / len(atr_vals) if atr_vals else 0
        if atr <= 0: continue
        
        abs_ret = abs(lookback)
        if abs_ret > 1.5 * atr:
            # Volume check
            avg_vol = sum(vols[i-60:i]) / 60
            if vols[i] > 1.5 * avg_vol:
                rev_signals += 1
                if lookback < 0:
                    rev_long += 1
                else:
                    rev_short += 1
    
    print(f"  Short-term reversal v2 signals: {rev_signals} ({rev_long} long, {rev_short} short)")
    print(f"  Est. trades/day: {rev_signals / 5:.1f}")
    total_signals_short_rev += rev_signals
    
    # === DONCHIAN BREAKOUT CHECK ===
    lookback = 20
    db_signals = 0
    db_long = 0
    db_short = 0
    for i in range(lookback, len(closes)):
        hi = max(highs[i - lookback:i])
        lo = min(lows[i - lookback:i])
        
        # ATR
        atr_vals = []
        for j in range(max(0, i - 14), i):
            tr = max(highs[j] - lows[j], abs(highs[j] - closes[j-1]) if j > 0 else 0, abs(lows[j] - closes[j-1]) if j > 0 else 0)
            atr_vals.append(tr)
        atr = sum(atr_vals) / len(atr_vals) if atr_vals else 0
        if atr <= 0: continue
        
        if closes[i] > hi:
            db_signals += 1
            db_long += 1
        elif closes[i] < lo:
            db_signals += 1
            db_short += 1
    
    print(f"  Donchian breakout signals: {db_signals} ({db_long} long, {db_short} short)")
    print(f"  Est. trades/day: {db_signals / 5:.1f}")
    total_signals_donchian += db_signals
    print()

print("=" * 60)
print(f"TOTAL short-term reversal signals: {total_signals_short_rev}")
print(f"TOTAL donchian breakout signals:   {total_signals_donchian}")
print()

# Assessment
for name, count in [("Short-term reversal v2", total_signals_short_rev), ("Donchian breakout", total_signals_donchian)]:
    trades_per_day = count / 5
    if trades_per_day >= 4:
        print(f"✅ {name}: STRONG ({trades_per_day:.1f} trades/day) — ready for OOS")
    elif trades_per_day >= 1:
        print(f"⚠️ {name}: MODERATE ({trades_per_day:.1f} trades/day) — needs tuning or more data")
    else:
        print(f"❌ {name}: WEAK ({trades_per_day:.1f} trades/day) — doesn't fire in current regime")
