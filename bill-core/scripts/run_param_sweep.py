#!/usr/bin/env python3
"""Run parameter sweeps for top strategies using the param_sweep Rust binary.

Uses staged approach to reduce total runtime:
- Stage 1: sweep main params with fixed exit offset
- Stage 2: sweep exit offset for top 10 configs
"""
import subprocess
import json
import sys
import os
from datetime import datetime

BASE = "/Users/brain/hedge/bill-core"
DATA = "/Users/brain/hedge/data/free"
BINARY = f"{BASE}/target/debug/param_sweep"
RESULTS_FILE = f"{BASE}/param_sweep_results.json"
SYMBOL = "NQ"

# Ensure cargo is in PATH
os.environ["PATH"] = f"{os.path.expanduser('~/.cargo/bin')}:{os.environ.get('PATH', '')}"
os.chdir(BASE)


def run_sweep(csv, strategy, **kwargs):
    """Run a single param_sweep invocation and parse the JSON result."""
    cmd = [BINARY, "--csv", csv, "--symbol", SYMBOL, "--strategy", strategy]
    for k, v in kwargs.items():
        cmd.append(f"--{k.replace('_', '-')}")
        cmd.append(str(v))
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def sweep_stage1(strategy, csv, param_grid, fixed_params):
    """Stage 1: sweep all main params with fixed exit offset."""
    results = []
    param_keys = list(param_grid.keys())
    param_values = list(param_grid.values())
    
    from itertools import product
    total = 1
    for pv in param_values:
        total *= len(pv)
    
    done = 0
    for combo in product(*param_values):
        params = dict(zip(param_keys, combo))
        params.update(fixed_params)
        vals = run_sweep(csv, strategy, **params)
        if vals:
            vals.update(params)
            vals["tf"] = os.path.basename(csv).split("-normalized-")[1].replace(".csv", "")
            results.append(vals)
        
        done += 1
        if done % 10 == 0:
            print(f"  [{done}/{total}]", flush=True)
    
    return results


def sweep_stage2(strategy, csv, top_configs, exit_offsets):
    """Stage 2: sweep exit offset for top configs from stage 1."""
    results = []
    for cfg in top_configs:
        for eo in exit_offsets:
            params = {k: v for k, v in cfg.items() 
                      if k in ('range_window', 'vol_threshold', 'sma_short', 'sma_long',
                              'short_lookback', 'long_lookback', 'short_threshold', 'long_threshold')}
            params['exit_offset'] = eo
            vals = run_sweep(csv, strategy, **params)
            if vals:
                vals.update(params)
                vals["tf"] = os.path.basename(csv).split("-normalized-")[1].replace(".csv", "")
                results.append(vals)
    return results


def print_markdown(results, title):
    """Print results as a markdown table."""
    if not results:
        print(f"  No results for {title}")
        return
    
    sorted_r = sorted(results, key=lambda r: float(r.get('total_r', 0)), reverse=True)
    
    param_keys = [k for k in sorted_r[0].keys() 
                  if k not in ("csv", "symbol", "strategy", "trades", "wins", "losses", "wr", "total_r", "avg_r", "tf")]
    
    print(f"\n### {title}")
    print(f"\n| {' | '.join(p.upper() for p in param_keys)} | TRADES | WR% | TOTAL R | AVG R |")
    print(f"| {' | '.join('---' for _ in param_keys)} | :---: | :---: | :---: | :---: |")
    
    for r in sorted_r[:30]:
        vals = [str(r.get(k, '')) for k in param_keys]
        vals += [str(r.get('trades', 0)), 
                 f"{float(r.get('wr', 0)):.1f}",
                 f"{float(r.get('total_r', 0)):.2f}",
                 f"{float(r.get('avg_r', 0)):.2f}"]
        print(f"| {' | '.join(vals)} |")
    
    print(f"\n*Showing top 30 by total R out of {len(sorted_r)} combinations*")
    
    # Best combo
    best = sorted_r[0]
    best_params = ', '.join(f'{k}={best.get(k, "?")}' for k in param_keys)
    print(f"\n**Best:** {best_params} → {best['trades']}T WR={best['wr']:.1f}% R={best['total_r']:.2f}\n")


def print_comparison(title, stage1_results, stage2_results):
    """Compare best configs with exit offset sweep."""
    if not stage1_results or not stage2_results:
        return
    
    s1_best = sorted(stage1_results, key=lambda r: float(r.get('total_r', 0)), reverse=True)[:5]
    s2_best = sorted(stage2_results, key=lambda r: float(r.get('total_r', 0)), reverse=True)[:10]
    
    print(f"\n### {title} — Exit Offset Sweep (Top 10)")
    param_keys = [k for k in s2_best[0].keys() 
                  if k not in ("csv", "symbol", "strategy", "trades", "wins", "losses", "wr", "total_r", "avg_r", "tf")]
    
    print(f"\n| {' | '.join(p.upper() for p in param_keys)} | TRADES | WR% | TOTAL R | AVG R | VS BEST |")
    dash = ' | '.join('---' for _ in param_keys)
    print(f"| {dash} | :---: | :---: | :---: | :---: | :---: |")
    
    best_r = float(s2_best[0].get('total_r', 0))
    for r in s2_best[:10]:
        vals = [str(r.get(k, '')) for k in param_keys]
        r_total = float(r.get('total_r', 0))
        if r_total == best_r:
            vs = "BASELINE"
        else:
            vs = f"+{((r_total-best_r)/best_r*100):+.1f}%"
        vals += [str(r.get('trades', 0)), 
                 f"{float(r.get('wr', 0)):.1f}",
                 f"{r_total:.2f}",
                 f"{float(r.get('avg_r', 0)):.2f}",
                 vs]
        print(f"| {' | '.join(vals)} |")


