#!/usr/bin/env python3
"""param_sweep_runner.py — Run full parameter grid sweeps for 3 strategies.

Calls the pre-built `target/release/param_sweep` binary for each combo.
Parses JSON output and writes ranked results to markdown.
"""

import subprocess
import json
import itertools
import sys
import os
from datetime import datetime

from typing import Optional

# ── Configuration ──────────────────────────────────────────────────────────
BASE_CSV_DIR = "/Users/brain/hedge/data/free"
BILL_DIR = "/Users/brain/hedge/bill-core"
BINARY = os.path.join(BILL_DIR, "target/release/param_sweep")
OUTPUT_DIR = "/Users/brain/Documents/memorybrain/Agent-Hermes/daily"
SYMBOL = "NQ"

# CSV paths per timeframe
CSVS = {
    "15m": os.path.join(BASE_CSV_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv"),
    "30m": os.path.join(BASE_CSV_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv"),
    "60m": os.path.join(BASE_CSV_DIR, "ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv"),
}

# ── Strategy parameter grids ───────────────────────────────────────────────
GRIDS = {
    "orb-breakout": {
        "timeframes": ["15m", "30m"],
        "params": {
            "--range-window": [8, 10, 12, 14, 16, 20],
            "--vol-threshold": [1.3, 1.5, 2.0],
            "--exit-offset":  [3, 5, 8],
        },
    },
    "wq-trend-mom": {
        "timeframes": ["30m"],
        "params": {
            "--sma-short":    [10, 15, 20, 30],
            "--sma-long":     [30, 40, 50, 60],
            "--vol-threshold": [1.3, 1.5],
            "--exit-offset":  [3, 5, 8],
        },
    },
    "wq-vol-regime": {
        "timeframes": ["60m"],
        "params": {
            "--short-lookback":  [5, 10, 15, 20],
            "--long-lookback":   [20, 30, 40, 50],
            "--short-threshold": [1.3, 1.4, 1.5, 1.6, 1.7, 2.0],
            "--long-threshold":  [0.5, 0.6, 0.7, 0.8, 0.9],
            "--exit-offset":     [5],
        },
    },
}


def run_one(strategy: str, timeframe: str, combo: dict) -> Optional[dict]:
    """Run param_sweep binary with given parameters, return parsed JSON."""
    cmd = [
        BINARY,
        "--strategy", strategy,
        "--csv", CSVS[timeframe],
        "--symbol", SYMBOL,
    ]
    for k, v in combo.items():
        cmd.extend([k, str(v)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "combo": combo}
        stdout = result.stdout.strip()
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "combo": combo}
    except json.JSONDecodeError as e:
        return {"error": f"json parse: {e}", "combo": combo, "raw": ""}
    except Exception as e:
        return {"error": str(e), "combo": combo}


def generate_combos(params: dict):
    """Generate all combinations of parameter values."""
    keys = list(params.keys())
    values = [params[k] for k in keys]
    for combo_values in itertools.product(*values):
        yield dict(zip(keys, combo_values))


def format_combo(combo: dict) -> str:
    """Format parameter combo as readable string."""
    parts = []
    for k, v in combo.items():
        short = k.replace("--", "").replace("-", "_")
        parts.append(f"{short}={v}")
    return ", ".join(parts)


def header(md_lines: list, text: str, level: int = 2):
    md_lines.append(f"\n{'#' * level} {text}\n")


def write_results(strategy: str, timeframe: str, results: list, md_lines: list):
    """Write a results table for one strategy+timeframe combo."""
    if not results:
        md_lines.append(f"*No results for {strategy} on {timeframe}*\n")
        return

    header(md_lines, f"{strategy} — {timeframe}", level=3)
    n_err = sum(1 for r in results if "error" in r)
    md_lines.append(f"Runs: {len(results)} | Errors: {n_err}\n")

    # Table header
    md_lines.append("| Rank | total_R | avg_R | WR% | Trades | Wins | Params |")
    md_lines.append("|------|---------|-------|-----|--------|------|--------|")

    sorted_results = sorted(
        [r for r in results if "error" not in r],
        key=lambda r: r.get("total_r", -9999),
        reverse=True,
    )
    errors = [r for r in results if "error" in r]

    for i, r in enumerate(sorted_results[:30], 1):
        params_str = format_combo(r.get("_combo", {}))
        md_lines.append(
            f"| {i} | {r['total_r']:.2f} | {r['avg_r']:.2f} | {r['wr']:.1f}% | "
            f"{r['trades']} | {r['wins']} | {params_str} |"
        )

    if errors:
        md_lines.append(f"\n**Errors ({len(errors)}):**")
        for e in errors[:5]:
            md_lines.append(f"- {e.get('error', 'unknown')[:120]}")

    if sorted_results:
        best = sorted_results[0]
        md_lines.append(f"\n**Best: total_R={best['total_r']:.2f}, "
                        f"avg_R={best['avg_r']:.2f}, "
                        f"WR={best['wr']:.1f}%, Trades={best['trades']}**")
        md_lines.append(f"Params: `{format_combo(best.get('_combo', {}))}`\n")


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(OUTPUT_DIR, f"param-sweep-results-{today}.md")
    md_lines = [
        f"# Parameter Sweep Results — {today}\n",
        f"**Symbol**: {SYMBOL}\n",
        f"**Data**: 21-day normalized CSVs\n",
        f"**Binary**: `target/release/param_sweep`\n",
        "---\n",
    ]

    total_combos = 0
    for strategy, grid in GRIDS.items():
        for tf in grid["timeframes"]:
            params = grid["params"]
            n = 1
            for vals in params.values():
                n *= len(vals)
            total_combos += n

    md_lines.append(f"**Total parameter combinations**: {total_combos}\n")

    for strategy, grid in GRIDS.items():
        header(md_lines, f"Strategy: {strategy}", level=2)
        md_lines.append(f"*Timeframes: {', '.join(grid['timeframes'])}*\n")

        for tf in grid["timeframes"]:
            params = grid["params"]
            combos = list(generate_combos(params))
            n = len(combos)
            md_lines.append(f"\nTesting {n} combinations on {tf}...\n")

            results = []
            for j, combo in enumerate(combos):
                if (j + 1) % max(1, n // 10) == 0:
                    pct = int((j + 1) / n * 100)
                    print(f"  [{strategy}/{tf}] {j+1}/{n} ({pct}%)...",
                          file=sys.stderr, flush=True)

                r = run_one(strategy, tf, combo)
                if r is not None:
                    r["_combo"] = combo
                else:
                    r = {"error": "no output", "_combo": combo}
                results.append(r)

            write_results(strategy, tf, results, md_lines)

    md_lines.append("\n---\n")
    md_lines.append(
        f"*Sweep completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
    )

    with open(out_path, "w") as f:
        f.write("\n".join(md_lines))

    print(f"\nResults written to {out_path}", file=sys.stderr)
    print(f"Total runs: {total_combos}", file=sys.stderr)


if __name__ == "__main__":
    main()
