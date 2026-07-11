#!/usr/bin/env python3
"""Parameter sweep runner for bill-core strategies.

Runs all parameter combinations for specified strategies on designated timeframes.
"""

import subprocess
import sys
import os
import itertools
import time
from datetime import datetime

BINARY = "./target/release/param_sweep"
DATA_DIR = "../data/free"

TIMEFRAMES = {
    "15m": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "30m": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "60m": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
    "daily": "ALL-2MARKETS-NQ-ES-1d-5y.csv",
}

# Strategy parameter grids
STRATEGIES = {
    "orb-breakout": {
        "timeframes": ["15m", "30m"],
        "params": {
            "range_window": [8, 10, 12, 14, 16, 20],
            "vol_threshold": [1.3, 1.5, 2.0],
            "exit_offset": [3, 5, 8],
        },
    },
    "wq-trend-mom": {
        "timeframes": ["30m"],
        "params": {
            "sma_short": [10, 15, 20, 30],
            "sma_long": [30, 40, 50, 60],
            "vol_threshold": [1.3, 1.5],
            "exit_offset": [3, 5, 8],
        },
    },
    "wq-vol-regime": {
        "timeframes": ["60m"],
        "params": {
            "short_lookback": [5, 10, 15, 20],
            "long_lookback": [20, 30, 40, 50],
            "short_threshold": [1.3, 1.4, 1.5, 1.6, 1.7, 2.0],
            "long_threshold": [0.5, 0.6, 0.7, 0.8, 0.9],
        },
    },
}


def run_single(strategy, timeframe, params):
    """Run a single param_sweep invocation and return parsed results."""
    csv_path = os.path.join(DATA_DIR, TIMEFRAMES[timeframe])
    param_str = ",".join(f"{k}={v}" for k, v in params.items())

    cmd = [
        BINARY,
        "--strategy", strategy,
        "--csv", csv_path,
        "--symbol", "NQ",
        "--params", param_str,
    ]

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    elapsed = time.time() - start

    if result.returncode != 0:
        return {
            "error": result.stderr.strip(),
            "elapsed": elapsed,
            "strategy": strategy,
            "timeframe": timeframe,
            "params": params,
        }

    # Parse output: strategy|symbol|trades|filtered|wins|wr%|totalR|filteredPnL
    line = result.stdout.strip()
    parts = line.split("|")

    if len(parts) >= 8:
        trades = int(parts[2])
        filtered = int(parts[3])
        wins = int(parts[4])
        wr = float(parts[5])
        total_r = float(parts[6])
        pnl = float(parts[7])
    else:
        trades = 0
        filtered = 0
        wins = 0
        wr = 0.0
        total_r = 0.0
        pnl = 0.0

    return {
        "strategy": strategy,
        "timeframe": timeframe,
        "params": params,
        "trades": trades,
        "filtered": filtered,
        "wins": wins,
        "losses": filtered - wins,
        "wr": wr,
        "total_r": total_r,
        "pnl": pnl,
        "elapsed": elapsed,
    }


def run_sweep(strategy_name, config):
    """Run full sweep for a strategy across its designated timeframes."""
    all_results = []
    param_names = list(config["params"].keys())
    param_values = list(config["params"].values())
    total_combos = len(list(itertools.product(*param_values)))
    total_runs = total_combos * len(config["timeframes"])

    print(f"\n{'='*70}")
    print(f"Strategy: {strategy_name}")
    print(f"Timeframes: {', '.join(config['timeframes'])}")
    print(f"Parameter combos per timeframe: {total_combos}")
    print(f"Total runs: {total_runs}")
    print(f"{'='*70}")

    run_count = 0
    for timeframe in config["timeframes"]:
        timeframe_label = f"[{timeframe}]"
        for combo in itertools.product(*param_values):
            params = dict(zip(param_names, combo))
            run_count += 1

            print(f"  {timeframe_label} ({run_count}/{total_runs}): ", end="")
            param_desc = ", ".join(f"{k}={v}" for k, v in params.items())
            sys.stdout.flush()

            result = run_single(strategy_name, timeframe, params)
            all_results.append(result)

            if "error" in result:
                print(f"ERROR: {result['error']}")
            else:
                print(f"{result['filtered']} trades, {result['wr']:.1f}% WR, "
                      f"{result['total_r']:.2f} R, ${result['pnl']:.0f} PnL "
                      f"[{result['elapsed']:.1f}s]")
            sys.stdout.flush()

    return all_results


