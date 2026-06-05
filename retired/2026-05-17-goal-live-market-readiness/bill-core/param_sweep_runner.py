#!/usr/bin/env python3
"""Run full parameter sweeps for top strategies on their best timeframes.

Usage: python3 param_sweep_runner.py
"""
import subprocess
import sys
import os
from datetime import datetime

CARGO = "/Users/brain/.cargo/bin/cargo"
WORKDIR = "/Users/brain/hedge/bill-core"
DATA_DIR = "/Users/brain/hedge/bill-core/../data/free"

CSV_MAP = {
    "15m": os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv"),
    "30m": os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv"),
    "60m": os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv"),
    "5m": os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-5m.csv"),
    "daily": os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1d-5y.csv"),
}

def run_sweep(csv_path, strategy, params, label):
    """Run a single param_sweep instance and return stdout."""
    cmd = [
        CARGO, "run", "--bin", "param_sweep", "--release", "--",
        csv_path,
        "--strategy", strategy,
        "--symbol", "NQ",
    ]
    for k, v in params.items():
        cmd.extend([f"--{k}", str(v)])
    
    result = subprocess.run(cmd, cwd=WORKDIR, capture_output=True, text=True, timeout=120)
    lines = [l for l in result.stdout.split('\n') if l.strip() and not l.startswith('Compiling') and not l.startswith('   Compil') and not l.startswith('warning') and not l.startswith('    Finished')]
    output = '\n'.join(lines)
    # Extract the result line
    result_line = ""
    for line in lines:
        if "trades" in line:
            result_line = line.strip()
    return result_line or output.strip()