def main():
    all_data = {}
    
    # === SWEEP 1: ORB-BREAKOUT on 15m ===
    print("=" * 70)
    print("STAGE 1: orb-breakout 15m (sweeping rw, vt, eo=5 fixed)")
    print("=" * 70)
    r1a = sweep_stage1("orb-breakout", 
                       f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
                       param_grid={"range_window": [8, 10, 12, 14, 16, 20],
                                   "vol_threshold": [1.3, 1.5, 2.0]},
                       fixed_params={"exit_offset": 5})
    print_markdown(r1a, "ORB-BREAKOUT 15m — Stage 1 (eo=5 fixed)")
    
    top5_15m = sorted(r1a, key=lambda r: float(r.get('total_r', 0)), reverse=True)[:5]
    r1b = sweep_stage2("orb-breakout",
                       f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
                       top5_15m, exit_offsets=[3, 8])
    print_comparison("ORB-BREAKOUT 15m", r1a, r1b + [r for r in r1a if r in top5_15m])
    all_data["orb-breakout-15m"] = {'stage1': r1a, 'stage2': r1b}
    
    # === SWEEP 2: ORB-BREAKOUT on 30m ===
    print("=" * 70)
    print("STAGE 1: orb-breakout 30m (sweeping rw, vt, eo=5 fixed)")
    print("=" * 70)
    r2a = sweep_stage1("orb-breakout",
                       f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
                       param_grid={"range_window": [8, 10, 12, 14, 16, 20],
                                   "vol_threshold": [1.3, 1.5, 2.0]},
                       fixed_params={"exit_offset": 5})
    print_markdown(r2a, "ORB-BREAKOUT 30m — Stage 1 (eo=5 fixed)")
    
    top5_30m = sorted(r2a, key=lambda r: float(r.get('total_r', 0)), reverse=True)[:5]
    r2b = sweep_stage2("orb-breakout",
                       f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
                       top5_30m, exit_offsets=[3, 8])
    print_comparison("ORB-BREAKOUT 30m", r2a, r2b + [r for r in r2a if r in top5_30m])
    all_data["orb-breakout-30m"] = {'stage1': r2a, 'stage2': r2b}
    
    # === SWEEP 3: WQ-TREND-MOM on 30m ===
    print("=" * 70)
    print("STAGE 1: wq-trend-mom 30m (sweeping ss, sl, vt, eo=5 fixed)")
    print("=" * 70)
    r3a = sweep_stage1("wq-trend-mom",
                       f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
                       param_grid={"sma_short": [10, 15, 20, 30],
                                   "sma_long": [30, 40, 50, 60],
                                   "vol_threshold": [1.3, 1.5]},
                       fixed_params={"exit_offset": 5})
    print_markdown(r3a, "WQ-TREND-MOM 30m — Stage 1 (eo=5 fixed)")
    
    top5_trend = sorted(r3a, key=lambda r: float(r.get('total_r', 0)), reverse=True)[:5]
    r3b = sweep_stage2("wq-trend-mom",
                       f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
                       top5_trend, exit_offsets=[3, 8])
    print_comparison("WQ-TREND-MOM 30m", r3a, r3b + [r for r in r3a if r in top5_trend])
    all_data["wq-trend-mom-30m"] = {'stage1': r3a, 'stage2': r3b}
    
    # === SWEEP 4: WQ-VOL-REGIME on 60m ===
    print("=" * 70)
    print("STAGE 1: wq-vol-regime 60m (sweeping sl, ll, st, lt, eo=5 fixed)")
    print("=" * 70)
    r4a = sweep_stage1("wq-vol-regime",
                       f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
                       param_grid={"short_lookback": [5, 10, 15, 20],
                                   "long_lookback": [20, 30, 40, 50],
                                   "short_threshold": [1.3, 1.5, 1.7, 2.0],
                                   "long_threshold": [0.5, 0.7, 0.9]},
                       fixed_params={"exit_offset": 5})
    print_markdown(r4a, "WQ-VOL-REGIME 60m — Stage 1 (eo=5 fixed)")
    
    top5_vol = sorted(r4a, key=lambda r: float(r.get('total_r', 0)), reverse=True)[:5]
    r4b = sweep_stage2("wq-vol-regime",
                       f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
                       top5_vol, exit_offsets=[3, 8])
    print_comparison("WQ-VOL-REGIME 60m", r4a, r4b + [r for r in r4a if r in top5_vol])
    all_data["wq-vol-regime-60m"] = {'stage1': r4a, 'stage2': r4b}
    
    # Save all data
    with open(RESULTS_FILE, "w") as f:
        json.dump(all_data, f, indent=2, default=str)
    print(f"\nFull results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
