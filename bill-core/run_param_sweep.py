#!/usr/bin/env python3
"""Orchestrate parameter sweeps for top 3 strategies on best timeframes."""
import subprocess
import re
import os
import sys
from datetime import date
from itertools import product

BINARY = os.path.expanduser("~/hedge/bill-core/target/release/param_sweep")
DATADIR = os.path.expanduser("~/hedge/bill-core/../data/free")
OUTPUT = os.path.expanduser(f"~/Documents/memorybrain/Agent-Hermes/daily/param-sweep-results-{date.today().isoformat()}.md")

PIPELINE_BINARY = os.path.expanduser("~/hedge/bill-core/target/release/full_strategy_pipeline")

# Baseline run for context
BASELINE_CSVS = {
    "5m": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-5m.csv",
    "15m": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "30m": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "60m": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
    "daily": "ALL-2MARKETS-NQ-ES-1d-5y.csv",
}

STRATEGIES = ["orb-breakout", "wq-trend-mom", "wq-vol-regime"]

def parse_output(output):
    """Parse param_sweep output for strategy results."""
    results = {}
    for line in output.split('\n'):
        m = re.match(r'\s+(\S+): (\d+) trades, (\d+)/(\d+) W/L \((\d+\.?\d*)%\), total R ([\d\.\-]+)', line)
        if m:
            strat = m.group(1)
            results[strat] = {
                'trades': int(m.group(2)),
                'wins': int(m.group(3)),
                'losses': int(m.group(4)),
                'wr': float(m.group(5)),
                'total_r': float(m.group(6)),
            }
    return results

def run_sweep(csv_path, env_vars, strategy=None, symbol="NQ"):
    """Run param_sweep with given env vars, return parsed results."""
    env = os.environ.copy()
    env.update(env_vars)
    cmd = [BINARY, csv_path, "--symbol", symbol]
    if strategy:
        cmd.extend(["--strategy", strategy])
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
        return parse_output(r.stdout), r.stdout
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT for {env_vars}")
        return {}, ""

def run_baseline():
    """Run baseline (default params) on all timeframes for comparison."""
    print("\n=== RUNNING BASELINE (ALL strategies, default params) ===")
    results = {}
    for tf, csv in BASELINE_CSVS.items():
        csv_path = os.path.join(DATADIR, csv)
        if not os.path.exists(csv_path):
            print(f"  SKIP {tf}: {csv_path} not found")
            continue
        r = subprocess.run([PIPELINE_BINARY, csv_path, "--symbol", "NQ"], 
                          capture_output=True, text=True, timeout=30)
        parsed = {}
        for line in r.stdout.split('\n'):
            m = re.match(r'\s+(\S+): (\d+) trades, (\d+)/(\d+) W/L \((\d+\.?\d*)%\), total R ([\d\.\-]+)', line)
            if m and m.group(1) in STRATEGIES:
                parsed[m.group(1)] = {
                    'trades': int(m.group(2)), 'wins': int(m.group(3)),
                    'losses': int(m.group(4)), 'wr': float(m.group(5)),
                    'total_r': float(m.group(6)),
                }
        results[tf] = parsed
        summary = ", ".join(f"{k}={v['total_r']:.1f}R" for k, v in parsed.items())
        print(f"  {tf}: {summary}")
    return results

def sweep_orb_breakout(csv_path, symbol="NQ"):
    """Sweep orb-breakout parameters on 15m (best) and 30m."""
    print("\n=== SWEEP: orb-breakout ===")
    results = {}
    range_windows = [8, 10, 12, 14, 16, 20]
    vol_thresholds = [1.3, 1.5, 2.0]
    exit_offsets = [3, 5, 8]
    total = len(range_windows) * len(vol_thresholds) * len(exit_offsets)
    count = 0
    for rw, vt, eo in product(range_windows, vol_thresholds, exit_offsets):
        count += 1
        env = {"ORB_RANGE_WINDOW": str(rw), "ORB_VOL_THRESHOLD": str(vt), "ORB_EXIT_OFFSET": str(eo)}
        parsed, _ = run_sweep(csv_path, env, "orb-breakout", symbol)
        if "orb-breakout" in parsed:
            key = f"rw={rw},vt={vt},eo={eo}"
            results[key] = parsed["orb-breakout"]
        sys.stdout.write(f"\r  orb-breakout: {count}/{total}")
        sys.stdout.flush()
    print()
    return results

def sweep_wq_trend_mom(csv_path, symbol="NQ"):
    """Sweep wq-trend-mom parameters on 30m (best)."""
    print("\n=== SWEEP: wq-trend-mom ===")
    results = {}
    sma_shorts = [10, 15, 20, 30]
    sma_longs = [30, 40, 50, 60]
    vol_thresholds = [1.3, 1.5]
    exit_offsets = [3, 5, 8]
    total = len(sma_shorts) * len(sma_longs) * len(vol_thresholds) * len(exit_offsets)
    count = 0
    for ss, sl, vt, eo in product(sma_shorts, sma_longs, vol_thresholds, exit_offsets):
        count += 1
        env = {"WQ_SMA_SHORT": str(ss), "WQ_SMA_LONG": str(sl), "WQ_VOL_THRESHOLD": str(vt), "WQ_EXIT_OFFSET": str(eo)}
        parsed, _ = run_sweep(csv_path, env, "wq-trend-mom", symbol)
        if "wq-trend-mom" in parsed:
            key = f"ss={ss},sl={sl},vt={vt},eo={eo}"
            results[key] = parsed["wq-trend-mom"]
        sys.stdout.write(f"\r  wq-trend-mom: {count}/{total}")
        sys.stdout.flush()
    print()
    return results

