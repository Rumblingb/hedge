#!/usr/bin/env python3
"""Debug wq-trend-mom to match Rust output."""
import sys
sys.path.insert(0, '/Users/brain/hedge/bill-core/scripts')
from param_sweep import *

bars = load_bars('/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv', 'NQ')
n = len(bars)
print(f"n={n}, n-8={n-8}, n.saturating_sub(8)={max(0, n-8)}")

# Exact Rust reimplementation
trades = []
exit_offset = 8
for i in range(40, n - exit_offset):
    # Rust sma(&bars[..=i], period) 
    def rust_sma(period):
        slice_len = i + 1
        if slice_len < period:
            return 0.0
        start = slice_len - period
        s = 0.0
        for j in range(start, i+1):
            s += bars[j].close
        return s / period
    
    sma20 = rust_sma(20)
    sma50 = rust_sma(50)
    
    # Rust avg_vol: bars[i-10..i]
    if i < 10:
        avg_vol = 0.0
    else:
        avg_vol = sum(bars[j].volume for j in range(i-10, i)) / 10.0
    
    if avg_vol <= 0.0:
        continue
    vol_ratio = bars[i].volume / avg_vol
    
    # Rust ATR: bars[i-14..i]
    if i < 14:
        atr_val = 0.0
    else:
        atr_val = sum(bars[j].high - bars[j].low for j in range(i-14, i)) / 14.0
    if atr_val <= 0.0:
        continue
    
    exit_price = bars[i + exit_offset].close
    
    if bars[i].close > sma20 and sma20 > sma50 and vol_ratio > 1.3:
        trades.append(Trade(
            strategy_id="wq-trend-mom", symbol=bars[i].symbol,
            side="long", entry=bars[i].close, exit=exit_price,
            entry_ts=bars[i].ts, exit_ts=bars[i+exit_offset].ts,
            r_multiple=(exit_price - bars[i].close) / atr_val,
        ))
    elif bars[i].close < sma20 and sma20 < sma50 and vol_ratio > 1.3:
        trades.append(Trade(
            strategy_id="wq-trend-mom", symbol=bars[i].symbol,
            side="short", entry=bars[i].close, exit=exit_price,
            entry_ts=bars[i].ts, exit_ts=bars[i+exit_offset].ts,
            r_multiple=(bars[i].close - exit_price) / atr_val,
        ))

report(trades, "wq-trend-mom exact Rust port")
print(f"Rust says: 295 trades, total R 130.46")
print(f"Python says: {len(trades)} trades, total R {sum(t.r_multiple for t in trades):.2f}")
print(f"Difference: {295 - len(trades)} trades, {130.46 - sum(t.r_multiple for t in trades):.2f}R")

# Check for any NaN or inf
for t in trades:
    if t.r_multiple != t.r_multiple:  # NaN check
        print(f"  NaN found at {t.entry_ts}")
    if abs(t.r_multiple) == float('inf'):
        print(f"  Inf found at {t.entry_ts}")
