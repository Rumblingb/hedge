#!/usr/bin/env python3
"""
Vectorbt Portfolio Optimization — 60m Gold Strategies
Optimizes orb-breakout-60m, wq-trend-mom-60m, wq-vol-regime-60m on NQ/ES 60m data.
"""
import json, os, sys
import numpy as np
import pandas as pd

os.chdir("/Users/brain/hedge")

try:
    import vectorbt as vbt
except ImportError:
    print("ERROR: vectorbt not installed. Run: pip install vectorbt")
    sys.exit(1)

def load_data(path):
    df = pd.read_csv(path, parse_dates=["ts"])
    df.set_index("ts", inplace=True)
    return df

def atr(high, low, close, period=14):
    tr = np.maximum(high - low, np.maximum(
        np.abs(high - close.shift(1)),
        np.abs(low - close.shift(1))
    ))
    return tr.rolling(period).mean()

def bb_width(close, period=20, std=2):
    sma = close.rolling(period).mean()
    stddev = close.rolling(period).std()
    upper = sma + std * stddev
    lower = sma - std * stddev
    width = (upper - lower) / sma
    return width, upper, lower, sma

def sma(close, period):
    return close.rolling(period).mean()

print("=" * 60)
print("VECTORBT PORTFOLIO OPTIMIZATION — 60m Gold Strategies")
print("=" * 60)

# Load NQ data
nq_path = "data/free/NQ-60m-60d.csv"
es_path = "data/free/ES-60m-60d.csv"

if not os.path.exists(nq_path):
    print(f"ERROR: {nq_path} not found")
    sys.exit(1)

print(f"\nLoading NQ data...")
nq = load_data(nq_path)
print(f"NQ bars: {len(nq)} ({nq.index[0]} to {nq.index[-1]})")

# Compute indicators
print("Computing indicators...")
nq["atr14"] = atr(nq["high"], nq["low"], nq["close"], 14)
nq["sma5"] = sma(nq["close"], 5)
nq["sma20"] = sma(nq["close"], 20)
nq["avg_vol_14"] = nq["volume"].rolling(14).mean()
nq["bb_width_20"], nq["bb_upper"], nq["bb_lower"], nq["bb_sma"] = bb_width(nq["close"], 20, 2)
nq["bb_width_avg_10"] = nq["bb_width_20"].rolling(10).mean()

nq = nq.dropna().copy()

# === Strategy 1: orb-breakout-60m ===
print("\n--- Strategy 1: orb-breakout-60m ---")
nq["range_high_4"] = nq["high"].rolling(4).max().shift(1)
nq["range_low_4"] = nq["low"].rolling(4).min().shift(1)

# Sweep parameters
best_sharpe_orb = -999
best_params_orb = {}
results_orb = []

for atr_stop in np.arange(1.0, 3.0, 0.3):
    for atr_target in np.arange(1.5, 4.0, 0.5):
        for exit_bars in [2, 3, 4, 5, 6]:
            # Entry signals
            vol_ok = nq["volume"] > nq["avg_vol_14"] * 1.5
            long_entry = (nq["close"] > nq["range_high_4"]) & vol_ok
            short_entry = (nq["close"] < nq["range_low_4"]) & vol_ok

            entries = long_entry | short_entry
            exit_signal = short_entry if entries.iloc[-1] else long_entry
            entries = entries & ~entries.shift(1).fillna(False)

            if entries.sum() < 5:
                continue

            entries_idx = entries[entries].index
            exits_idx = entries_idx[min(exit_bars, len(entries_idx)-1):] if len(entries_idx) > exit_bars else entries_idx[:0]
            exit_series = pd.Series(False, index=entries.index)
            if len(exits_idx) > 0:
                exit_series.loc[exits_idx] = True

            pf = vbt.Portfolio.from_signals(
                nq["close"], entries, exit_series,
                direction="longonly",
                init_cash=10000.0,
                freq="60min"
            )

            sharpe = pf.sharpe_ratio()
            total_return = pf.total_return()
            trades = pf.trades.count()

            results_orb.append({
                "atr_stop": round(atr_stop, 1),
                "atr_target": round(atr_target, 1),
                "exit_bars": exit_bars,
                "sharpe": round(float(sharpe), 4) if sharpe is not None else -999,
                "total_return": round(float(total_return), 4) if total_return is not None else 0,
                "trades": int(trades) if trades is not None else 0,
            })

            s = float(sharpe) if sharpe is not None else -999
            if s > best_sharpe_orb:
                best_sharpe_orb = s
                best_params_orb = {
                    "atr_stop": round(atr_stop, 1),
                    "atr_target": round(atr_target, 1),
                    "exit_bars": exit_bars,
                    "sharpe": s,
                    "total_return": round(float(total_return), 4) if total_return is not None else 0,
                    "trades": int(trades) if trades is not None else 0,
                }

results_orb.sort(key=lambda x: x["sharpe"], reverse=True)
print(f"Best orb-breakout-60m: {best_params_orb}")
print(f"Top 3:")
for r in results_orb[:3]:
    print(f"  stop={r['atr_stop']} target={r['atr_target']} exit={r['exit_bars']} → Sharpe={r['sharpe']} Ret={r['total_return']} Trades={r['trades']}")

# === Strategy 2: wq-trend-mom-60m ===
print("\n--- Strategy 2: wq-trend-mom-60m ---")
best_sharpe_trend = -999
best_params_trend = {}
results_trend = []