def sweep_wq_vol_regime(csv_path, symbol="NQ"):
    """Sweep wq-vol-regime parameters on 60m (best)."""
    print("\n=== SWEEP: wq-vol-regime ===")
    results = {}
    short_lookbacks = [5, 10, 15, 20]
    long_lookbacks = [20, 30, 40, 50]
    short_thresholds = [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]
    long_thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
    total = len(short_lookbacks) * len(long_lookbacks) * len(short_thresholds) * len(long_thresholds)
    count = 0
    for sl, ll, st, lt in product(short_lookbacks, long_lookbacks, short_thresholds, long_thresholds):
        count += 1
        env = {"WV_SHORT_LOOKBACK": str(sl), "WV_LONG_LOOKBACK": str(ll),
               "WV_SHORT_THRESHOLD": str(st), "WV_LONG_THRESHOLD": str(lt)}
        parsed, _ = run_sweep(csv_path, env, "wq-vol-regime", symbol)
        if "wq-vol-regime" in parsed:
            key = f"sl={sl},ll={ll},st={st},lt={lt}"
            results[key] = parsed["wq-vol-regime"]
        sys.stdout.write(f"\r  wq-vol-regime: {count}/{total}")
        sys.stdout.flush()
    print()
    return results

def rank_results(results, metric="total_r"):
    """Return top N results sorted by metric."""
    sorted_results = sorted(results.items(), key=lambda x: x[1][metric], reverse=True)
    return sorted_results

def format_row(key, data, extra=""):
    return f"| {key:40s} | {data['trades']:5d} | {data['wins']:4d}/{data['losses']:<4d} | {data['wr']:5.1f}% | {data['total_r']:>8.2f}R | {extra} |"

