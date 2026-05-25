#!/usr/bin/env python3
"""Corrected turtle-breakout sweep — channel uses PRIOR bars only (classic Donchian)."""
import csv
import numpy as np

INPUT = "/Users/brain/hedge/data/free/NQ-60m-1y.csv"

rows = []
with open(INPUT) as f:
    for row in csv.DictReader(f):
        rows.append(row)

n = len(rows)
close = np.array([float(r["close"]) for r in rows])
high = np.array([float(r["high"]) for r in rows])
low = np.array([float(r["low"]) for r in rows])

print(f"Loaded {n} bars: {rows[0]['ts']} to {rows[-1]['ts']}")

# Precompute ATRs
atr_periods = [14, 20]
atr_cache = {}
for p in atr_periods:
    tr_arr = np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1]))
    tr_arr = np.maximum(tr_arr, np.abs(low[1:] - close[:-1]))
    atr = np.zeros(n)
    atr[0] = tr_arr[0]
    for i in range(1, n-1):
        atr[i] = (atr[i-1] * (p - 1) + tr_arr[i]) / p
    atr_cache[p] = atr

# Precompute rolling max/min for channel periods (PRIOR bars only, excluding current)
ch_periods = [5, 10, 20, 40, 60]
ch_cache = {}
for ch in ch_periods:
    h_roll = np.zeros(n)
    l_roll = np.zeros(n)
    for i in range(ch + 1, n):
        h_roll[i] = high[i-ch:i].max()   # bars i-ch through i-1 (excludes current bar i)
        l_roll[i] = low[i-ch:i].min()
    ch_cache[ch] = (h_roll, l_roll)

def test_params_fast(sma_p, ch_p, atr_p, ex_b):
    h_roll, l_roll = ch_cache[ch_p]
    atr_arr = atr_cache[atr_p]
    
    trades = wins = 0
    total_r = 0.0
    longs = shorts = 0
    
    min_i = max(sma_p, ch_p + 1, atr_p)
    end_i = n - ex_b
    
    for i in range(min_i, end_i):
        a = atr_arr[i]
        if a <= 0:
            continue
        
        s = close[i-sma_p+1:i+1].mean()
        entry = close[i]
        
        # LONG: close above SMA AND close above prior channel high
        if entry > s and entry > h_roll[i]:
            exit_p = close[i + ex_b]
            r = (exit_p - entry) / a
            trades += 1
            longs += 1
            total_r += r
            if r > 0:
                wins += 1
        
        # SHORT: close below SMA AND close below prior channel low
        elif entry < s and entry < l_roll[i]:
            exit_p = close[i + ex_b]
            r = (entry - exit_p) / a
            trades += 1
            shorts += 1
            total_r += r
            if r > 0:
                wins += 1
    
    return trades, wins, total_r, longs, shorts

# Parameter grid
smas = [20, 50, 100, 200]
chs = [5, 10, 20, 40, 60]
atrs = [14, 20]
exits = [3, 5, 8, 13]

results = []
total = len(smas) * len([c for c in chs if c <= max(smas)]) * len(atrs) * len(exits)

for sma_p in smas:
    for ch_p in chs:
        if ch_p > sma_p:
            continue
        for atr_p in atrs:
            for ex_b in exits:
                t, w, tr, lo, sh = test_params_fast(sma_p, ch_p, atr_p, ex_b)
                if t > 0:
                    wr = w / t * 100
                    results.append((sma_p, ch_p, atr_p, ex_b, t, w, wr, tr, tr/t, lo, sh))

results.sort(key=lambda x: x[7], reverse=True)

print(f"\n{'SMA':>5} {'CH':>4} {'ATR':>4} {'ExB':>4} {'Trades':>7} {'Wins':>6} {'WR%':>6} {'TotalR':>8} {'AvgR':>7} {'Long':>5} {'Short':>6}")
print("-" * 85)

for r in results[:30]:
    sma_p, ch_p, atr_p, ex_b, t, w, wr, tr, avg_r, lo, sh = r
    print(f"{sma_p:>5} {ch_p:>4} {atr_p:>4} {ex_b:>4} {t:>7} {w:>6} {wr:>6.1f} {tr:>8.2f} {avg_r:>7.3f} {lo:>5} {sh:>6}")

print(f"\nCombos with trades: {len(results)}")

if results:
    best = results[0]
    worst = results[-1]
    print(f"\nBEST  by TotalR: SMA={best[0]} CH={best[1]} ATR={best[2]} ExB={best[3]}")
    print(f"  {best[4]} trades, {best[5]} wins, {best[6]:.1f}% WR, {best[7]:.2f}R total, {best[8]:.3f}R avg")
    print(f"  Longs: {best[9]}, Shorts: {best[10]}")
    
    # Also show best by avgR with decent trade count
    filtered = [r for r in results if r[4] >= 50]
    if filtered:
        best50 = max(filtered, key=lambda x: x[7])
        print(f"\nBEST  (≥50 trades): SMA={best50[0]} CH={best50[1]} ATR={best50[2]} ExB={best50[3]}")
        print(f"  {best50[4]} trades, {best50[5]} wins, {best50[6]:.1f}% WR, {best50[7]:.2f}R total, {best50[8]:.3f}R avg")

# Save
output_path = "/Users/brain/hedge/data/free/turtle_breakout_sweep.csv"
with open(output_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sma_period", "ch_period", "atr_period", "exit_bars", "trades", "wins", "wr_pct", "total_r", "avg_r", "longs", "shorts"])
    for r in results:
        w.writerow(r)
print(f"\nFull results saved to {output_path}")
