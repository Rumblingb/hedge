#!/usr/bin/env python3
"""Parameter sweep runner for orb-breakout, wq-trend-mom, wq-vol-regime.
Calls the pre-compiled param_sweep binary for each combination.
"""

import subprocess
import json
import sys
from datetime import datetime
from pathlib import Path
from itertools import product

BINARY = Path("/Users/brain/hedge/bill-core/target/release/param_sweep")
DATA_DIR = Path("/Users/brain/hedge/data/free")

# Map of shorthand to full CSV path
CSVS = {
    "15m": str(DATA_DIR / "ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv"),
    "30m": str(DATA_DIR / "ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv"),
    "60m": str(DATA_DIR / "ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv"),
}


def run_sweep(strategy, csv_key, param_names, param_combos):
    """Run the binary for each parameter combination, return list of (params, result_dict)."""
    results = []
    total = len(param_combos)
    for idx, combo in enumerate(param_combos):
        args = [
            str(BINARY),
            "--strategy", strategy,
            "--csv", CSVS[csv_key],
            "--symbol", "NQ",
        ]
        for name, val in zip(param_names, combo):
            args.extend([name, str(val)])

        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=30)
            if p.returncode != 0:
                print(f"  [{idx+1}/{total}] ERROR: {p.stderr.strip()}", file=sys.stderr)
                results.append((combo, None))
                continue
            data = json.loads(p.stdout.strip())
            results.append((combo, data))
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            print(f"  [{idx+1}/{total}] FAIL: {e}", file=sys.stderr)
            results.append((combo, None))
            continue

        if (idx + 1) % 10 == 0 or idx == 0:
            print(f"  [{idx+1}/{total}] done", file=sys.stderr)
    return results


def format_table(param_names, results, sort_by="total_r"):
    """Format results as a Markdown table, sorted by best total_r descending."""
    valid = [(p, r) for p, r in results if r is not None and r["trades"] > 0]
    if not valid:
        return "No valid results.\n"

    valid.sort(key=lambda x: x[1].get(sort_by, 0), reverse=True)

    header = "| " + " | ".join(param_names) + " | Trades | Wins | Loss | WR% | totalR | avgR | longR | shortR |"
    sep = "|" + "|".join(["---"] * (len(param_names) + 8)) + "|"

    lines = [header, sep]
    for params, r in valid:
        t = r["trades"]
        vals = " | ".join(str(p) for p in params)
        row = f"| {vals} | {t} | {r['wins']} | {r['losses']} | {r['wr']:.1f} | {r['total_r']:.2f} | {r['avg_r']:.2f} | {r['long_r']:.2f} | {r['short_r']:.2f} |"
        lines.append(row)

    # Add a summary line for best
    if valid:
        best_p, best_r = valid[0]
        lines.append(f"\n**Best**: params=({', '.join(str(p) for p in best_p)}) → totalR={best_r['total_r']:.2f}, WR={best_r['wr']:.1f}%, avgR={best_r['avg_r']:.2f}")

    return "\n".join(lines)


def main():
    out_path = Path(f"/Users/brain/Documents/memorybrain/Agent-Hermes/daily/param-sweep-results-{datetime.now().strftime('%Y-%m-%d')}.md")
    lines = [f"# Parameter Sweep Results — {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]

    # ============================================================
    # 1. orb-breakout on 15m and 30m
    # ============================================================
    param_names_orb = ["--range-window", "--vol-threshold", "--exit-offset"]
    range_windows = [8, 10, 12, 14, 16, 20]
    vol_thresholds = [1.3, 1.5, 2.0]
    exit_offsets = [3, 5, 8]
    combos_orb = list(product(range_windows, vol_thresholds, exit_offsets))

    for tf in ["15m", "30m"]:
        print(f"\n=== orb-breakout on {tf} ({len(combos_orb)} combos) ===", file=sys.stderr)
        results = run_sweep("orb-breakout", tf, param_names_orb, combos_orb)

        lines.append(f"## orb-breakout — {tf}")
        lines.append(f"_Parameters swept: range-window × vol-threshold × exit-offset ({len(combos_orb)} combinations)_")
        lines.append("")
        lines.append(format_table(["range", "vol_thr", "exit"], results))
        lines.append("")

    # ============================================================
    # 2. wq-trend-mom on 30m
    # ============================================================
    param_names_tm = ["--sma-short", "--sma-long", "--vol-threshold", "--exit-offset"]
    sma_shorts = [10, 15, 20, 30]
    sma_longs = [30, 40, 50, 60]
    vol_thresh_tm = [1.3, 1.5]
    exit_offsets_tm = [3, 5, 8]
    combos_tm = list(product(sma_shorts, sma_longs, vol_thresh_tm, exit_offsets_tm))

    print(f"\n=== wq-trend-mom on 30m ({len(combos_tm)} combos) ===", file=sys.stderr)
    results_tm = run_sweep("wq-trend-mom", "30m", param_names_tm, combos_tm)

    lines.append("## wq-trend-mom — 30m")
    lines.append(f"_Parameters swept: sma-short × sma-long × vol-threshold × exit-offset ({len(combos_tm)} combinations)_")
    lines.append("")
    lines.append(format_table(["SMA_s", "SMA_l", "vol_thr", "exit"], results_tm))
    lines.append("")

    # ============================================================
    # 3. wq-vol-regime on 60m
    # ============================================================
    param_names_vr = ["--short-lookback", "--long-lookback", "--short-threshold", "--long-threshold"]
    short_lookbacks = [5, 10, 15, 20]
    long_lookbacks = [20, 30, 40, 50]
    short_thresholds = [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]
    long_thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
    combos_vr = list(product(short_lookbacks, long_lookbacks, short_thresholds, long_thresholds))

    print(f"\n=== wq-vol-regime on 60m ({len(combos_vr)} combos) ===", file=sys.stderr)
    results_vr = run_sweep("wq-vol-regime", "60m", param_names_vr, combos_vr)

    lines.append("## wq-vol-regime — 60m")
    lines.append(f"_Parameters swept: short-lookback × long-lookback × short-threshold × long-threshold ({len(combos_vr)} combinations)_")
    lines.append("")
    lines.append(format_table(["sh_lk", "lg_lk", "sh_thr", "lg_thr"], results_vr))
    lines.append("")

    # Write output
    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    print(f"\nResults written to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
