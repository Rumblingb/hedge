#!/usr/bin/env python3
"""OOS validation for top candidates from quant research sweep."""
import csv, sys
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

BASE = "/Users/brain/hedge/data/free"

@dataclass
class Bar:
    ts: str; symbol: str; open: float; high: float; low: float; close: float; volume: int
    @property
    def dt(self): return datetime.fromisoformat(self.ts.replace('Z','+00:00'))

def load(path, symbol="NQ"):
    bars = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row['symbol'].strip().upper() == symbol:
                bars.append(Bar(ts=row['ts'], symbol=row['symbol'], open=float(row['open']),
                    high=float(row['high']), low=float(row['low']), close=float(row['close']), volume=int(row['volume'])))
    return bars

def atr(bars, idx, period=14):
    if idx < period: return 0.0
    return sum(bars[j].high - bars[j].low for j in range(idx-period, idx)) / period

def avg_vol(bars, idx, window):
    if idx < window: return 0
    return sum(b.volume for b in bars[idx-window:idx]) / window

def sma(closes, period):
    if len(closes) < period: return 0.0
    return sum(closes[-period:]) / period

# === Strategy 1: Donchian Breakout (30m) ===
def run_donchian(bars):
    trades = []
    n = len(bars)
    for i in range(20, n - 8):
        hi = max(b.high for b in bars[i-20:i])
        lo = min(b.low for b in bars[i-20:i])
        atr_v = atr(bars, i, 14)
        if atr_v <= 0: continue
        exit_b = bars[i+8]
        if bars[i].close > hi:
            r = (exit_b.close - bars[i].close) / atr_v
            trades.append(r)
        elif bars[i].close < lo:
            r = (bars[i].close - exit_b.close) / atr_v
            trades.append(r)
    return trades

# === Strategy 2: Short-term Reversal (15m) ===
def run_str_reversal(bars, atr_mult=1.5, exit_e=5):
    trades = []
    n = len(bars)
    for i in range(1, n - exit_e):
        atr_v = atr(bars, i, 14)
        if atr_v <= 0: continue
        exit_b = bars[i + exit_e]
        if bars[i].close < bars[i-1].close - atr_mult * atr_v:
            r = (exit_b.close - bars[i].close) / atr_v
            trades.append(r)
        elif bars[i].close > bars[i-1].close + atr_mult * atr_v:
            r = (bars[i].close - exit_b.close) / atr_v
            trades.append(r)
    return trades

# === Strategy 3: Vol Expansion Momentum (60m) ===
def run_vol_expansion(bars, slb=10, llb=20, squeeze_th=0.8, exit_e=8):
    trades = []
    n = len(bars)
    for i in range(llb + 3, n - exit_e):
        short_vol = sum(bars[j].high - bars[j].low for j in range(i-slb, i)) / slb
        long_vol = sum(bars[j].high - bars[j].low for j in range(i-llb, i)) / llb
        if long_vol <= 0: continue
        vr = short_vol / long_vol
        # Check if ratios for last 3 bars were below threshold
        prev_vr = []
        for k in range(1, 4):
            ps = sum(bars[j].high - bars[j].low for j in range(i-k-slb, i-k)) / slb
            pl = sum(bars[j].high - bars[j].low for j in range(i-k-llb, i-k)) / llb
            if pl <= 0: break
            prev_vr.append(ps / pl)
        if len(prev_vr) < 3: continue
        if not all(r < squeeze_th for r in prev_vr): continue  # wasn't squeezed
        if vr < squeeze_th: continue  # still squeezed, hasn't expanded
        atr_v = atr(bars, i, 14)
        if atr_v <= 0: continue
        closes = [b.close for b in bars[:i+1]]
        sma20 = sum(closes[-20:]) / 20.0 if len(closes) >= 20 else 0
        exit_b = bars[i + exit_e]
        if bars[i].close > sma20:
            r = (exit_b.close - bars[i].close) / atr_v
            trades.append(('long', r))
        elif bars[i].close < sma20:
            r = (bars[i].close - exit_b.close) / atr_v
            trades.append(('short', r))
    return trades

def report(trades, label):
    if not trades:
        return f"{label}: ❌ 0 trades"
    r_vals = [t if isinstance(t, (int, float)) else t[1] for t in trades]
    n = len(r_vals)
    r_total = sum(r_vals)
    wins = sum(1 for t in r_vals if t > 0)
    wr = wins / n * 100
    return f"{label}: ✅ {n}t, {wins}/{n-wins} W/L ({wr:.1f}%), R {r_total:+.2f}, avg {r_total/n:+.3f}"

