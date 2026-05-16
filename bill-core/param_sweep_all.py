#!/usr/bin/env python3
"""Run all parameter sweeps for orb-breakout, wq-trend-mom, wq-vol-regime."""
import subprocess
import sys
import os
import time
from datetime import datetime

BIN = "target/release/param_sweep"
BIN_DIR = "/Users/brain/hedge/bill-core"
DATA_DIR = "/Users/brain/hedge/data/free"
RESULTS_FILE = "/Users/brain/Documents/memorybrain/Agent-Hermes/daily/param-sweep-results-2026-05-16.md"

CSVS = {
    "15m": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "30m": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "60m": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
}

def run_sweep(strategy, csv_path, params, label=""):
    """Run a single param_sweep invocation and parse output."""
    param_str = ",".join(f"{k}={v}" for k, v in params.items())
    cmd = [BIN, "--strategy", strategy, "--csv", csv_path, "--symbol", "NQ", "--params", param_str]
    ts = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, cwd=BIN_DIR
        )
        elapsed = time.time() - ts
        output = result.stdout.strip()
        if result.returncode != 0:
            return {"label": label, "params": params, "error": result.stderr.strip(), "elapsed": elapsed}
        parts = output.split("|")
        if len(parts) >= 8:
            return {
                "label": label,
                "params": params,
                "trades": int(parts[2]),
                "filtered": int(parts[3]),
                "wins": int(parts[4]),
                "wr": float(parts[5]),
                "total_r": float(parts[6]),
                "pnl": float(parts[7]),
                "elapsed": elapsed,
            }
        else:
            return {"label": label, "params": params, "error": f"Unexpected output: {output[:200]}", "elapsed": elapsed}
    except subprocess.TimeoutExpired:
        return {"label": label, "params": params, "error": "timeout", "elapsed": time.time() - ts}
    except Exception as e:
        return {"label": label, "params": params, "error": str(e), "elapsed": time.time() - ts}

def fmt_result(r):
    if "error" in r:
        return f"  ❌ {r['label']}: ERROR - {r['error']}"
    return (f"  {r['label']}: {r['filtered']} trades, {r['wins']}W, "
            f"{r['wr']:.1f}% WR, {r['total_r']:.2f}R, ${r['pnl']:.0f} PnL [{r['elapsed']:.1f}s]")

# ================================
# ORB-BREAKOUT SWEEP (15m + 30m)
# ================================
def sweep_orb_breakout():
    results = []
    timeframes = [("15m", CSVS["15m"]), ("30m", CSVS["30m"])]
    range_windows = [8, 10, 12, 14, 16, 20]
    vol_thresholds = [1.3, 1.5, 2.0]
    exit_offsets = [3, 5, 8]

    total = len(timeframes) * len(range_windows) * len(vol_thresholds) * len(exit_offsets)
    count = 0
    for tf_name, csv_path in timeframes:
        for rw in range_windows:
            for vt in vol_thresholds:
                for eo in exit_offsets:
                    params = {"range_window": rw, "vol_threshold": vt, "exit_offset": eo}
                    label = f"orb-breakout({tf_name}) rw={rw} vt={vt} eo={eo}"
                    count += 1
                    sys.stdout.write(f"\r  [{count}/{total}] {label}...")
                    sys.stdout.flush()
                    r = run_sweep("orb-breakout", csv_path, params, label)
                    results.append(r)
    sys.stdout.write("\n")
    return results

# ================================
# WQ-TREND-MOM SWEEP (30m)
# ================================
def sweep_wq_trend_mom():
    results = []
    csv_path = CSVS["30m"]
    sma_shorts = [10, 15, 20, 30]
    sma_longs = [30, 40, 50, 60]
    vol_thresholds = [1.3, 1.5]
    exit_offsets = [3, 5, 8]

    total = len(sma_shorts) * len(sma_longs) * len(vol_thresholds) * len(exit_offsets)
    count = 0
    for ss in sma_shorts:
        for sl in sma_longs:
            for vt in vol_thresholds:
                for eo in exit_offsets:
                    params = {"sma_short": ss, "sma_long": sl, "vol_threshold": vt, "exit_offset": eo}
                    label = f"wq-trend-mom(30m) ss={ss} sl={sl} vt={vt} eo={eo}"
                    count += 1
                    sys.stdout.write(f"\r  [{count}/{total}] {label}...")
                    sys.stdout.flush()
                    r = run_sweep("wq-trend-mom", csv_path, params, label)
                    results.append(r)
    sys.stdout.write("\n")
    return results

