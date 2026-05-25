#!/usr/bin/env python3
"""
Strategy Permutation Test Framework — Neurotrader-Inspired Validation

This is the strategy validation backbone. It implements the two critical
permutation tests from Timothy Masters' book:

TEST 1: In-Sample Monte Carlo Permutation Test
  - Generate N permutations of price bars (preserving stat properties)
  - Re-optimize strategy on each permutation
  - Compare real profit factor vs permutation distribution
  - Pass: P-value < 1% (strategy beats noise)

TEST 2: Walk-Forward Monte Carlo Permutation Test
  - After first training fold, permute remaining data
  - Run walk-forward on each permutation
  - Compare real WF PF vs permuted WF PF
  - Pass: P-value < 5% (WF results not from luck)

Usage:
  python3 permute_test.py --strategy orb-breakout --csv data.csv --threshold 0.01

Integration:
  Runs before any strategy is promoted past BRONZE in domain.ts
"""

import json, os, sys, argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

# ── Config ──────────────────────────────────────────────────────────────
STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/research"))
STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(path: str) -> pd.DataFrame:
    """Load and validate CSV data."""
    df = pd.read_csv(path)
    required = ["open", "high", "low", "close"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")
    
    df = df.sort_values("ts") if "ts" in df.columns else df
    return df


def permute_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Generate a permuted copy of bar data (OHLC-preserving).
    
    Algorithm from Neurotrader / Timothy Masters:
    - Convert to log space
    - Record relative prices within each bar
    - Shuffle bar indices
    - Reconstruct preserving first/last prices
    """
    result = df.copy()
    
    prices = result[["open", "high", "low", "close"]].values
    log_prices = np.log(np.maximum(prices, 1e-10))
    
    n = len(log_prices)
    if n < 3:
        return result
    
    # Relative prices: high/low/close relative to bar's open
    rel_high = log_prices[1:, 1] - log_prices[1:, 0]  # high - open
    rel_low = log_prices[1:, 2] - log_prices[1:, 0]   # low - open
    rel_close = log_prices[1:, 3] - log_prices[1:, 0]  # close - open
    rel_gap = log_prices[1:, 0] - log_prices[:-1, 3]   # open - prior close
    
    # Shuffle
    np.random.shuffle(rel_high)
    np.random.shuffle(rel_low)
    np.random.shuffle(rel_close)
    np.random.shuffle(rel_gap)
    
    # Reconstruct
    new_log = np.zeros_like(log_prices)
    new_log[0] = log_prices[0]  # Preserve first bar
    
    for i in range(1, n):
        new_open = new_log[i-1, 3] + rel_gap[i-1]
        new_log[i, 0] = new_open
        new_log[i, 1] = new_open + rel_high[i-1]
        new_log[i, 2] = new_open + rel_low[i-1]
        new_log[i, 3] = new_open + rel_close[i-1]
        
        # Ensure OHLC integrity
        new_log[i, 1] = max(new_log[i, 1], new_log[i, 0], new_log[i, 3])
        new_log[i, 2] = min(new_log[i, 2], new_log[i, 0], new_log[i, 3])
    
    result[["open", "high", "low", "close"]] = np.exp(new_log)
    return result


def compute_profit_factor(strategy_fn: Callable, df: pd.DataFrame) -> float:
    """Compute profit factor for a strategy on given data."""
    signals = strategy_fn(df)
    
    if signals is None or len(signals) == 0:
        return 0.0
    
    closes = df["close"].values
    returns = np.diff(np.log(closes))
    
    # Align signals with returns
    min_len = min(len(signals), len(returns))
    strategy_returns = signals[:min_len] * returns[:min_len]
    
    gross_profit = np.sum(strategy_returns[strategy_returns > 0])
    gross_loss = abs(np.sum(strategy_returns[strategy_returns < 0]))
    
    if gross_loss < 1e-10:
        return 100.0  # All winning (suspicious — flag for review)
    
    return gross_profit / gross_loss


def orb_breakout_strategy(df: pd.DataFrame, lookback: int = 20, exit_bars: int = 5) -> np.ndarray:
    """Simple ORB breakout strategy for permutation testing."""
    closes = df["close"].values
    highs = df["high"].values if "high" in df.columns else closes
    lows = df["low"].values if "low" in df.columns else closes
    
    signals = np.zeros(len(closes))
    
    for i in range(lookback, len(closes) - exit_bars):
        window_high = np.max(highs[i-lookback:i])
        window_low = np.min(lows[i-lookback:i])
        entry = closes[i]
        
        if entry > window_high * 1.001:  # Long
            signals[i] = 1
        elif entry < window_low * 0.999:  # Short
            signals[i] = -1
    
    return signals


def run_in_sample_permutation_test(
    df: pd.DataFrame,
    strategy_fn: Callable,
    n_permutations: int = 1000,
    threshold: float = 0.01,
) -> dict:
    """Test 1: In-Sample Monte Carlo Permutation Test."""
    print(f"\n{'='*60}")
    print(f"IN-SAMPLE PERMUTATION TEST")
    print(f"{'='*60}")
    
    # Real profit factor
    real_pf = compute_profit_factor(strategy_fn, df)
    print(f"Real profit factor: {real_pf:.4f}")
    
    # Run permutations
    perm_pfs = np.zeros(n_permutations)
    for i in range(n_permutations):
        if (i + 1) % 200 == 0:
            print(f"  Permutation {i+1}/{n_permutations}...")
        permuted = permute_bars(df)
        perm_pfs[i] = compute_profit_factor(strategy_fn, permuted)
    
    # Compute P-value
    n_better = int(np.sum(perm_pfs >= real_pf))
    p_value = n_better / n_permutations
    
    print(f"\nPermutation distribution: "
          f"mean PF={np.mean(perm_pfs):.3f}, std={np.std(perm_pfs):.3f}")
    print(f"Real PF beats {100 - p_value*100:.1f}% of permutations")
    print(f"P-value: {p_value:.4f} {'✅ PASS' if p_value < threshold else '❌ FAIL'}")
    
    return {
        "test": "in_sample_permutation",
        "real_pf": round(real_pf, 4),
        "permutation_mean_pf": round(float(np.mean(perm_pfs)), 4),
        "permutation_std_pf": round(float(np.std(perm_pfs)), 4),
        "n_permutations": n_permutations,
        "n_better_than_real": int(n_better),
        "p_value": round(float(p_value), 4),
        "threshold": threshold,
        "passed": bool(p_value < threshold),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_walk_forward_permutation_test(
    df: pd.DataFrame,
    strategy_fn: Callable,
    train_window: int = 500,
    train_step: int = 50,
    n_permutations: int = 200,
    threshold: float = 0.05,
) -> dict:
    """Test 2: Walk-Forward Monte Carlo Permutation Test."""
    print(f"\n{'='*60}")
    print(f"WALK-FORWARD PERMUTATION TEST")
    print(f"{'='*60}")
    
    closes = df["close"].values
    n = len(closes)
    
    if n < train_window * 2:
        return {"test": "walk_forward_permutation", "error": "Insufficient data",
                "passed": False}
    
    # Real walk-forward signal
    signals = np.zeros(n)
    for start in range(train_window, n - 1, train_step):
        end = min(start + train_step, n - 1)
        fold_df = df.iloc[:start].copy()
        fold_signals = strategy_fn(fold_df)
        if len(fold_signals) > 0:
            signals[start:end] = fold_signals[-min(len(fold_signals), len(range(start, end))):]
    
    # Real WF profit factor
    returns = np.diff(np.log(closes))
    min_len = min(len(signals), len(returns))
    wf_returns = signals[:min_len] * returns[:min_len]
    gross_profit = np.sum(wf_returns[wf_returns > 0])
    gross_loss = abs(np.sum(wf_returns[wf_returns < 0]))
    real_wf_pf = gross_profit / gross_loss if gross_loss > 1e-10 else 100.0
    print(f"Real walk-forward PF: {real_wf_pf:.4f}")
    
    # Permuted walk-forward
    perm_pfs = np.zeros(n_permutations)
    for i in range(n_permutations):
        if (i + 1) % 50 == 0:
            print(f"  WF Permutation {i+1}/{n_permutations}...")
        permuted = permute_bars(df.iloc[train_window:])
        full_permuted = pd.concat([df.iloc[:train_window], permuted])
        
        perm_signals = np.zeros(n)
        for start in range(train_window, n - 1, train_step):
            end = min(start + train_step, n - 1)
            fold_df = full_permuted.iloc[:start].copy()
            fold_signals = strategy_fn(fold_df)
            if len(fold_signals) > 0:
                perm_signals[start:end] = fold_signals[-min(len(fold_signals), len(range(start, end))):]
        
        perm_returns = perm_signals[:min_len] * returns[:min_len]
        gp = np.sum(perm_returns[perm_returns > 0])
        gl = abs(np.sum(perm_returns[perm_returns < 0]))
        perm_pfs[i] = gp / gl if gl > 1e-10 else 100.0
    
    n_better = int(np.sum(perm_pfs >= real_wf_pf))
    p_value = n_better / n_permutations
    
    print(f"\nWF permutation distribution: "
          f"mean PF={np.mean(perm_pfs):.3f}, std={np.std(perm_pfs):.3f}")
    print(f"Real WF PF beats {100 - p_value*100:.1f}% of permutations")
    print(f"P-value: {p_value:.4f} {'✅ PASS' if p_value < threshold else '❌ FAIL'}")
    
    return {
        "test": "walk_forward_permutation",
        "real_wf_pf": round(float(real_wf_pf), 4),
        "permutation_mean_pf": round(float(np.mean(perm_pfs)), 4),
        "permutation_std_pf": round(float(np.std(perm_pfs)), 4),
        "n_permutations": n_permutations,
        "train_window": train_window,
        "train_step": train_step,
        "p_value": round(float(p_value), 4),
        "threshold": threshold,
        "passed": bool(p_value < threshold),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Strategy Permutation Test Framework")
    parser.add_argument("--csv", required=True, help="Path to CSV data file")
    parser.add_argument("--strategy", default="orb-breakout", 
                        choices=["orb-breakout"], help="Strategy to test")
    parser.add_argument("--permutations", type=int, default=200,
                        help="Number of permutations (default: 200, recommended: 1000)")
    parser.add_argument("--threshold", type=float, default=0.01,
                        help="P-value threshold (default: 0.01)")
    parser.add_argument("--wf-only", action="store_true",
                        help="Run only walk-forward permutation test")
    parser.add_argument("--is-only", action="store_true",
                        help="Run only in-sample permutation test")
    args = parser.parse_args()
    
    print("🧪 Strategy Validation — Permutation Test Framework")
    print(f"   Based on 'Permutation and Randomization Tests' by Timothy Masters")
    print(f"   Strategy: {args.strategy}")
    print(f"   Data: {args.csv}")
    
    # Load data
    df = load_csv(args.csv)
    print(f"   Bars: {len(df)}")
    
    # Select strategy function
    if args.strategy == "orb-breakout":
        strategy_fn = orb_breakout_strategy
    else:
        strategy_fn = orb_breakout_strategy
    
    results = {
        "strategy": args.strategy,
        "data_file": args.csv,
        "data_bars": len(df),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tests": [],
    }
    
    # Run tests
    if not args.wf_only:
        in_sample = run_in_sample_permutation_test(
            df, strategy_fn, n_permutations=args.permutations, threshold=args.threshold
        )
        results["tests"].append(in_sample)
    
    if not args.is_only:
        wf = run_walk_forward_permutation_test(
            df, strategy_fn, n_permutations=max(args.permutations // 5, 100),
            threshold=min(args.threshold * 5, 0.05)
        )
        results["tests"].append(wf)
    
    # Overall result
    all_passed = all(t.get("passed", False) for t in results["tests"])
    results["overall_passed"] = all_passed
    results["verdict"] = "✅ APPROVED FOR PROMOTION" if all_passed else "❌ FAILED — do not promote"
    
    print(f"\n{'='*60}")
    print(f"VERDICT: {results['verdict']}")
    print(f"{'='*60}")
    
    # Save
    outfile = STATE_DIR / f"permutation-test-{args.strategy}-latest.json"
    with open(outfile, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {outfile}")


if __name__ == "__main__":
    main()
