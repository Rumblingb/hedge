#!/usr/bin/env python3
"""param_sweep_orchestrator.py — Run all parameter sweeps for top 3 strategies.

Sweeps:
1. orb-breakout: range_window (8,10,12,14,16,20) × vol_threshold (1.3,1.5,2.0) × exit_offset (3,5,8)
   → on 15m and 30m
2. wq-trend-mom: sma_short (10,15,20,30) × sma_long (30,40,50,60) × vol_threshold (1.3,1.5) × exit_offset (3,5,8)
   → on 30m
3. wq-vol-regime: short_lookback (5,10,15,20) × long_lookback (20,30,40,50) × short_threshold (1.3,1.4,1.5,1.6,1.7,2.0) × long_threshold (0.5,0.6,0.7,0.8,0.9)
   → on 60m
"""

import subprocess
import sys
import os
import datetime
from pathlib import Path

BILL_CORE = "/Users/brain/hedge/bill-core"
DATA_DIR = "/Users/brain/hedge/data/free"
CARGO = os.path.expanduser("~/.cargo/bin/cargo")

CSV_15M = os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv")
CSV_30M = os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv")
CSV_60M = os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv")

def run_sweep(strategy, csv_path, env_vars):
    """Run a single param_sweep with given env vars. Returns (trades, wr, total_r)."""
    env = os.environ.copy()
    env.update(env_vars)
    env["PATH"] = f"{os.path.expanduser('~/.cargo/bin')}:{env.get('PATH', '')}"
    
    result = subprocess.run(
        [CARGO, "run", "--bin", "param_sweep", "--", csv_path, "--symbol", "NQ", "--strategy", strategy],
        capture_output=True, text=True, timeout=90, cwd=BILL_CORE, env=env
    )
    
    # Parse output: "  orb-breakout: 485 trades, 289/196 W/L (59.6%), total R 265.42"
    for line in result.stdout.split('\n'):
        if f"  {strategy}:" in line:
            parts = line.strip().split()
            if len(parts) >= 9:
                trades = int(parts[1].rstrip(','))
                wr_str = parts[5].strip('(),%')
                wr = float(wr_str)
                total_r = float(parts[8])
                return trades, wr, total_r
    return 0, 0.0, 0.0

def fmt_env(env_vars):
    """Format env vars for display."""
    return ", ".join(f"{k}={v}" for k, v in sorted(env_vars.items()))

def sort_key(result):
    """Sort by total R descending."""
    return result[2]  # total_r

def sweep_orb_breakout():
    print("=" * 80)
    print("SWEEP 1: orb-breakout")
    print("Params: range_window × vol_threshold × exit_offset")
    print("Timeframes: 15m and 30m")
    print("=" * 80)
    
    windows = [8, 10, 12, 14, 16, 20]
    vols = [1.3, 1.5, 2.0]
    exits = [3, 5, 8]
    
    results_15m = []
    results_30m = []
    
    total_combos = len(windows) * len(vols) * len(exits)
    done = 0
    
    for w in windows:
        for v in vols:
            for e in exits:
                env = {"ORB_RANGE_WINDOW": str(w), "ORB_VOL_THRESHOLD": str(v), "ORB_EXIT_OFFSET": str(e)}
                done += 1
                
                t15, wr15, r15 = run_sweep("orb-breakout", CSV_15M, env)
                results_15m.append((w, v, e, t15, wr15, r15))
                
                t30, wr30, r30 = run_sweep("orb-breakout", CSV_30M, env)
                results_30m.append((w, v, e, t30, wr30, r30))
                
                print(f"  [{done}/{total_combos}] w={w} v={v} e={e}: 15m={r15:.1f}R ({t15}t, {wr15:.1f}%), 30m={r30:.1f}R ({t30}t, {wr30:.1f}%)")
                sys.stdout.flush()
    
    # Sort and report
    results_15m.sort(key=lambda x: x[5], reverse=True)
    results_30m.sort(key=lambda x: x[5], reverse=True)
    
    print("\n" + "=" * 80)
    print("ORB-BREAKOUT TOP 15 RESULTS")
    print("=" * 80)
    print("--- 15m ---")
    print(f"{'Rank':<5} {'Window':<8} {'Vol':<8} {'Exit':<6} {'Trades':<8} {'WR':<8} {'Total R':<10}")
    for i, (w, v, e, t, wr, r) in enumerate(results_15m[:15]):
        print(f"{i+1:<5} {w:<8} {v:<8.1f} {e:<6} {t:<8} {wr:<7.1f}% {r:<+10.1f}")
    
    print("\n--- 30m ---")
    print(f"{'Rank':<5} {'Window':<8} {'Vol':<8} {'Exit':<6} {'Trades':<8} {'WR':<8} {'Total R':<10}")
    for i, (w, v, e, t, wr, r) in enumerate(results_30m[:15]):
        print(f"{i+1:<5} {w:<8} {v:<8.1f} {e:<6} {t:<8} {wr:<7.1f}% {r:<+10.1f}")
    
    return results_15m, results_30m

