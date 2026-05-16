#!/usr/bin/env python3
"""
Parameter sweep for the 3 top-performing strategies.
Replicates exact Rust strategy logic from full_strategy_pipeline.rs.
Runs sweeps on the best timeframe for each strategy.
"""

import csv
import sys
import os
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class Bar:
    ts: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class Trade:
    strategy_id: str
    side: str
    entry: float
    exit: float
    entry_ts: str
    exit_ts: str
    r_multiple: float

def load_csv(path: str, target_symbol: str) -> List[Bar]:
    bars = []
    with open(path) as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) >= 7:
                symbol = row[1].strip().upper()
                if target_symbol == "ALL" or symbol == target_symbol:
                    bars.append(Bar(
                        ts=row[0].strip(),
                        symbol=symbol,
                        open=float(row[2]),
                        high=float(row[3]),
                        low=float(row[4]),
                        close=float(row[5]),
                        volume=int(row[6]),
                    ))
    return bars

def avg_vol_window(bars: List[Bar], idx: int, window: int) -> float:
    if idx < window:
        return 0.0
    return sum(b.volume for b in bars[idx-window:idx]) / window

def sma(bars: List[Bar], idx: int, period: int) -> float:
    """SMA of close prices up to and including idx."""
    if idx + 1 < period:
        return 0.0
    return sum(bars[i].close for i in range(idx+1-period, idx+1)) / period

def atr(bars: List[Bar], idx: int, period: int) -> float:
    """ATR over period bars BEFORE idx (not including idx). Matches Rust bars[i-period..i]."""
    if idx < period:
        return 0.0
    return sum(bars[i].high - bars[i].low for i in range(idx-period, idx)) / period


# === STRATEGY: ORB Breakout ===
def run_orb_breakout(bars: List[Bar], range_window: int, vol_threshold: float, exit_offset: int) -> List[Trade]:
    n = len(bars)
    trades = []
    for i in range(range_window, n - exit_offset):
        range_high = max(b.high for b in bars[0:range_window])
        range_low = min(b.low for b in bars[0:range_window])
        range_sz = range_high - range_low
        if range_sz <= 0:
            continue
        atr_val = atr(bars, i, 14)
        if atr_val <= 0:
            continue
        exit_bar = bars[i + exit_offset]
        exit_price = exit_bar.close
        avg_v = avg_vol_window(bars, i, 10)
        if bars[i].close > range_high and bars[i].volume > avg_v * vol_threshold:
            r = (exit_price - bars[i].close) / atr_val
            trades.append(Trade("orb-breakout", "long", bars[i].close, exit_price, bars[i].ts, exit_bar.ts, r))
        elif bars[i].close < range_low and bars[i].volume > avg_v * vol_threshold:
            r = (bars[i].close - exit_price) / atr_val
            trades.append(Trade("orb-breakout", "short", bars[i].close, exit_price, bars[i].ts, exit_bar.ts, r))
    return trades


# === STRATEGY: WQ Trend Momentum ===
def run_wq_trend_mom(bars: List[Bar], sma_short: int, sma_long: int, vol_threshold: float, exit_offset: int) -> List[Trade]:
    n = len(bars)
    trades = []
    required = max(sma_long, 40)
    for i in range(required, n - exit_offset):
        sma_s = sma(bars, i, sma_short)
        sma_l = sma(bars, i, sma_long)
        avg_v = avg_vol_window(bars, i, 10)
        if avg_v <= 0:
            continue
        vol_ratio = bars[i].volume / avg_v
        atr_val = atr(bars, i, 14)
        if atr_val <= 0:
            continue
        exit_bar = bars[i + exit_offset]
        exit_price = exit_bar.close
        if bars[i].close > sma_s and sma_s > sma_l and vol_ratio > vol_threshold:
            r = (exit_price - bars[i].close) / atr_val
            trades.append(Trade("wq-trend-mom", "long", bars[i].close, exit_price, bars[i].ts, exit_bar.ts, r))
        elif bars[i].close < sma_s and sma_s < sma_l and vol_ratio > vol_threshold:
            r = (bars[i].close - exit_price) / atr_val
            trades.append(Trade("wq-trend-mom", "short", bars[i].close, exit_price, bars[i].ts, exit_bar.ts, r))
    return trades


# === STRATEGY: WQ Vol Regime ===
def run_wq_vol_regime(bars: List[Bar], short_lookback: int, long_lookback: int, short_threshold: float, long_threshold: float, exit_offset: int) -> List[Trade]:
    n = len(bars)
    trades = []
    required = max(long_lookback, 30)
    for i in range(required, n - exit_offset):
        short_vol = sum(bars[j].high - bars[j].low for j in range(i-short_lookback, i)) / short_lookback
        long_vol = sum(bars[j].high - bars[j].low for j in range(i-long_lookback, i)) / long_lookback
        if long_vol <= 0:
            continue
        vol_ratio = short_vol / long_vol
        atr_val = atr(bars, i, 14)
        if atr_val <= 0:
            continue
        exit_bar = bars[i + exit_offset]
        exit_price = exit_bar.close
        if vol_ratio > short_threshold:
            r = (bars[i].close - exit_price) / atr_val
            trades.append(Trade("wq-vol-regime", "short", bars[i].close, exit_price, bars[i].ts, exit_bar.ts, r))
        elif vol_ratio < long_threshold:
            r = (exit_price - bars[i].close) / atr_val
            trades.append(Trade("wq-vol-regime", "long", bars[i].close, exit_price, bars[i].ts, exit_bar.ts, r))
    return trades


