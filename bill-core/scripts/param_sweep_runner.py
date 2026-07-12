#!/usr/bin/env python3
"""param_sweep_runner.py — Orchestrate parameter sweeps for top strategies.

Calls `cargo run --bin param_sweep` for each parameter combination.
Writes results to the Hermes daily vault.
"""

import subprocess
import json
import sys
import os
from datetime import datetime
from itertools import product

CARGO = "cargo"
PROJECT_DIR = "/Users/brain/hedge/bill-core"
DATA_DIR = os.path.join(PROJECT_DIR, "..", "data", "free")
VAULT_DAILY = "/Users/brain/Documents/memorybrain/Agent-Hermes/daily"
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

CSVS = {
    "5m":  os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-5m.csv"),
    "15m": os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv"),
    "30m": os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv"),
    "60m": os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv"),
    "daily": os.path.join(DATA_DIR, "ALL-2MARKETS-NQ-ES-1d-5y.csv"),
}

SYMBOL = "NQ"

def run_sweep(strategy, csv_path, params_dict):
    """Run a single param_sweep invocation and return the parsed JSON result."""
    cmd = [
        CARGO, "run", "--bin", "param_sweep", "--",
        "--strategy", strategy,
        "--csv", csv_path,
        "--symbol", SYMBOL,
    ]
    for key, val in params_dict.items():
        cmd.extend([f"--{key}", str(val)])

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # JSON is on stdout; warnings are on stderr
        output = result.stdout.strip()
        if not output:
            return None
        # Find the JSON line (last non-empty line)
        lines = [l for l in output.splitlines() if l.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return None


def build_combos(strategy, tf, target_csv):
    """Yield (params_dict, label) combos for a strategy+timeframe."""
    if strategy == "orb-breakout":
        range_windows = [8, 10, 12, 14, 16, 20]
        vol_thresholds = [1.3, 1.5, 2.0]
        exit_offsets = [3, 5, 8]
        for rw, vt, eo in product(range_windows, vol_thresholds, exit_offsets):
            params = {"range-window": rw, "vol-threshold": vt, "exit-offset": eo}
            label = f"rw={rw},vt={vt},eo={eo}"
            yield params, label

    elif strategy == "wq-trend-mom":
        sma_shorts = [10, 15, 20, 30]
        sma_longs = [30, 40, 50, 60]
        vol_thresholds = [1.3, 1.5]
        exit_offsets = [3, 5, 8]
        for ss, sl, vt, eo in product(sma_shorts, sma_longs, vol_thresholds, exit_offsets):
            params = {"sma-short": ss, "sma-long": sl, "vol-threshold": vt, "exit-offset": eo}
            label = f"ss={ss},sl={sl},vt={vt},eo={eo}"
            yield params, label

    elif strategy == "wq-vol-regime":
        short_lookbacks = [5, 10, 15, 20]
        long_lookbacks = [20, 30, 40, 50]
        short_thresholds = [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]
        long_thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
        # Exit offset not swept for vol-regime (keep at default 5 per user spec)
        for slk, llk, st, lt in product(
            short_lookbacks, long_lookbacks, short_thresholds, long_thresholds
        ):
            params = {
                "short-lookback": slk,
                "long-lookback": llk,
                "short-threshold": st,
                "long-threshold": lt,
                "exit-offset": 5,
            }
            label = f"slk={slk},llk={llk},st={st},lt={lt},eo=5"
            yield params, label


def run_and_collect(strategy, tf, target_csv):
    """Run all combos for a strategy+TF, return sorted results."""
    results = []
    combos = list(build_combos(strategy, tf, target_csv))
    total = len(combos)
    print(f"\n{'='*60}")
    print(f"SWEEP: {strategy} on {tf} ({total} combos)")
    print(f"{'='*60}")

    best = None
    for idx, (params, label) in enumerate(combos):
        result = run_sweep(strategy, target_csv, params)
        if result:
            result["_params"] = label
            result["_tf"] = tf
            results.append(result)
            total_r = result.get("total_r", 0)
            wr = result.get("wr", 0)
            trades = result.get("trades", 0)
            print(f"  [{idx+1}/{total}] {label} → {trades} trades, {wr:.1f}% WR, {total_r:+.2f}R")
            if best is None or total_r > best.get("total_r", -999):
                best = result
        else:
            print(f"  [{idx+1}/{total}] {label} → FAILED")

    # Sort by total_r descending
    results.sort(key=lambda r: r.get("total_r", -999), reverse=True)
    return results, best


def format_md_table(results, top_n=20):
    """Format top N results as a Markdown table."""
    if not results:
        return "No results."
    lines = []
    lines.append("| # | Params | Trades | WR% | Total R | Avg R | Longs | Shorts | Long R | Short R |")
    lines.append("|:--|:--------|:------:|:---:|:-------:|:-----:|:-----:|:------:|:------:|:-------:|")
    for i, r in enumerate(results[:top_n]):
        params = r.get("_params", "?")
        trades = r.get("trades", 0)
        wr = r.get("wr", 0)
        total_r = r.get("total_r", 0)
        avg_r = r.get("avg_r", 0)
        longs = r.get("longs", 0)
        shorts = r.get("shorts", 0)
        long_r = r.get("long_r", 0)
        short_r = r.get("short_r", 0)
        lines.append(
            f"| {i+1} | {params} | {trades} | {wr:.1f} | {total_r:+.2f} | {avg_r:+.2f} | {longs} | {shorts} | {long_r:+.2f} | {short_r:+.2f} |"
        )
    return "\n".join(lines)


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(VAULT_DAILY, f"param-sweep-results-{today}.md")

    # Ensure cargo build is up to date (compile once)
    print("=== PARAM SWEEP RUNNER ===")
    print(f"Timestamp: {TIMESTAMP}")
    print("Building param_sweep binary...")
    build_result = subprocess.run(
        [CARGO, "build", "--bin", "param_sweep"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if build_result.returncode != 0:
        print("BUILD FAILED:", build_result.stderr[-500:], file=sys.stderr)
        sys.exit(1)
    print("Build OK.\n")

    sweeps = [
        ("orb-breakout", "15m", CSVS["15m"]),
        ("orb-breakout", "30m", CSVS["30m"]),
        ("wq-trend-mom", "30m", CSVS["30m"]),
        ("wq-vol-regime", "60m", CSVS["60m"]),
    ]

    all_sections = []

    for strategy, tf, csv_path in sweeps:
        results, best = run_and_collect(strategy, tf, csv_path)
        if best:
            total_r = best.get("total_r", 0)
            wr = best.get("wr", 0)
            trades = best.get("trades", 0)
            avg_r = best.get("avg_r", 0)
            params = best.get("_params", "?")
            print(f"\n  🏆 BEST: {params}")
            print(f"     {trades} trades, {wr:.1f}% WR, {total_r:+.2f}R total, {avg_r:+.2f}R avg")
        else:
            print(f"\n  ❌ No valid results.")

        if best:
            section = f"""## {strategy} — {tf}

**Best config:** `{best['_params']}` → {best['trades']} trades, {best['wr']:.1f}% WR, {best['total_r']:+.2f}R total, {best['avg_r']:+.2f}R avg

### Top 20 Results

{format_md_table(results, 20)}

"""
        else:
            section = f"""## {strategy} — {tf}

**No valid results.**

"""

        all_sections.append(section)

    # Write output
    md_content = f"""# Parameter Sweep Results — {today}

**Generated:** {TIMESTAMP}  
**Binary:** `param_sweep` (Rust)  
**Symbol:** {SYMBOL}  
**Total sweeps:** 4 (orb-breakout 15m+30m, wq-trend-mom 30m, wq-vol-regime 60m)

---

{"".join(all_sections)}

---
*Generated by param_sweep_runner.py*
"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(md_content)
    print(f"\n✅ Results written to {out_path}")


if __name__ == "__main__":
    main()
