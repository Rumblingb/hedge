#!/usr/bin/env python3
"""Parameter sweep for top 3 strategies on best timeframes.

Usage: python3 scripts/param_sweep.py [--symbol NQ] [--csv <path>] [--strategy <name>]

Omitting --strategy runs all three sweeps.
"""

import csv
import sys
import argparse
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Bar:
    ts: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int

def load_csv(path: str, target_symbol: str) -> List[Bar]:
    bars = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row['symbol'].strip().upper()
            if target_symbol != 'ALL' and sym != target_symbol:
                continue
            bars.append(Bar(
                ts=row['ts'].strip(),
                symbol=sym,
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=int(row['volume']),
            ))
    # Deduplicate by symbol (keep first symbol encountered, which is fine for single-symbol sweeps)
    return bars

def sma(values, period):
    if len(values) < period:
        return 0.0
    return sum(values[-period:]) / period

def report(trades, label):
    if not trades:
        return (0, 0.0, 0.0, 0)
    total_r = sum(t.r_multiple for t in trades)
    wins = sum(1 for t in trades if t.r_multiple > 0)
    total = len(trades)
    wr = wins / total * 100 if total > 0 else 0
    return (total, total_r, wr, wins)

def fmt_results(label, trades):
    total, total_r, wr, wins = report(trades, label)
    losses = total - wins
    return f"  {label}: {total} trades, {wins}/{losses} W/L ({wr:.1f}%), total R {total_r:.2f}"

# ========== SWEEP FUNCTIONS ==========

@dataclass
class TradeResult:
    strategy_id: str
    side: str
    entry: float
    exit: float
    r_multiple: float
    params: dict

def sweep_orb_breakout(bars: List[Bar]) -> List[Tuple[dict, List[TradeResult]]]:
    """Sweep: range_window (8,10,12,14,16,20) × vol_threshold (1.3,1.5,2.0) × exit_offset (3,5,8)"""
    results = []
    n = len(bars)
    if n < 22:
        return results

    for range_window in [8, 10, 12, 14, 16, 20]:
        for vol_threshold in [1.3, 1.5, 2.0]:
            for exit_offset in [3, 5, 8]:
                trades = []
                for i in range(range_window + 2, n - exit_offset):
                    range_high = max(b.high for b in bars[i-range_window:i])
                    range_low = min(b.low for b in bars[i-range_window:i])
                    range_val = range_high - range_low
                    if range_val <= 0:
                        continue

                    # avg volume over last 10 bars
                    avg_vol_window = 10
                    if i < avg_vol_window:
                        continue
                    avg_vol = sum(b.volume for b in bars[i-avg_vol_window:i]) / avg_vol_window
                    if avg_vol <= 0:
                        continue

                    bar = bars[i]
                    exit_bar = bars[i + exit_offset]
                    atr_val = sum(b.high - b.low for b in bars[i-14:i]) / 14.0
                    if atr_val <= 0:
                        continue

                    if bar.close > range_high and bar.volume > avg_vol * vol_threshold:
                        r = (exit_bar.close - bar.close) / atr_val
                        trades.append(TradeResult("orb-breakout", "long", bar.close, exit_bar.close, r, {}))
                    elif bar.close < range_low and bar.volume > avg_vol * vol_threshold:
                        r = (bar.close - exit_bar.close) / atr_val
                        trades.append(TradeResult("orb-breakout", "short", bar.close, exit_bar.close, r, {}))

                params = {"range": range_window, "vol_thr": vol_threshold, "exit": exit_offset}
                results.append(({**params, "label": f"r{range_window} v{vol_threshold} e{exit_offset}"}, trades))
    return results