def sweep_wq_trend_mom():
    print("\n" + "=" * 80)
    print("SWEEP 2: wq-trend-mom")
    print("Params: sma_short × sma_long × vol_threshold × exit_offset")
    print("Timeframe: 30m")
    print("=" * 80)
    
    short_smas = [10, 15, 20, 30]
    long_smas = [30, 40, 50, 60]
    vols = [1.3, 1.5]
    exits = [3, 5, 8]
    
    results = []
    total_combos = len(short_smas) * len(long_smas) * len(vols) * len(exits)
    done = 0
    
    for ss in short_smas:
        for ls in long_smas:
            if ls <= ss:
                continue  # Long SMA must be > short SMA
            for v in vols:
                for e in exits:
                    env = {"WQ_SMA_SHORT": str(ss), "WQ_SMA_LONG": str(ls), "WQ_VOL_THRESHOLD": str(v), "WQ_EXIT_OFFSET": str(e)}
                    done += 1
                    
                    t, wr, r = run_sweep("wq-trend-mom", CSV_30M, env)
                    results.append((ss, ls, v, e, t, wr, r))
                    
                    print(f"  [{done}/{total_combos}] short={ss} long={ls} vol={v} exit={e}: {r:.1f}R ({t}t, {wr:.1f}%)")
                    sys.stdout.flush()
    
    results.sort(key=lambda x: x[6], reverse=True)
    
    print("\n" + "=" * 80)
    print("WQ-TREND-MOM TOP 15 RESULTS")
    print("=" * 80)
    print(f"{'Rank':<5} {'SMA_S':<8} {'SMA_L':<8} {'Vol':<8} {'Exit':<6} {'Trades':<8} {'WR':<8} {'Total R':<10}")
    for i, (ss, ls, v, e, t, wr, r) in enumerate(results[:15]):
        print(f"{i+1:<5} {ss:<8} {ls:<8} {v:<8.1f} {e:<6} {t:<8} {wr:<7.1f}% {r:<+10.1f}")
    
    return results

def sweep_wq_vol_regime():
    print("\n" + "=" * 80)
    print("SWEEP 3: wq-vol-regime")
    print("Params: short_lookback × long_lookback × short_threshold × long_threshold")
    print("Timeframe: 60m")
    print("=" * 80)
    
    short_lbs = [5, 10, 15, 20]
    long_lbs = [20, 30, 40, 50]
    short_ths = [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]
    long_ths = [0.5, 0.6, 0.7, 0.8, 0.9]
    
    results = []
    total_combos = len(short_lbs) * len(long_lbs) * len(short_ths) * len(long_ths)
    done = 0
    
    for sl in short_lbs:
        for ll in long_lbs:
            if ll <= sl:
                continue  # Long lookback must be > short lookback
            for st in short_ths:
                for lt in long_ths:
                    env = {"WV_SHORT_LOOKBACK": str(sl), "WV_LONG_LOOKBACK": str(ll), "WV_SHORT_THRESHOLD": str(st), "WV_LONG_THRESHOLD": str(lt), "WV_EXIT_OFFSET": "5"}
                    done += 1
                    
                    t, wr, r = run_sweep("wq-vol-regime", CSV_60M, env)
                    results.append((sl, ll, st, lt, 5, t, wr, r))
                    
                    if done % 50 == 0 or done == total_combos:
                        print(f"  [{done}/{total_combos}] sl={sl} ll={ll} st={st} lt={lt}: {r:.1f}R ({t}t, {wr:.1f}%)")
                    sys.stdout.flush()
    
    results.sort(key=lambda x: x[7], reverse=True)
    
    print("\n" + "=" * 80)
    print("WQ-VOL-REGIME TOP 15 RESULTS")
    print("=" * 80)
    print(f"{'Rank':<5} {'S_LB':<8} {'L_LB':<8} {'S_TH':<8} {'L_TH':<8} {'Exit':<6} {'Trades':<8} {'WR':<8} {'Total R':<10}")
    for i, (sl, ll, st, lt, e, t, wr, r) in enumerate(results[:15]):
        print(f"{i+1:<5} {sl:<8} {ll:<8} {st:<8.1f} {lt:<8.1f} {e:<6} {t:<8} {wr:<7.1f}% {r:<+10.1f}")
    
    return results

def main():
    print(f"Parameter Sweep Run — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Binary: param_sweep.rs in bill-core")
    print()
    
    r1_15, r1_30 = sweep_orb_breakout()
    r2 = sweep_wq_trend_mom()
    r3 = sweep_wq_vol_regime()
    
    print("\n" + "=" * 80)
    print("SWEEP COMPLETE")
    print("=" * 80)
    print(f"Completed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"orb-breakout: {len(r1_15)} combos on 15m, {len(r1_30)} combos on 30m")
    print(f"wq-trend-mom: {len(r2)} combos on 30m")
    print(f"wq-vol-regime: {len(r3)} combos on 60m")
    
    # Summary of best parameters
    print("\n" + "=" * 80)
    print("BEST PARAMETERS SUMMARY")
    print("=" * 80)
    
    b15 = r1_15[0] if r1_15 else None
    b30 = r1_30[0] if r1_30 else None
    bt = r2[0] if r2 else None
    bv = r3[0] if r3 else None
    
    print(f"\n1. orb-breakout 15m: window={b15[0]}, vol={b15[1]}, exit={b15[2]} → {b15[4]:.1f}% WR, {b15[5]:.1f}R ({b15[3]} trades)")
    print(f"2. orb-breakout 30m: window={b30[0]}, vol={b30[1]}, exit={b30[2]} → {b30[4]:.1f}% WR, {b30[5]:.1f}R ({b30[3]} trades)")
    print(f"3. wq-trend-mom 30m: short={bt[0]}, long={bt[1]}, vol={bt[2]}, exit={bt[3]} → {bt[5]:.1f}% WR, {bt[6]:.1f}R ({bt[4]} trades)")
    print(f"4. wq-vol-regime 60m: s_lb={bv[0]}, l_lb={bv[1]}, s_th={bv[2]}, l_th={bv[3]}, exit={bv[4]} → {bv[6]:.1f}% WR, {bv[7]:.1f}R ({bv[5]} trades)")

if __name__ == "__main__":
    main()