def rank_results(results, metric="total_r", top_n=20):
    """Rank results by a given metric."""
    valid = [r for r in results if "error" not in r and r["filtered"] > 0]
    ranked = sorted(valid, key=lambda r: r[metric], reverse=True)
    return ranked[:top_n]


def print_summary(all_results, strategy_name):
    """Print summary table of top results."""
    # Group by timeframe
    by_tf = {}
    for r in all_results:
        if "error" in r:
            continue
        tf = r["timeframe"]
        if tf not in by_tf:
            by_tf[tf] = []
        by_tf[tf].append(r)

    print(f"\n\n{'='*70}")
    print(f"TOP RESULTS: {strategy_name}")
    print(f"{'='*70}")

    for tf, results in by_tf.items():
        print(f"\n--- {tf} ---")

        # Rank by total R
        ranked_r = sorted(
            [r for r in results if r["filtered"] > 0],
            key=lambda r: r["total_r"], reverse=True
        )[:10]

        # Rank by Sharpe-like metric (R / sqrt(trades))
        ranked_sharpe = sorted(
            [r for r in results if r["filtered"] > 3 and r["total_r"] > 0],
            key=lambda r: r["total_r"] / max(r["filtered"] ** 0.5, 1),
            reverse=True
        )[:10]

        # Rank by win rate
        ranked_wr = sorted(
            [r for r in results if r["filtered"] > 5],
            key=lambda r: r["wr"], reverse=True
        )[:10]

        print("\n  By Total R:")
        print(f"  {'Params':<55} {'Trades':>6} {'WR%':>6} {'Tot R':>8} {'$/trade':>8}")
        print(f"  {'-'*55} {'-'*6} {'-'*6} {'-'*8} {'-'*8}")
        for r in ranked_r:
            param_desc = ", ".join(f"{k}={v}" for k, v in r["params"].items())
            pp_trade = r["pnl"] / max(r["filtered"], 1)
            print(f"  {param_desc:<55} {r['filtered']:>6} {r['wr']:>5.1f}% {r['total_r']:>8.2f} ${pp_trade:>7.0f}")

        print("\n  By R/√(trades) (sharpness):")
        print(f"  {'Params':<55} {'Trades':>6} {'R/√N':>8} {'Tot R':>8} {'WR%':>6}")
        print(f"  {'-'*55} {'-'*6} {'-'*8} {'-'*8} {'-'*6}")
        for r in ranked_sharpe:
            param_desc = ", ".join(f"{k}={v}" for k, v in r["params"].items())
            r_sqrt = r["total_r"] / max(r["filtered"] ** 0.5, 1)
            print(f"  {param_desc:<55} {r['filtered']:>6} {r_sqrt:>8.3f} {r['total_r']:>8.2f} {r['wr']:>5.1f}%")

        print("\n  By Win Rate (min 5 trades):")
        print(f"  {'Params':<55} {'Trades':>6} {'WR%':>6} {'Tot R':>8} {'$/trade':>8}")
        print(f"  {'-'*55} {'-'*6} {'-'*6} {'-'*8} {'-'*8}")
        for r in ranked_wr:
            param_desc = ", ".join(f"{k}={v}" for k, v in r["params"].items())
            pp_trade = r["pnl"] / max(r["filtered"], 1)
            print(f"  {param_desc:<55} {r['filtered']:>6} {r['wr']:>5.1f}% {r['total_r']:>8.2f} ${pp_trade:>7.0f}")

    # Best overall
    all_valid = [r for r in all_results if "error" not in r and r["filtered"] > 3]
    if all_valid:
        print(f"\n\n  BEST OVERALL (by total R):")
        best = max(all_valid, key=lambda r: r["total_r"])
        print(f"  {best['timeframe']} | params: {best['params']}")
        print(f"  {best['filtered']} trades, {best['wr']:.1f}% WR, "
              f"{best['total_r']:.2f} total R, ${best['pnl']:.0f} PnL")

        print(f"\n  BEST OVERALL (by R/√N):")
        best_sharp = max(
            [r for r in all_valid if r["total_r"] > 0],
            key=lambda r: r["total_r"] / max(r["filtered"] ** 0.5, 1)
        )
        r_sqrt = best_sharp["total_r"] / max(best_sharp["filtered"] ** 0.5, 1)
        print(f"  {best_sharp['timeframe']} | params: {best_sharp['params']}")
        print(f"  {best_sharp['filtered']} trades, {best_sharp['wr']:.1f}% WR, "
              f"{best_sharp['total_r']:.2f} total R, R/√N={r_sqrt:.3f}")