def report(trades: List[Trade]) -> Tuple[int, int, int, float, float]:
    if not trades:
        return (0, 0, 0, 0.0, 0.0)
    total_r = sum(t.r_multiple for t in trades)
    wins = sum(1 for t in trades if t.r_multiple > 0)
    losses = len(trades) - wins
    wr = wins / len(trades) * 100.0
    return (len(trades), wins, losses, wr, total_r)


def sweep_strategy(name: str, bars: List[Bar], param_grid: List[dict], csv_timeframe: str):
    print(f"\n=== {name.upper()} SWEEP on {csv_timeframe} ({len(bars)} bars) ===")
    results = []
    for params in param_grid:
        if name == "orb-breakout":
            trades = run_orb_breakout(bars, params['rw'], params['vt'], params['eo'])
        elif name == "wq-trend-mom":
            trades = run_wq_trend_mom(bars, params['ss'], params['sl'], params['vt'], params['eo'])
        elif name == "wq-vol-regime":
            trades = run_wq_vol_regime(bars, params['sll'], params['lll'], params['st'], params['lt'], params['eo'])
        else:
            continue
        cnt, wins, losses, wr, total_r = report(trades)
        results.append((total_r, cnt, wins, losses, wr, params))

    results.sort(key=lambda x: x[0], reverse=True)

    # Print header
    if name == "orb-breakout":
        print(f"{'rw':>4} {'vt':>5} {'eo':>3} | {'Trades':>6} {'W/L':>8} {'WR':>6} {'Total R':>8}")
        print("-" * 45)
        for total_r, cnt, wins, losses, wr, p in results[:15]:
            print(f"{p['rw']:>4} {p['vt']:>5.1f} {p['eo']:>3} | {cnt:>6} {wins}/{losses:<3} {wr:>5.1f}% {total_r:>8.2f}")
    elif name == "wq-trend-mom":
        print(f"{'ss':>4} {'sl':>4} {'vt':>5} {'eo':>3} | {'Trades':>6} {'W/L':>8} {'WR':>6} {'Total R':>8}")
        print("-" * 52)
        for total_r, cnt, wins, losses, wr, p in results[:15]:
            print(f"{p['ss']:>4} {p['sl']:>4} {p['vt']:>5.1f} {p['eo']:>3} | {cnt:>6} {wins}/{losses:<3} {wr:>5.1f}% {total_r:>8.2f}")
    elif name == "wq-vol-regime":
        print(f"{'sll':>4} {'lll':>4} {'st':>5} {'lt':>5} {'eo':>3} | {'Trades':>6} {'W/L':>8} {'WR':>6} {'Total R':>8}")
        print("-" * 60)
        for total_r, cnt, wins, losses, wr, p in results[:15]:
            print(f"{p['sll']:>4} {p['lll']:>4} {p['st']:>5.1f} {p['lt']:>5.1f} {p['eo']:>3} | {cnt:>6} {wins}/{losses:<3} {wr:>5.1f}% {total_r:>8.2f}")

    print(f"\nTop-1: {results[0][-1]} → {results[0][0]:.2f}R, {results[0][3]:.1f}% WR, {results[0][1]} trades")
    print(f"Combos tested: {len(param_grid)}")
    return results


def main():
    data_dir = "/Users/brain/hedge/data/free"

    # =========================================================
    # 1. ORB-BREAKOUT on 15m and 30m
    # =========================================================
    for tf in ["15m", "30m"]:
        csv_path = f"{data_dir}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-{tf}.csv"
        bars = load_csv(csv_path, "NQ")
        if not bars:
            print(f"No NQ bars found in {csv_path}")
            continue

        rw_vals = [8, 10, 12, 14, 16, 20]
        vt_vals = [1.3, 1.5, 2.0]
        eo_vals = [3, 5, 8]
        param_grid = [{"rw": r, "vt": v, "eo": e} for r in rw_vals for v in vt_vals for e in eo_vals]
        sweep_strategy("orb-breakout", bars, param_grid, tf)

    # =========================================================
    # 2. WQ-TREND-MOM on 30m
    # =========================================================
    tf = "30m"
    csv_path = f"{data_dir}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-{tf}.csv"
    bars = load_csv(csv_path, "NQ")
    if bars:
        ss_vals = [10, 15, 20, 30]
        sl_vals = [30, 40, 50, 60]
        vt_vals = [1.3, 1.5]
        eo_vals = [3, 5, 8]
        param_grid = [{"ss": s, "sl": l, "vt": v, "eo": e} for s in ss_vals for l in sl_vals for v in vt_vals for e in eo_vals]
        sweep_strategy("wq-trend-mom", bars, param_grid, tf)
    else:
        print(f"No NQ bars found in {csv_path}")

    # =========================================================
    # 3. WQ-VOL-REGIME on 60m (as requested) + 30m (for comparison)
    # =========================================================
    for tf in ["60m", "30m"]:
        csv_path = f"{data_dir}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-{tf}.csv"
        bars = load_csv(csv_path, "NQ")
        if not bars:
            print(f"No NQ bars found in {csv_path}")
            continue

        sll_vals = [5, 10, 15, 20]
        lll_vals = [20, 30, 40, 50]
        st_vals = [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]
        lt_vals = [0.5, 0.6, 0.7, 0.8, 0.9]
        eo_vals = [3, 5, 8]
        param_grid = [{"sll": s, "lll": l, "st": st, "lt": lt, "eo": e} for s in sll_vals for l in lll_vals for st in st_vals for lt in lt_vals for e in eo_vals]
        sweep_strategy("wq-vol-regime", bars, param_grid, tf)


if __name__ == "__main__":
    main()