def write_results(baseline, orb_15m, orb_30m, trend_mom, vol_regime):
    """Write all results to markdown file."""
    today = date.today().isoformat()
    
    lines = []
    lines.append(f"# Parameter Sweep Results — {today}")
    lines.append("")
    lines.append("## Baseline (Default Parameters, NQ only)")
    lines.append("")
    lines.append("| Timeframe | Strategy | Trades | W/L | WR | Total R |")
    lines.append("|-----------|----------|--------|-----|----|---------|")
    for tf in ["15m", "30m", "60m"]:
        if tf in baseline:
            for strat in STRATEGIES:
                if strat in baseline[tf]:
                    d = baseline[tf][strat]
                    lines.append(f"| {tf:9s} | {strat:14s} | {d['trades']:5d} | {d['wins']:3d}/{d['losses']:<3d} | {d['wr']:5.1f}% | {d['total_r']:>8.2f}R |")
    lines.append("")
    
    # === orb-breakout 15m ===
    lines.append("## orb-breakout — 15m Sweep (BEST TIMEFRAME)")
    lines.append("")
    lines.append("Parameters: `ORB_RANGE_WINDOW` (rw), `ORB_VOL_THRESHOLD` (vt), `ORB_EXIT_OFFSET` (eo)")
    lines.append("")
    lines.append("| Params | Trades | W/L | WR | Total R | Delta |")
    lines.append("|--------|--------|-----|----|---------|-------|")
    
    default_15m = baseline.get("15m", {}).get("orb-breakout", {}).get("total_r", 0)
    ranked = rank_results(orb_15m)
    for key, data in ranked[:20]:
        delta = data['total_r'] - default_15m
        lines.append(format_row(key, data, f"{delta:+.2f}R delta"))
    if len(ranked) > 20:
        lines.append(f"\n*(showing top 20 of {len(ranked)} combinations)*")
    
    lines.append("")
    lines.append("### orb-breakout 15m — Bottom 5")
    lines.append("")
    bottom = rank_results(orb_15m, "total_r")[-5:]
    for key, data in bottom:
        delta = data['total_r'] - default_15m
        lines.append(format_row(key, data, f"{delta:+.2f}R delta"))
    lines.append("")
    
    # === orb-breakout 30m ===
    lines.append("## orb-breakout — 30m Sweep (Alternative)")
    lines.append("")
    lines.append("| Params | Trades | W/L | WR | Total R | Delta |")
    lines.append("|--------|--------|-----|----|---------|-------|")
    
    default_30m = baseline.get("30m", {}).get("orb-breakout", {}).get("total_r", 0)
    ranked = rank_results(orb_30m)
    for key, data in ranked[:20]:
        delta = data['total_r'] - default_30m
        lines.append(format_row(key, data, f"{delta:+.2f}R delta"))
    if len(ranked) > 20:
        lines.append(f"\n*(showing top 20 of {len(ranked)} combinations)*")
    
    lines.append("")
    
    # === wq-trend-mom 30m ===
    lines.append("## wq-trend-mom — 30m Sweep (BEST TIMEFRAME)")
    lines.append("")
    lines.append("Parameters: `WQ_SMA_SHORT` (ss), `WQ_SMA_LONG` (sl), `WQ_VOL_THRESHOLD` (vt), `WQ_EXIT_OFFSET` (eo)")
    lines.append("")
    lines.append("| Params | Trades | W/L | WR | Total R | Delta |")
    lines.append("|--------|--------|-----|----|---------|-------|")
    
    default_tm = baseline.get("30m", {}).get("wq-trend-mom", {}).get("total_r", 0)
    ranked = rank_results(trend_mom)
    for key, data in ranked[:25]:
        delta = data['total_r'] - default_tm
        lines.append(format_row(key, data, f"{delta:+.2f}R delta"))
    if len(ranked) > 25:
        lines.append(f"\n*(showing top 25 of {len(ranked)} combinations)*")
    
    lines.append("")
    lines.append("### wq-trend-mom 30m — Bottom 5")
    lines.append("")
    bottom = rank_results(trend_mom, "total_r")[-5:]
    for key, data in bottom:
        delta = data['total_r'] - default_tm
        lines.append(format_row(key, data, f"{delta:+.2f}R delta"))
    lines.append("")
    
    # === wq-vol-regime 60m ===
    lines.append("## wq-vol-regime — 60m Sweep (BEST TIMEFRAME)")
    lines.append("")
    lines.append("Parameters: `WV_SHORT_LOOKBACK` (sl), `WV_LONG_LOOKBACK` (ll), `WV_SHORT_THRESHOLD` (st), `WV_LONG_THRESHOLD` (lt)")
    lines.append("")
    lines.append("| Params | Trades | W/L | WR | Total R | Delta |")
    lines.append("|--------|--------|-----|----|---------|-------|")
    
    default_vr = baseline.get("60m", {}).get("wq-vol-regime", {}).get("total_r", 0)
    ranked = rank_results(vol_regime)
    for key, data in ranked[:30]:
        delta = data['total_r'] - default_vr
        lines.append(format_row(key, data, f"{delta:+.2f}R delta"))
    if len(ranked) > 30:
        lines.append(f"\n*(showing top 30 of {len(ranked)} combinations)*")
    
    lines.append("")
    lines.append("### wq-vol-regime 60m — Bottom 5")
    lines.append("")
    bottom = rank_results(vol_regime, "total_r")[-5:]
    for key, data in bottom:
        delta = data['total_r'] - default_vr
        lines.append(format_row(key, data, f"{delta:+.2f}R delta"))
    lines.append("")
    
    # === Best configs summary ===
    lines.append("## Best Configurations Summary")
    lines.append("")
    lines.append("### 🏆 Top orb-breakout (15m)")
    top15 = rank_results(orb_15m)[:3]
    for key, data in top15:
        lines.append(f"- `{key}` → {data['trades']} trades, {data['wr']:.1f}% WR, **{data['total_r']:.2f}R**")
    
    lines.append("")
    lines.append("### 🏆 Top orb-breakout (30m)")
    top30 = rank_results(orb_30m)[:3]
    for key, data in top30:
        lines.append(f"- `{key}` → {data['trades']} trades, {data['wr']:.1f}% WR, **{data['total_r']:.2f}R**")
    
    lines.append("")
    lines.append("### 🏆 Top wq-trend-mom (30m)")
    top_tm = rank_results(trend_mom)[:5]
    for key, data in top_tm:
        lines.append(f"- `{key}` → {data['trades']} trades, {data['wr']:.1f}% WR, **{data['total_r']:.2f}R**")
    
    lines.append("")
    lines.append("### 🏆 Top wq-vol-regime (60m)")
    top_vr = rank_results(vol_regime)[:5]
    for key, data in top_vr:
        lines.append(f"- `{key}` → {data['trades']} trades, {data['wr']:.1f}% WR, **{data['total_r']:.2f}R**")
    
    lines.append("")
    
    content = '\n'.join(lines)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, 'w') as f:
        f.write(content)
    print(f"\nResults written to {OUTPUT}")
    return content

if __name__ == "__main__":
    print("=== FULL STRATEGY PARAMETER SWEEP ===")
    print(f"Binary: {BINARY}")
    print(f"Data dir: {DATADIR}")
    print()
    
    # Run baselines
    baseline = run_baseline()
    
    # Run sweeps
    csv_15m = os.path.join(DATADIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv")
    csv_30m = os.path.join(DATADIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv")
    csv_60m = os.path.join(DATADIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv")
    
    orb_15m = sweep_orb_breakout(csv_15m)
    orb_30m = sweep_orb_breakout(csv_30m)
    trend_mom = sweep_wq_trend_mom(csv_30m)
    vol_regime = sweep_wq_vol_regime(csv_60m)
    
    # Write results
    content = write_results(baseline, orb_15m, orb_30m, trend_mom, vol_regime)
    
    # Print summary to stdout
    print()
    print(content)