def save_results(all_results, strategy_name, start_time):
    """Save detailed results to a file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elapsed = time.time() - start_time

    lines = []
    lines.append(f"# Param Sweep Results: {strategy_name}")
    lines.append(f"Generated: {timestamp}")
    lines.append(f"Elapsed: {elapsed:.1f}s")
    lines.append(f"Total runs: {len(all_results)}")
    lines.append("")
    lines.append("| timeframe | " + " | ".join(list(all_results[0]["params"].keys())) + " | trades | filtered | wins | losses | WR% | totalR | PnL |")
    sep_parts = ["---"] * (3 + len(list(all_results[0]["params"].keys())) + 6)
    lines.append("|" + "|".join(sep_parts) + "|")

    for r in sorted(all_results, key=lambda x: x["total_r"], reverse=True):
        if "error" in r:
            lines.append(f"| {r['timeframe']} | ERROR: {r['error']} |")
            continue
        param_vals = " | ".join(str(r["params"].get(k, "")) for k in r["params"])
        lines.append(
            f"| {r['timeframe']} | {param_vals} "
            f"| {r['trades']} | {r['filtered']} | {r['wins']} | {r['losses']} "
            f"| {r['wr']:.1f} | {r['total_r']:.2f} | ${r['pnl']:.0f} |"
        )

    return "\n".join(lines)


def format_markdown_report(all_results):
    """Create a clean markdown summary for the daily note."""
    lines = []
    lines.append("## Parameter Sweep Results\n")

    # Group by strategy then timeframe
    by_strat_tf = {}
    for r in all_results:
        key = (r["strategy"], r["timeframe"])
        if key not in by_strat_tf:
            by_strat_tf[key] = []
        by_strat_tf[key].append(r)

    for strat_tf, results in sorted(by_strat_tf.items()):
        strategy_name, tf = strat_tf
        # Skip errors and empty
        valid = [r for r in results if "error" not in r and r["filtered"] > 0]
        if not valid:
            continue

        # Top 5 by total R
        top_r = sorted(valid, key=lambda r: r["total_r"], reverse=True)[:5]
        # Top 5 by R/√N
        top_sharp = sorted(
            [r for r in valid if r["total_r"] > 0],
            key=lambda r: r["total_r"] / max(r["filtered"] ** 0.5, 1),
            reverse=True
        )[:5]

        lines.append(f"### {strategy_name} — {tf}\n")
        lines.append(f"**Parameter grid:** {len(results)} combinations\n")

        # Default params
        default_params = {
            "orb-breakout": {"range_window": 12, "vol_threshold": 1.3, "exit_offset": 5},
            "wq-trend-mom": {"sma_short": 20, "sma_long": 50, "vol_threshold": 1.3, "exit_offset": 8},
            "wq-vol-regime": {"short_lookback": 10, "long_lookback": 30, "short_threshold": 1.5, "long_threshold": 0.7, "exit_offset": 5},
        }

        # Find default performance
        defaults = default_params.get(strategy_name, {})
        default_result = None
        for r in results:
            if r.get("params") == defaults:
                default_result = r
                break

        if default_result:
            lines.append(f"**Default params:** {defaults}")
            lines.append(f"  → {default_result['filtered']} trades, {default_result['wr']:.1f}% WR, "
                         f"{default_result['total_r']:.2f} total R, ${default_result['pnl']:.0f} PnL\n")

        lines.append("**Top 5 by Total R:**")
        lines.append("| Params | Trades | WR% | Total R | $PnL | $/Trade |")
        lines.append("|--------|--------|-----|---------|------|---------|")
        for r in top_r:
            param_desc = ", ".join(f"{k}={v}" for k, v in r["params"].items())
            pp_trade = r["pnl"] / max(r["filtered"], 1)
            lines.append(f"| {param_desc} | {r['filtered']} | {r['wr']:.1f}% | {r['total_r']:.2f} | ${r['pnl']:.0f} | ${pp_trade:.0f} |")

        lines.append("\n**Top 5 by R/√N (sharpness):**")
        lines.append("| Params | Trades | WR% | Total R | R/√N |")
        lines.append("|--------|--------|-----|---------|------|")
        for r in top_sharp:
            param_desc = ", ".join(f"{k}={v}" for k, v in r["params"].items())
            r_sqrt = r["total_r"] / max(r["filtered"] ** 0.5, 1)
            lines.append(f"| {param_desc} | {r['filtered']} | {r['wr']:.1f}% | {r['total_r']:.2f} | {r_sqrt:.3f} |")

        lines.append("")

        # Best improvement over default
        if default_result and top_r[0]["total_r"] > default_result["total_r"]:
            improvement = (top_r[0]["total_r"] - default_result["total_r"]) / abs(default_result["total_r"]) * 100 if default_result["total_r"] != 0 else float('inf')
            lines.append(f"**Best improvement over default:** +{improvement:.1f}% R "
                         f"(default: {default_result['total_r']:.2f}R → best: {top_r[0]['total_r']:.2f}R)\n")

    return "\n".join(lines)


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    start_time = time.time()

    all_results = []
    all_final = []

    for strategy_name, config in STRATEGIES.items():
        results = run_sweep(strategy_name, config)
        all_results.append(results)
        print_summary(results, strategy_name)

    # Create markdown report
    flat_results = [r for batch in all_results for r in batch]
    md_report = format_markdown_report(flat_results)

    # Save detailed CSV
    detailed_name = f"param_sweep_detailed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(detailed_name, "w") as f:
        f.write("strategy,timeframe,")
        # Get param names from first result
        if flat_results:
            param_names = list(flat_results[0]["params"].keys())
            f.write(",".join(param_names) + ",trades,filtered,wins,losses,wr,total_r,pnl\n")
            for r in flat_results:
                if "error" in r:
                    continue
                param_vals = ",".join(str(r["params"].get(k, "")) for k in param_names)
                f.write(f"{r['strategy']},{r['timeframe']},{param_vals},"
                        f"{r['trades']},{r['filtered']},{r['wins']},{r['losses']},"
                        f"{r['wr']},{r['total_r']},{r['pnl']}\n")

    elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"ALL SWEEPS COMPLETE in {elapsed:.1f}s")
    print(f"Detailed results saved to: {detailed_name}")
    print(f"{'='*70}")

    # Output the markdown report for use
    print("\n\n=== MARKDOWN REPORT ===\n")
    print(md_report)

    # Save markdown report
    md_path = f"/Users/brain/Documents/memorybrain/Agent-Hermes/daily/param-sweep-results-{datetime.now().strftime('%Y-%m-%d')}.md"
    with open(md_path, "w") as f:
        f.write(md_report)
    print(f"\nMarkdown saved to: {md_path}")


if __name__ == "__main__":
    main()
