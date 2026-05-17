#!/usr/bin/env python3
"""
Deep strategy analysis — what drives edge, what can be fixed structurally.

Tests: session gating, regime-adaptive exits, vol confirmation on long side.
Uses Rust param_sweep for ground truth on base strategies.
"""
import subprocess, sys, csv, json
from dataclasses import dataclass
from typing import List, Tuple
from pathlib import Path
from datetime import datetime, timedelta

@dataclass
class Bar:
    ts: str; symbol: str; open: float; high: float; low: float; close: float; volume: int
    @property
    def dt(self) -> datetime:
        return datetime.fromisoformat(self.ts.replace('Z','+00:00'))

BASE = "/Users/brain/hedge/data/free"
CSVS = {
    "15m": f"{BASE}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "30m": f"{BASE}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "60m": f"{BASE}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
}

def load(csv_path: str, symbol: str) -> List[Bar]:
    bars = []
    with open(csv_path) as f:
        r = csv.DictReader(f)
        for row in r:
            if row['symbol'].strip().upper() == symbol:
                bars.append(Bar(ts=row['ts'], symbol=row['symbol'], open=float(row['open']),
                    high=float(row['high']), low=float(row['low']), close=float(row['close']), volume=int(row['volume'])))
    return bars

def split_by_session(bars: List[Bar]) -> dict:
    """Split bars into NY (09:30-16:00 ET), London (03:00-07:00), Asia (19:00-03:00)"""
    ny_m, ln_m, asia_m = [], [], []
    for b in bars:
        h = b.dt.hour
        m = b.dt.minute
        mins = h * 60 + m
        if 9*60+30 <= mins <= 16*60:
            ny_m.append(b)
        elif 3*60 <= mins <= 7*60:
            ln_m.append(b)
        elif mins >= 19*60 or mins < 3*60:
            asia_m.append(b)
    return {"NY": ny_m, "London": ln_m, "Asia": asia_m}

# === Strategy implementations matching Rust param_sweep ===
def sma(closes, period):
    if len(closes) < period: return 0.0
    return sum(closes[-period:]) / period

def atr(bars, idx, period=14):
    if idx < period: return 0.0
    return sum(bars[j].high - bars[j].low for j in range(idx-period, idx)) / period

def run_wq_trend_mom(bars, sma_short=20, sma_long=50, vol_threshold=1.3, exit_offset=8):
    trades = []
    min_bars = sma_long + exit_offset + 2
    if len(bars) < min_bars: return trades
    n = len(bars)
    for i in range(sma_long, n - exit_offset):
        closes_short = [b.close for b in bars[:i+1]]
        closes_long = [b.close for b in bars[:i+1]]
        sma_s = sma(closes_short, sma_short)
        sma_l = sma(closes_long, sma_long)
        if sma_s == 0 or sma_l == 0: continue
        avg_vol = sum(b.volume for b in bars[i-10:i]) / 10.0 if i >= 10 else 0
        if avg_vol <= 0: continue
        vol_ratio = bars[i].volume / avg_vol
        atr_val = atr(bars, i, 14)
        if atr_val <= 0: continue
        exit_bar = bars[i + exit_offset]
        if bars[i].close > sma_s and sma_s > sma_l and vol_ratio > vol_threshold:
            r = (exit_bar.close - bars[i].close) / atr_val
            trades.append(r)
        elif bars[i].close < sma_s and sma_s < sma_l and vol_ratio > vol_threshold:
            r = (bars[i].close - exit_bar.close) / atr_val
            trades.append(r)
    return trades