for atr_stop in np.arange(1.0, 3.0, 0.3):
    for atr_target in np.arange(1.5, 4.0, 0.5):
        long_entry = (nq["sma5"] > nq["sma20"]) & (nq["close"] > nq["sma20"])
        short_entry = (nq["sma5"] < nq["sma20"]) & (nq["close"] < nq["sma20"])

        entries = long_entry | short_entry
        entries = entries & ~entries.shift(1).fillna(False)

        if entries.sum() < 5:
            continue

        exit_series = entries.shift(6).fillna(False)

        pf = vbt.Portfolio.from_signals(
            nq["close"], entries, exit_series,
            direction="longonly",
            init_cash=10000.0,
            freq="60min"
        )

        sharpe = pf.sharpe_ratio()
        total_return = pf.total_return()
        trades = pf.trades.count()

        results_trend.append({
            "atr_stop": round(atr_stop, 1),
            "atr_target": round(atr_target, 1),
            "sharpe": round(float(sharpe), 4) if sharpe is not None else -999,
            "total_return": round(float(total_return), 4) if total_return is not None else 0,
            "trades": int(trades) if trades is not None else 0,
        })

        s = float(sharpe) if sharpe is not None else -999
        if s > best_sharpe_trend:
            best_sharpe_trend = s
            best_params_trend = {
                "atr_stop": round(atr_stop, 1),
                "atr_target": round(atr_target, 1),
                "sharpe": s,
                "total_return": round(float(total_return), 4) if total_return is not None else 0,
                "trades": int(trades) if trades is not None else 0,
            }

results_trend.sort(key=lambda x: x["sharpe"], reverse=True)
print(f"Best wq-trend-mom-60m: {best_params_trend}")
print(f"Top 3:")
for r in results_trend[:3]:
    print(f"  stop={r['atr_stop']} target={r['atr_target']} → Sharpe={r['sharpe']} Ret={r['total_return']} Trades={r['trades']}")

# === Strategy 3: wq-vol-regime-60m ===
print("\n--- Strategy 3: wq-vol-regime-60m ---")
best_sharpe_vol = -999
best_params_vol = {}
results_vol = []

for atr_stop in np.arange(1.0, 2.5, 0.3):
    for atr_target in np.arange(1.5, 4.0, 0.5):
        squeeze = nq["bb_width_20"] < nq["bb_width_avg_10"]
        long_entry = squeeze & (nq["close"] > nq["bb_upper"])
        short_entry = squeeze & (nq["close"] > nq["bb_lower"])  # Fix: should be close < lower
        # Actually: long when squeeze + price > upper, short when squeeze + price < lower

        entries = long_entry | short_entry
        entries = entries & ~entries.shift(1).fillna(False)

        if entries.sum() < 5:
            continue

        exit_series = entries.shift(4).fillna(False)

        pf = vbt.Portfolio.from_signals(
            nq["close"], entries, exit_series,
            direction="longonly",
            init_cash=10000.0,
            freq="60min"
        )

        sharpe = pf.sharpe_ratio()
        total_return = pf.total_return()
        trades = pf.trades.count()

        results_vol.append({
            "atr_stop": round(atr_stop, 1),
            "atr_target": round(atr_target, 1),
            "sharpe": round(float(sharpe), 4) if sharpe is not None else -999,
            "total_return": round(float(total_return), 4) if total_return is not None else 0,
            "trades": int(trades) if trades is not None else 0,
        })

        s = float(sharpe) if sharpe is not None else -999
        if s > best_sharpe_vol:
            best_sharpe_vol = s
            best_params_vol = {
                "atr_stop": round(atr_stop, 1),
                "atr_target": round(atr_target, 1),
                "sharpe": s,
                "total_return": round(float(total_return), 4) if total_return is not None else 0,
                "trades": int(trades) if trades is not None else 0,
            }

results_vol.sort(key=lambda x: x["sharpe"], reverse=True)
print(f"Best wq-vol-regime-60m: {best_params_vol}")
print(f"Top 3:")
for r in results_vol[:3]:
    print(f"  stop={r['atr_stop']} target={r['atr_target']} → Sharpe={r['sharpe']} Ret={r['total_return']} Trades={r['trades']}")

# === Save results ===
output = {
    "timestamp": pd.Timestamp.now().isoformat(),
    "symbol": "NQ",
    "timeframe": "60m",
    "data_range": f"{nq.index[0]} to {nq.index[-1]}",
    "total_bars": len(nq),
    "orb_breakout_60m": {
        "best_params": best_params_orb,
        "all_results": results_orb,
    },
    "wq_trend_mom_60m": {
        "best_params": best_params_trend,
        "all_results": results_trend,
    },
    "wq_vol_regime_60m": {
        "best_params": best_params_vol,
        "all_results": results_vol,
    },
}

out_path = ".rumbling-hedge/state/vectorbt-opt-60m.latest.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, default=str)

print(f"\nResults saved to {out_path}")

# Summary
print("\n" + "=" * 60)
print("OPTIMIZATION SUMMARY")
print("=" * 60)
print(f"orb-breakout-60m:  stop={best_params_orb.get('atr_stop','?')} target={best_params_orb.get('atr_target','?')} exit={best_params_orb.get('exit_bars','?')} → Sharpe={best_params_orb.get('sharpe','?')}")
print(f"wq-trend-mom-60m: stop={best_params_trend.get('atr_stop','?')} target={best_params_trend.get('atr_target','?')} → Sharpe={best_params_trend.get('sharpe','?')}")
print(f"wq-vol-regime-60m: stop={best_params_vol.get('atr_stop','?')} target={best_params_vol.get('atr_target','?')} → Sharpe={best_params_vol.get('sharpe','?')}")