def sweep_wq_trend_mom(bars: List[Bar]) -> List[Tuple[dict, List[TradeResult]]]:
    """Sweep: sma_short (10,15,20,30) × sma_long (30,40,50,60) × vol_threshold (1.3,1.5) × exit_offset (3,5,8)"""
    results = []
    n = len(bars)
    if n < 70:
        return results

    for sma_short in [10, 15, 20, 30]:
        for sma_long in [30, 40, 50, 60]:
            if sma_long <= sma_short:
                continue  # long must be > short
            for vol_threshold in [1.3, 1.5]:
                for exit_offset in [3, 5, 8]:
                    trades = []
                    min_lookback = max(sma_long, sma_short) + 5
                    for i in range(min_lookback, n - exit_offset):
                        # Compute SMAs
                        closes = [b.close for b in bars[:i+1]]
                        sma_s = sma(closes, sma_short)
                        sma_l = sma(closes, sma_long)
                        if sma_s == 0 or sma_l == 0:
                            continue

                        avg_vol_window = 10
                        if i < avg_vol_window:
                            continue
                        avg_vol = sum(b.volume for b in bars[i-avg_vol_window:i]) / avg_vol_window
                        if avg_vol <= 0:
                            continue

                        vol_ratio = bars[i].volume / avg_vol
                        atr_val = sum(b.high - b.low for b in bars[i-14:i]) / 14.0
                        if atr_val <= 0:
                            continue

                        exit_bar = bars[i + exit_offset]

                        if bars[i].close > sma_s and sma_s > sma_l and vol_ratio > vol_threshold:
                            r = (exit_bar.close - bars[i].close) / atr_val
                            trades.append(TradeResult("wq-trend-mom", "long", bars[i].close, exit_bar.close, r, {}))
                        elif bars[i].close < sma_s and sma_s < sma_l and vol_ratio > vol_threshold:
                            r = (bars[i].close - exit_bar.close) / atr_val
                            trades.append(TradeResult("wq-trend-mom", "short", bars[i].close, exit_bar.close, r, {}))

                    params = {"s": sma_short, "l": sma_long, "v": vol_threshold, "e": exit_offset}
                    results.append(({**params, "label": f"s{sma_short} l{sma_long} v{vol_threshold} e{exit_offset}"}, trades))
    return results

def sweep_wq_vol_regime(bars: List[Bar]) -> List[Tuple[dict, List[TradeResult]]]:
    """Sweep: short_lookback (5,10,15,20) × long_lookback (20,30,40,50) × short_threshold (1.3,1.4,1.5,1.6,1.7,2.0) × long_threshold (0.5,0.6,0.7,0.8,0.9)"""
    results = []
    n = len(bars)
    if n < 55:
        return results

    for short_lookback in [5, 10, 15, 20]:
        for long_lookback in [20, 30, 40, 50]:
            if short_lookback >= long_lookback:
                continue
            for short_threshold in [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]:
                for long_threshold in [0.5, 0.6, 0.7, 0.8, 0.9]:
                    trades = []
                    min_lookback = long_lookback + 5
                    for i in range(min_lookback, n - 5):  # exit_offset=5 for all
                        short_vol = sum(b.high - b.low for b in bars[i-short_lookback:i]) / short_lookback
                        long_vol = sum(b.high - b.low for b in bars[i-long_lookback:i]) / long_lookback
                        if long_vol <= 0:
                            continue
                        vol_ratio = short_vol / long_vol
                        atr_val = sum(b.high - b.low for b in bars[i-14:i]) / 14.0
                        if atr_val <= 0:
                            continue

                        exit_bar = bars[i + 5]

                        if vol_ratio > short_threshold:
                            r = (bars[i].close - exit_bar.close) / atr_val
                            trades.append(TradeResult("wq-vol-regime", "short", bars[i].close, exit_bar.close, r, {}))
                        elif vol_ratio < long_threshold:
                            r = (exit_bar.close - bars[i].close) / atr_val
                            trades.append(TradeResult("wq-vol-regime", "long", bars[i].close, exit_bar.close, r, {}))

                    params = {"sl": short_lookback, "ll": long_lookback, "st": short_threshold, "lt": long_threshold}
                    results.append(({**params, "label": f"s{short_lookback} l{long_lookback} S{short_threshold} L{long_threshold}"}, trades))
    return results