def run_wq_vol_regime(bars, short_lb=10, long_lb=20, short_th=1.4, long_th=0.8, exit_offset=5):
    trades = []
    min_bars = long_lb + exit_offset + 5
    if len(bars) < min_bars: return trades
    n = len(bars)
    for i in range(long_lb, n - exit_offset):
        short_vol = sum(bars[j].high - bars[j].low for j in range(i-short_lb, i)) / short_lb
        long_vol = sum(bars[j].high - bars[j].low for j in range(i-long_lb, i)) / long_lb
        if long_vol <= 0: continue
        vol_ratio = short_vol / long_vol
        atr_val = atr(bars, i, 14)
        if atr_val <= 0: continue
        exit_bar = bars[i + exit_offset]
        if vol_ratio > short_th:
            r = (bars[i].close - exit_bar.close) / atr_val
            trades.append(('short', r))
        elif vol_ratio < long_th:
            r = (exit_bar.close - bars[i].close) / atr_val
            trades.append(('long', r))
    return trades

def report(trades, label):
    if not trades: return f"{label}: 0 trades"
    total_r = sum(t.r_multiple if hasattr(t, 'r_multiple') else (t if isinstance(t, (int, float)) else t[1]) for t in trades)
    n = len(trades)
    wins = sum(1 for t in trades if (t.r_multiple if hasattr(t, 'r_multiple') else (t if isinstance(t, (int, float)) else t[1])) > 0)
    wr = wins / n * 100
    return f"{label}: {n} trades, {wins}/{n-wins} W/L ({wr:.1f}%), total R {total_r:+.2f}, avg R {total_r/n:+.3f}"

# ======= MAIN ANALYSIS =======

print("=" * 80)
print("DEEP STRATEGY ANALYSIS — WHAT DRIVES EDGE")
print("=" * 80)

for tf_name, csv_path in CSVS.items():
    bars = load(csv_path, "NQ")
    if not bars:
        continue
    print(f"\n--- {tf_name} ({len(bars)} NQ bars) ---")

    # 1. wq-trend-mom — base + session-gated
    base = run_wq_trend_mom(bars)
    print(f"  Base: {report(base, 'wq-trend-mom')}")

    # Session gating: NY only
    sessions = split_by_session(bars)
    for sess_name, sess_bars in sessions.items():
        if len(sess_bars) < 100: continue
        sr = run_wq_trend_mom(sess_bars)
        if sr:
            r_total = sum(sr)
            print(f"  {sess_name}: {len(sr)} trades, R {r_total:+.2f}")

    # 2. wq-vol-regime — base + split by short/long side
    vr_base = run_wq_vol_regime(bars)
    shorts = [r for (side, r) in vr_base if side == 'short']
    longs = [r for (side, r) in vr_base if side == 'long']
    if vr_base:
        r_total = sum(r for _, r in vr_base)
        r_short = sum(shorts) if shorts else 0
        r_long = sum(longs) if longs else 0
        print(f"  wq-vol-regime base: {len(vr_base)} trades, total R {r_total:+.2f}")
        print(f"    Short side (vol>th): {len(shorts)} trades, R {r_short:+.2f}")
        print(f"    Long side (vol<th): {len(longs)} trades, R {r_long:+.2f}")

        # Test: improve long side with volume confirmation
        long_fixed = []
        if len(bars) >= 35:
            for i in range(long_lb_used := 20, len(bars) - 6):
                short_vol = sum(bars[j].high - bars[j].low for j in range(i-10, i)) / 10.0
                long_vol = sum(bars[j].high - bars[j].low for j in range(i-20, i)) / 20.0
                if long_vol <= 0: continue
                vol_ratio = short_vol / long_vol
                if vol_ratio >= 0.8: continue  # not long condition
                # ADD volume confirmation: current vol > avg vol
                avg_vol_10 = sum(b.volume for b in bars[i-10:i]) / 10.0 if i >= 10 else 0
                if avg_vol_10 <= 0: continue
                vol_confirm = bars[i].volume > avg_vol_10 * 1.2  # volume must be rising
                if not vol_confirm: continue
                atr_val = atr(bars, i, 14)
                if atr_val <= 0: continue
                exit_bar = bars[i + 5]
                r = (exit_bar.close - bars[i].close) / atr_val
                long_fixed.append(r)

            if long_fixed:
                r_fixed = sum(long_fixed)
                print(f"    Long side WITH vol confirm: {len(long_fixed)} trades, R {r_fixed:+.2f} (was {r_long:+.2f})")