# ================================
# WQ-VOL-REGIME SWEEP (60m)
# ================================
def sweep_wq_vol_regime():
    results = []
    csv_path = CSVS["60m"]
    short_lookbacks = [5, 10, 15, 20]
    long_lookbacks = [20, 30, 40, 50]
    short_thresholds = [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]
    long_thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]

    total = len(short_lookbacks) * len(long_lookbacks) * len(short_thresholds) * len(long_thresholds)
    count = 0
    for slb in short_lookbacks:
        for llb in long_lookbacks:
            for sth in short_thresholds:
                for lth in long_thresholds:
                    params = {"short_lookback": slb, "long_lookback": llb, "short_threshold": sth, "long_threshold": lth}
                    label = f"wq-vol-regime(60m) slb={slb} llb={llb} sth={sth} lth={lth}"
                    count += 1
                    sys.stdout.write(f"\r  [{count}/{total}] {label}...")
                    sys.stdout.flush()
                    r = run_sweep("wq-vol-regime", csv_path, params, label)
                    results.append(r)
    sys.stdout.write("\n")
    return results

# ================================
# MAIN
# ================================
if __name__ == "__main__":
    start = time.time()
    all_sections = {}

    print("=" * 70)
    print("FULL STRATEGY PARAMETER SWEEP")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # --- Orb-breakout ---
    print("\n--- ORB-BREAKOUT SWEEP (15m + 30m) ---")
    orb_results = sweep_orb_breakout()
    valid_orb = [r for r in orb_results if "error" not in r]
    orb_by_pnl = sorted(valid_orb, key=lambda r: r["pnl"], reverse=True)
    orb_by_r = sorted(valid_orb, key=lambda r: r["total_r"], reverse=True)
    all_sections["orb-breakout"] = {"results": orb_results, "by_pnl": orb_by_pnl, "by_r": orb_by_r}
    print(f"  Total: {len(valid_orb)}/{len(orb_results)} valid | Best by PnL: {orb_by_pnl[0]['label']} (${orb_by_pnl[0]['pnl']:.0f})")

    # --- WQ Trend Mom ---
    print("\n--- WQ-TREND-MOM SWEEP (30m) ---")
    trend_results = sweep_wq_trend_mom()
    valid_trend = [r for r in trend_results if "error" not in r]
    trend_by_pnl = sorted(valid_trend, key=lambda r: r["pnl"], reverse=True)
    trend_by_r = sorted(valid_trend, key=lambda r: r["total_r"], reverse=True)
    all_sections["wq-trend-mom"] = {"results": trend_results, "by_pnl": trend_by_pnl, "by_r": trend_by_r}
    print(f"  Total: {len(valid_trend)}/{len(trend_results)} valid | Best by PnL: {trend_by_pnl[0]['label']} (${trend_by_pnl[0]['pnl']:.0f})")

    # --- WQ Vol Regime ---
    print("\n--- WQ-VOL-REGIME SWEEP (60m) ---")
    vol_results = sweep_wq_vol_regime()
    valid_vol = [r for r in vol_results if "error" not in r]
    vol_by_pnl = sorted(valid_vol, key=lambda r: r["pnl"], reverse=True)
    vol_by_r = sorted(valid_vol, key=lambda r: r["total_r"], reverse=True)
    all_sections["wq-vol-regime"] = {"results": vol_results, "by_pnl": vol_by_pnl, "by_r": vol_by_r}
    print(f"  Total: {len(valid_vol)}/{len(vol_results)} valid | Best by PnL: {vol_by_pnl[0]['label']} (${vol_by_pnl[0]['pnl']:.0f})")

    elapsed = time.time() - start
    print(f"\nTotal time: {elapsed:.0f}s ({elapsed/60:.1f}m)")

    # ================================
    # WRITE RESULTS FILE
    # ================================
    today = datetime.now().strftime("%Y-%m-%d")
    content = f"""# Parameter Sweep Results — {today}

**Generated by**: Hermes Agent automated parameter sweep
**Duration**: {elapsed:.0f}s ({elapsed/60:.1f}m)
**Symbol**: NQ (all sweeps)

---

## orb-breakout Sweep (15m + 30m)

### Top 10 by PnL
| # | Params | Trades | WR% | Total R | PnL |
|---|--------|--------|-----|---------|-----|
"""
    for i, r in enumerate(orb_by_pnl[:10]):
        content += f"| {i+1} | {r['label']} | {r['filtered']} | {r['wr']:.1f}% | {r['total_r']:.2f}R | ${r['pnl']:.0f} |\n"

    content += "\n### Top 10 by Total R\n| # | Params | Trades | WR% | Total R | PnL |\n|---|--------|--------|-----|---------|-----|\n"
    for i, r in enumerate(orb_by_r[:10]):
        content += f"| {i+1} | {r['label']} | {r['filtered']} | {r['wr']:.1f}% | {r['total_r']:.2f}R | ${r['pnl']:.0f} |\n"

    content += f"""
### All Results ({len(valid_orb)} valid)
<details>
<summary>Click to expand</summary>

```
"""
    for r in orb_results:
        content += fmt_result(r) + "\n"
    content += "```\n</details>\n\n---\n\n"

    # --- Trend Mom ---
    content += """## wq-trend-mom Sweep (30m)

### Top 10 by PnL
| # | Params | Trades | WR% | Total R | PnL |
|---|--------|--------|-----|---------|-----|
"""
    for i, r in enumerate(trend_by_pnl[:10]):
        content += f"| {i+1} | {r['label']} | {r['filtered']} | {r['wr']:.1f}% | {r['total_r']:.2f}R | ${r['pnl']:.0f} |\n"

    content += "\n### Top 10 by Total R\n| # | Params | Trades | WR% | Total R | PnL |\n|---|--------|--------|-----|---------|-----|\n"
    for i, r in enumerate(trend_by_r[:10]):
        content += f"| {i+1} | {r['label']} | {r['filtered']} | {r['wr']:.1f}% | {r['total_r']:.2f}R | ${r['pnl']:.0f} |\n"

    content += f"""
### All Results ({len(valid_trend)} valid)
<details>
<summary>Click to expand</summary>

```
"""
    for r in trend_results:
        content += fmt_result(r) + "\n"
    content += "```\n</details>\n\n---\n\n"

    # --- Vol Regime ---
    content += """## wq-vol-regime Sweep (60m)

### Top 10 by PnL
| # | Params | Trades | WR% | Total R | PnL |
|---|--------|--------|-----|---------|-----|
"""
    for i, r in enumerate(vol_by_pnl[:10]):
        content += f"| {i+1} | {r['label']} | {r['filtered']} | {r['wr']:.1f}% | {r['total_r']:.2f}R | ${r['pnl']:.0f} |\n"

    content += "\n### Top 10 by Total R\n| # | Params | Trades | WR% | Total R | PnL |\n|---|--------|--------|-----|---------|-----|\n"
    for i, r in enumerate(vol_by_r[:10]):
        content += f"| {i+1} | {r['label']} | {r['filtered']} | {r['wr']:.1f}% | {r['total_r']:.2f}R | ${r['pnl']:.0f} |\n"

    content += f"""
### All Results ({len(valid_vol)} valid)
<details>
<summary>Click to expand</summary>

```
"""
    for r in vol_results:
        content += fmt_result(r) + "\n"
    content += "```\n</details>\n\n---\n\n"

    # ================================
    # RECOMMENDATIONS
    # ================================
    content += f"""## Recommendations

### orb-breakout
- **Best PnL**: {orb_by_pnl[0]['label']} (${orb_by_pnl[0]['pnl']:.0f}, {orb_by_pnl[0]['total_r']:.2f}R)
- **Best R**: {orb_by_r[0]['label']} ({orb_by_r[0]['total_r']:.2f}R)

### wq-trend-mom
- **Best PnL**: {trend_by_pnl[0]['label']} (${trend_by_pnl[0]['pnl']:.0f}, {trend_by_pnl[0]['total_r']:.2f}R)
- **Best R**: {trend_by_r[0]['label']} ({trend_by_r[0]['total_r']:.2f}R)

### wq-vol-regime
- **Best PnL**: {vol_by_pnl[0]['label']} (${vol_by_pnl[0]['pnl']:.0f}, {vol_by_pnl[0]['total_r']:.2f}R)
- **Best R**: {vol_by_r[0]['label']} ({vol_by_r[0]['total_r']:.2f}R)
"""

    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        f.write(content)
    print(f"\nResults written to: {RESULTS_FILE}")