def run_sweep(name: str, csv_path: str, symbol: str, sweep_fn, bars: List[Bar]):
    print(f"\n{'='*70}")
    print(f"=== SWEEP: {name} ===")
    print(f"CSV: {csv_path}")
    print(f"Symbol: {symbol}")
    print(f"Bars: {len(bars)}")
    print(f"{'='*70}\n")

    results = sweep_fn(bars)
    if not results:
        print("  No results (not enough bars)")
        return

    # Compute stats and sort by total R descending
    scored = []
    for params, trades in results:
        if not trades:
            scored.append((params, 0, 0.0, 0.0, 0))
            continue
        total, total_r, wr, wins = report(trades, "")
        scored.append((params, total, total_r, wr, wins))

    scored.sort(key=lambda x: x[2], reverse=True)

    # Print top 20
    print(f"  {'Label':<40} {'Trades':>6} {'Wins':>5} {'Loss':>5} {'WR%':>7} {'TotalR':>10}")
    print(f"  {'-'*40} {'-'*6} {'-'*5} {'-'*5} {'-'*7} {'-'*10}")
    for params, total, total_r, wr, wins in scored[:20]:
        losses = total - wins
        label = params['label']
        print(f"  {label:<40} {total:>6} {wins:>5} {losses:>5} {wr:>6.1f}% {total_r:>10.2f}")

    print(f"\n  --- Best 5 ---")
    for params, total, total_r, wr, wins in scored[:5]:
        print(f"  {params['label']}: {total}R={total_r:.2f}, {wr:.1f}% WR, {total} trades")

    print(f"\n  --- Worst 5 ---")
    for params, total, total_r, wr, wins in scored[-5:]:
        print(f"  {params['label']}: {total}R={total_r:.2f}, {wr:.1f}% WR, {total} trades")

    # Return top 5 for summary
    return scored[:5]


def main():
    parser = argparse.ArgumentParser(description="Parameter sweep for trading strategies")
    parser.add_argument("--symbol", default="NQ", help="Symbol to filter (default: NQ)")
    parser.add_argument("--strategy", default=None, help="Strategy to sweep: orb-breakout, wq-trend-mom, wq-vol-regime")
    args = parser.parse_args()

    sweeps = [
        ("wq-vol-regime (60m)", "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv", sweep_wq_vol_regime),
        ("wq-trend-mom (30m)", "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv", sweep_wq_trend_mom),
        ("orb-breakout (15m)", "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv", sweep_orb_breakout),
        ("orb-breakout (30m)", "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv", sweep_orb_breakout),
    ]

    if args.strategy:
        strat_filter = args.strategy
        sweeps = [(n, p, f) for n, p, f in sweeps if strat_filter in n]

    all_best = {}

    for name, csv_path, sweep_fn in sweeps:
        bars = load_csv(csv_path, args.symbol)
        if not bars:
            print(f"\n[SKIP] {name}: No data for {args.symbol}")
            continue

        # Count NQ bars
        nq_bars = [b for b in bars if b.symbol == args.symbol]
        if not nq_bars:
            print(f"\n[SKIP] {name}: No {args.symbol} bars found")
            continue

        top5 = run_sweep(name, csv_path, args.symbol, sweep_fn, bars)
        all_best[name] = top5

    print(f"\n{'='*70}")
    print(f"=== SUMMARY OF BEST PARAMETERS ===")
    print(f"{'='*70}")
    for name, top5 in all_best.items():
        if top5:
            print(f"\n{name}:")
            for params, total, total_r, wr, wins in top5[:3]:
                print(f"  {params['label']}: {total}R={total_r:.2f}, {wr:.1f}% WR, {total} trades")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