def main():
    results = []
    results.append(f"# Parameter Sweep Results — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    results.append("")
    results.append("## Baseline Reference (Current Default Parameters)")
    results.append("")
    
    # First, get baseline for all strategies on all relevant timeframes
    print("=== Running baseline references ===")
    for tf in ["15m", "30m", "60m"]:
        for strat in ["orb-breakout", "wq-trend-mom", "wq-vol-regime"]:
            label = f"{strat} on {tf}"
            print(f"  Baseline: {label}...")
            try:
                out = run_sweep(CSV_MAP[tf], strat, {}, label)
                results.append(f"- **{label}**: {out}")
                print(f"    -> {out}")
            except Exception as e:
                results.append(f"- **{label}**: ERROR - {e}")
                print(f"    -> ERROR: {e}")
    
    results.append("")
    results.append("---")
    results.append("")
    
    # =========================================================
    # SWEEP 1: orb-breakout on 15m and 30m
    # =========================================================
    print("\n=== SWEEP 1: orb-breakout (15m + 30m) ===")
    results.append("## 1. orb-breakout Parameter Sweep")
    results.append("")
    results.append("**Best timeframe: 15m and 30m**")
    results.append("")
    results.append("### 1a. Range Window Sweep (vol_threshold=1.3, exit_offset=8)")
    results.append("")
    
    for tf in ["15m", "30m"]:
        results.append(f"**{tf}:**")
        for rw in [8, 10, 12, 14, 16, 20]:
            label = f"orb-breakout/{tf} rw={rw}"
            print(f"  {label}...")
            out = run_sweep(CSV_MAP[tf], "orb-breakout", {"range-window": rw, "vol-threshold": 1.3, "exit-offset": 8}, label)
            results.append(f"  - rw={rw}: {out}")
            print(f"    -> {out}")
        results.append("")
    
    results.append("### 1b. Volume Threshold Sweep (range_window=12, exit_offset=8)")
    results.append("")
    for tf in ["15m", "30m"]:
        results.append(f"**{tf}:**")
        for vt in [1.3, 1.5, 2.0]:
            label = f"orb-breakout/{tf} vt={vt}"
            print(f"  {label}...")
            out = run_sweep(CSV_MAP[tf], "orb-breakout", {"range-window": 12, "vol-threshold": vt, "exit-offset": 8}, label)
            results.append(f"  - vt={vt}: {out}")
            print(f"    -> {out}")
        results.append("")
    
    results.append("### 1c. Exit Bar Offset Sweep (range_window=12, vol_threshold=1.3)")
    results.append("")
    for tf in ["15m", "30m"]:
        results.append(f"**{tf}:**")
        for ex in [3, 5, 8]:
            label = f"orb-breakout/{tf} ex={ex}"
            print(f"  {label}...")
            out = run_sweep(CSV_MAP[tf], "orb-breakout", {"range-window": 12, "vol-threshold": 1.3, "exit-offset": ex}, label)
            results.append(f"  - exit_offset={ex}: {out}")
            print(f"    -> {out}")
        results.append("")
    
    # =========================================================
    # SWEEP 2: wq-trend-mom on 30m
    # =========================================================
    print("\n=== SWEEP 2: wq-trend-mom (30m) ===")
    results.append("## 2. wq-trend-mom Parameter Sweep")
    results.append("")
    results.append("**Best timeframe: 30m (+166R)**")
    results.append("")
    results.append("### 2a. SMA Short Period Sweep (sma_long=50, vol_threshold=1.3, exit_offset=8)")
    results.append("")
    
    for ss in [10, 15, 20, 30]:
        label = f"wq-trend-mom/30m ss={ss}"
        print(f"  {label}...")
        out = run_sweep(CSV_MAP["30m"], "wq-trend-mom", {"sma-short": ss, "sma-long": 50, "vol-threshold": 1.3, "exit-offset": 8}, label)
        results.append(f"  - sma_short={ss}: {out}")
        print(f"    -> {out}")
    results.append("")
    
    results.append("### 2b. SMA Long Period Sweep (sma_short=20, vol_threshold=1.3, exit_offset=8)")
    results.append("")
    for sl in [30, 40, 50, 60]:
        label = f"wq-trend-mom/30m sl={sl}"
        print(f"  {label}...")
        out = run_sweep(CSV_MAP["30m"], "wq-trend-mom", {"sma-short": 20, "sma-long": sl, "vol-threshold": 1.3, "exit-offset": 8}, label)
        results.append(f"  - sma_long={sl}: {out}")
        print(f"    -> {out}")
    results.append("")
    
    results.append("### 2c. Volume Threshold Sweep (sma_short=20, sma_long=50, exit_offset=8)")
    results.append("")
    for vt in [1.3, 1.5]:
        label = f"wq-trend-mom/30m vt={vt}"
        print(f"  {label}...")
        out = run_sweep(CSV_MAP["30m"], "wq-trend-mom", {"sma-short": 20, "sma-long": 50, "vol-threshold": vt, "exit-offset": 8}, label)
        results.append(f"  - vt={vt}: {out}")
        print(f"    -> {out}")
    results.append("")
    
    results.append("### 2d. Exit Offset Sweep (sma_short=20, sma_long=50, vol_threshold=1.3)")
    results.append("")
    for ex in [3, 5, 8]:
        label = f"wq-trend-mom/30m ex={ex}"
        print(f"  {label}...")
        out = run_sweep(CSV_MAP["30m"], "wq-trend-mom", {"sma-short": 20, "sma-long": 50, "vol-threshold": 1.3, "exit-offset": ex}, label)
        results.append(f"  - exit_offset={ex}: {out}")
        print(f"    -> {out}")
    results.append("")
    
    # =========================================================
    # SWEEP 3: wq-vol-regime on 60m
    # =========================================================
    print("\n=== SWEEP 3: wq-vol-regime (60m) ===")
    results.append("## 3. wq-vol-regime Parameter Sweep")
    results.append("")
    results.append("**Best timeframe: 60m (+130R)**")
    results.append("")
    results.append("### 3a. Short Vol Lookback Sweep (long_lookback=30, short_threshold=1.5, long_threshold=0.7, exit_offset=5)")
    results.append("")
    
    for slk in [5, 10, 15, 20]:
        label = f"wq-vol-regime/60m slk={slk}"
        print(f"  {label}...")
        out = run_sweep(CSV_MAP["60m"], "wq-vol-regime", {"short-lookback": slk, "long-lookback": 30, "short-threshold": 1.5, "long-threshold": 0.7, "exit-offset": 5}, label)
        results.append(f"  - short_lookback={slk}: {out}")
        print(f"    -> {out}")
    results.append("")
    
    results.append("### 3b. Long Vol Lookback Sweep (short_lookback=10, short_threshold=1.5, long_threshold=0.7, exit_offset=5)")
    results.append("")
    for llk in [20, 30, 40, 50]:
        label = f"wq-vol-regime/60m llk={llk}"
        print(f"  {label}...")
        out = run_sweep(CSV_MAP["60m"], "wq-vol-regime", {"short-lookback": 10, "long-lookback": llk, "short-threshold": 1.5, "long-threshold": 0.7, "exit-offset": 5}, label)
        results.append(f"  - long_lookback={llk}: {out}")
        print(f"    -> {out}")
    results.append("")
    
    results.append("### 3c. Short Threshold (Short Entry) Sweep (short_lookback=10, long_lookback=30, long_threshold=0.7, exit_offset=5)")
    results.append("")
    for st in [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]:
        label = f"wq-vol-regime/60m st={st}"
        print(f"  {label}...")
        out = run_sweep(CSV_MAP["60m"], "wq-vol-regime", {"short-lookback": 10, "long-lookback": 30, "short-threshold": st, "long-threshold": 0.7, "exit-offset": 5}, label)
        results.append(f"  - short_threshold={st}: {out}")
        print(f"    -> {out}")
    results.append("")
    
    results.append("### 3d. Long Threshold (Long Entry) Sweep (short_lookback=10, long_lookback=30, short_threshold=1.5, exit_offset=5)")
    results.append("")
    for lt in [0.5, 0.6, 0.7, 0.8, 0.9]:
        label = f"wq-vol-regime/60m lt={lt}"
        print(f"  {label}...")
        out = run_sweep(CSV_MAP["60m"], "wq-vol-regime", {"short-lookback": 10, "long-lookback": 30, "short-threshold": 1.5, "long-threshold": lt, "exit-offset": 5}, label)
        results.append(f"  - long_threshold={lt}: {out}")
        print(f"    -> {out}")
    results.append("")
    
    # =========================================================
    # SUMMARY
    # =========================================================
    results.append("---")
    results.append("")
    results.append("## Summary: Best Parameters Found")
    results.append("")
    results.append("*(To be filled in after analyzing results above)*")
    
    return '\n'.join(results)

if __name__ == "__main__":
    output = main()
    print("\n\n" + "="*60)
    print("COMPLETE OUTPUT:")
    print("="*60)
    print(output)
    
    # Save to vault
    today = datetime.now().strftime("%Y-%m-%d")
    vault_path = f"/Users/brain/Documents/memorybrain/Agent-Hermes/daily/param-sweep-results-{today}.md"
    with open(vault_path, 'w') as f:
        f.write(output)
    print(f"\nResults saved to {vault_path}")