print("=" * 80)
print("OOS VALIDATION — Top Candidates")
print("=" * 80)

tests = [
    ("donchian-breakout (30m)", "30m", run_donchian),
    ("short-term-reversal (15m)", "15m", lambda b: run_str_reversal(b, 1.5, 5)),
    ("vol-expansion-momentum (60m)", "60m", run_vol_expansion),
]

for name, tf, fn in tests:
    csv_path = f"{BASE}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-{tf}.csv"
    bars = load(csv_path, "NQ")
    n = len(bars)
    split_idx = n * 2 // 3  # first 66% train, last 33% OOS
    
    train = bars[:split_idx]
    test = bars[split_idx:]
    
    train_t = fn(train)
    test_t = fn(test)
    
    print(f"\n--- {name} ({len(bars)} bars, train {len(train)}, OOS {len(test)}) ---")
    print(f"  Train: {report(train_t, '')}")
    print(f"  OOS:   {report(test_t, '')}")
    
    test_r = sum(t if isinstance(t, (int, float)) else t[1] for t in test_t) if test_t else 0
    status = "✅ PASS" if test_r > 0 else "❌ FAIL"
    print(f"  Verdict: {status} (OOS R = {test_r:+.2f})")

# === Don't miss: session-composite ===
print(f"\n{'='*80}")
print("SESSION COMPOSITE (30m) — OOS")
print(f"{'='*80}")

def session_trend(bars):
    trades = []
    n = len(bars)
    for i in range(50, n - 8):
        h = bars[i].dt.hour * 60 + bars[i].dt.minute
        if not (3*60 <= h <= 7*60 or h >= 19*60 or h < 3*60):
            continue  # non-asia/london
        cs = [b.close for b in bars[:i+1]]
        s20 = sum(cs[-20:]) / 20.0 if len(cs) >= 20 else 0
        s50 = sum(cs[-50:]) / 50.0 if len(cs) >= 50 else 0
        if s20 == 0 or s50 == 0: continue
        av = sum(b.volume for b in bars[i-10:i]) / 10.0 if i >= 10 else 0
        if av <= 0: continue
        vr = bars[i].volume / av
        atr_v = atr(bars, i, 14)
        if atr_v <= 0: continue
        exit_b = bars[i+8]
        if bars[i].close > s20 and s20 > s50 and vr > 1.3:
            trades.append((exit_b.close - bars[i].close) / atr_v)
        elif bars[i].close < s20 and s20 < s50 and vr > 1.3:
            trades.append((bars[i].close - exit_b.close) / atr_v)
    return trades

bars30 = load(f"{BASE}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv", "NQ")
split30 = len(bars30) * 2 // 3
train30, test30 = bars30[:split30], bars30[split30:]

st_train = session_trend(train30)
st_test = session_trend(test30)
print(f"  wq-trend-mom (Asia+London) Train: {report(st_train, '')}")
print(f"  wq-trend-mom (Asia+London) OOS:   {report(st_test, '')}")

# Also test the base wq-trend-mom (all sessions) for comparison
def base_trend(bars):
    trades = []
    n = len(bars)
    for i in range(50, n - 8):
        cs = [b.close for b in bars[:i+1]]
        s20 = sum(cs[-20:]) / 20.0 if len(cs) >= 20 else 0
        s50 = sum(cs[-50:]) / 50.0 if len(cs) >= 50 else 0
        if s20 == 0 or s50 == 0: continue
        av = sum(b.volume for b in bars[i-10:i]) / 10.0 if i >= 10 else 0
        if av <= 0: continue
        vr = bars[i].volume / av
        atr_v = atr(bars, i, 14)
        if atr_v <= 0: continue
        exit_b = bars[i+8]
        if bars[i].close > s20 and s20 > s50 and vr > 1.3:
            trades.append((exit_b.close - bars[i].close) / atr_v)
        elif bars[i].close < s20 and s20 < s50 and vr > 1.3:
            trades.append((bars[i].close - exit_b.close) / atr_v)
    return trades

bt_train = base_trend(train30)
bt_test = base_trend(test30)
print(f"  wq-trend-mom (ALL sessions) Train: {report(bt_train, '')}")
print(f"  wq-trend-mom (ALL sessions) OOS:   {report(bt_test, '')}")
print(f"\n  Comparison: Asia+London OOS vs All-session OOS")
st_r = sum(st_test) if st_test else 0
bt_r = sum(bt_test) if bt_test else 0
print(f"    Asia+London: {st_r:+.2f}R vs All-sessions: {bt_r:+.2f}R")
print(f"    Session gate improvement: {(st_r - bt_r):+.2f}R")
