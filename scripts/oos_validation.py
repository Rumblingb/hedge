#!/usr/bin/env python3
"""
OOS Validation: Split 21d data into train (first 14d) and OOS (last 7d).
Test session-gated strategies + composite dispatch.
"""
import csv, sys
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Bar:
    ts: str; symbol: str; open: float; high: float; low: float; close: float; volume: int
    @property
    def dt(self): return datetime.fromisoformat(self.ts.replace('Z','+00:00'))

BASE = "/Users/brain/hedge/data/free"
def load(path, symbol="NQ"):
    bars = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row['symbol'].strip().upper() == symbol:
                bars.append(Bar(ts=row['ts'], symbol=row['symbol'], open=float(row['open']),
                    high=float(row['high']), low=float(row['low']), close=float(row['close']), volume=int(row['volume'])))
    return bars

def split_oos(bars, split_pct=0.66):
    n = len(bars)
    split = int(n * split_pct)
    return bars[:split], bars[split:]

def sma(closes, period):
    if len(closes) < period: return 0.0
    return sum(closes[-period:]) / period

def r_wq_trend_mom(bars, ss=20, sl=50, vt=1.3, eo=8):
    trades = []
    n = len(bars)
    if n < sl + eo + 2: return trades
    for i in range(sl, n - eo):
        c = [b.close for b in bars[:i+1]]
        sma_s, sma_l = sma(c, ss), sma(c, sl)
        if sma_s == 0 or sma_l == 0: continue
        av = sum(b.volume for b in bars[i-10:i]) / 10.0 if i >= 10 else 0
        if av <= 0: continue
        vr = bars[i].volume / av
        atr_v = sum(bars[j].high - bars[j].low for j in range(i-14, i)) / 14.0
        if atr_v <= 0: continue
        exit_b = bars[i + eo]
        if bars[i].close > sma_s and sma_s > sma_l and vr > vt:
            trades.append((exit_b.close - bars[i].close) / atr_v)
        elif bars[i].close < sma_s and sma_s < sma_l and vr > vt:
            trades.append((bars[i].close - exit_b.close) / atr_v)
    return trades

def r_orb_breakout(bars, rw=8, vt=1.3, eo=8):
    trades = []
    n = len(bars)
    if n < rw + eo + 2: return trades
    for i in range(rw + 2, n - eo):
        rh = max(b.high for b in bars[i-rw:i])
        rl = min(b.low for b in bars[i-rw:i])
        if rh - rl <= 0: continue
        av = sum(b.volume for b in bars[i-10:i]) / 10.0 if i >= 10 else 0
        if av <= 0: continue
        atr_v = sum(bars[j].high - bars[j].low for j in range(i-14, i)) / 14.0
        if atr_v <= 0: continue
        exit_b = bars[i + eo]
        if bars[i].close > rh and bars[i].volume > av * vt:
            trades.append((exit_b.close - bars[i].close) / atr_v)
        elif bars[i].close < rl and bars[i].volume > av * vt:
            trades.append((bars[i].close - exit_b.close) / atr_v)
    return trades

def report(trades, label):
    if not trades: return f"{label}: ❌ 0 trades"
    n = len(trades)
    r_total = sum(trades)
    wins = sum(1 for t in trades if t > 0)
    wr = wins / n * 100
    return f"{label}: ✅ {n} trades, {wins}/{n-wins} W/L ({wr:.1f}%), R {r_total:+.2f}, avg R {r_total/n:+.3f}"

print("=" * 80)
print("OOS VALIDATION: wq-trend-mom + orb-breakout (30m NQ)")
print("=" * 80)

csv_path = f"{BASE}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv"
bars = load(csv_path, "NQ")

# Walk-forward: 2 OOS windows
window_size = len(bars) // 3
print(f"\nTotal bars: {len(bars)}, window size: {window_size}")

results = []
for w in range(2):
    train_start = 0
    train_end = window_size * (w + 1)
    test_start = train_end
    test_end = min(test_start + window_size, len(bars))
    
    train = bars[train_start:test_start]
    test = bars[test_start:test_end]
    
    print(f"\n--- Window {w+1}: Train [{train_start}:{test_start}] ({len(train)} bars), OOS [{test_start}:{test_end}] ({len(test)} bars) ---")
    
    # wq-trend-mom on train (find best params)
    tm_train = r_wq_trend_mom(train)
    tm_test = r_wq_trend_mom(test)
    
    print(f"  wq-trend-mom train: {report(tm_train, '')}")
    print(f"  wq-trend-mom OOS:   {report(tm_test, '')}")
    
    # orb-breakout
    ob_train = r_orb_breakout(train)
    ob_test = r_orb_breakout(test)
    
    print(f"  orb-breakout train:  {report(ob_train, '')}")
    print(f"  orb-breakout OOS:    {report(ob_test, '')}")
    
    # COMPOSITE: only trade when BOTH agree (direction is in report already)
    # Since we're just computing R values without direction, we merge
    # A real composite would check direction alignment
    
    tm_r = sum(tm_test) if tm_test else 0
    ob_r = sum(ob_test) if ob_test else 0
    combined = tm_r + ob_r
    
    results.append({
        "window": w+1,
        "tm_train": sum(tm_train) if tm_train else 0,
        "tm_train_n": len(tm_train),
        "tm_oos": tm_r,
        "tm_oos_n": len(tm_test),
        "ob_train": sum(ob_train) if ob_train else 0,
        "ob_train_n": len(ob_train),
        "ob_oos": ob_r,
        "ob_oos_n": len(ob_test),
        "combined_oos": combined
    })

print(f"\n{'='*80}")
print("OOS SUMMARY")
print(f"{'='*80}")

for r in results:
    line = f"Window {r['window']}: "
    line += f"tm OOS R={r['tm_oos']:+.2f} ({r['tm_oos_n']}t) | "
    line += f"ob OOS R={r['ob_oos']:+.2f} ({r['ob_oos_n']}t) | "
    line += f"combined R={r['combined_oos']:+.2f}"
    status = "✅ PROFITABLE" if r['combined_oos'] > 0 else "❌ LOSING"
    print(f"  {line} {status}")

total_oos = sum(r['combined_oos'] for r in results)
status = "✅ PASS" if total_oos > 0 else "❌ FAIL"
print(f"\n  TOTAL OOS R: {total_oos:+.2f} {status}")
print(f"  Windows profitable: {sum(1 for r in results if r['combined_oos'] > 0)}/{len(results)}")
