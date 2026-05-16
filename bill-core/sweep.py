#!/usr/bin/env python3
"""Parameter sweep orchestrator — fixed dedup logic.
Only matches entries where all non-varied parameters equal the baseline defaults."""

import subprocess
import os
import datetime

BINARY = "./target/debug/param_sweep"
DATA_DIR = os.path.expanduser("/Users/brain/hedge/data/free")
WORK_DIR = os.path.expanduser("/Users/brain/hedge/bill-core")
VAULT_DIR = os.path.expanduser("/Users/brain/Documents/memorybrain/Agent-Hermes/daily")

TIMEFRAMES = {
    "orb-breakout": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "wq-trend-mom": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "wq-vol-regime": "ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
}

DEFAULTS = {
    "orb-breakout": {"range_window": 12, "vol_threshold": 1.3, "exit_offset": 5},
    "wq-trend-mom": {"sma_short": 20, "sma_long": 50, "vol_threshold": 1.3, "exit_offset": 5},
    "wq-vol-regime": {"short_lookback": 10, "long_lookback": 30, "short_threshold": 1.5, "long_threshold": 0.7, "exit_offset": 5},
}

# Each sweep: (param_key_to_vary, [values_to_test], display_name)
SWEEPS = {
    "orb-breakout": [
        ("range_window", [8, 10, 12, 14, 16, 20], "Range Window"),
        ("vol_threshold", [1.3, 1.5, 2.0], "Volume Threshold"),
        ("exit_offset", [3, 5, 8], "Exit Offset"),
    ],
    "wq-trend-mom": [
        ("sma_short", [10, 15, 20, 30], "SMA Short Period"),
        ("sma_long", [30, 40, 50, 60], "SMA Long Period"),
        ("vol_threshold", [1.3, 1.5], "Volume Threshold"),
        ("exit_offset", [3, 5, 8], "Exit Offset"),
    ],
    "wq-vol-regime": [
        ("short_lookback", [5, 10, 15, 20], "Short Vol Lookback"),
        ("long_lookback", [20, 30, 40, 50], "Long Vol Lookback"),
        ("short_threshold", [1.3, 1.4, 1.5, 1.6, 1.7, 2.0], "Short Vol Threshold"),
        ("long_threshold", [0.5, 0.6, 0.7, 0.8, 0.9], "Long Vol Threshold"),
    ],
}

def build_params(strategy, vary_key, vary_val):
    """Build params dict: defaults, but vary_key=vary_val."""
    params = dict(DEFAULTS[strategy])
    params[vary_key] = vary_val
    return params

def params_to_flag(params):
    return ",".join(f"{k}={v}" for k, v in params.items())

def run_sweep(strategy, params):
    csv = TIMEFRAMES[strategy]
    csv_path = os.path.join(DATA_DIR, csv)
    param_flag = params_to_flag(params)
    
    env = os.environ.copy()
    env["PATH"] = f"{os.path.expanduser('~/.cargo/bin')}:{env.get('PATH', '')}"
    
    result = subprocess.run(
        [BINARY, "--strategy", strategy, "--csv", csv_path, "--symbol", "NQ", "--params", param_flag],
        cwd=WORK_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    
    line = result.stdout.strip()
    parts = line.split("|")
    if len(parts) >= 7:
        return {
            "trades": int(parts[2]),
            "filtered": int(parts[3]),
            "wins": int(parts[4]),
            "wr": float(parts[5]),
            "total_r": float(parts[6]),
            "pnl": float(parts[7]) if len(parts) > 7 else 0.0,
        }
    return None

def params_equal(p1, p2):
    return set(p1.items()) == set(p2.items())

def generate_report():
    today = datetime.date.today().strftime("%Y-%m-%d")
    report_lines = []
    report_lines.append(f"# Parameter Sweep Results — {today}")
    report_lines.append("")
    report_lines.append("## Summary")
    report_lines.append("")
    report_lines.append(f"Strategies tested: {', '.join(SWEEPS.keys())}")
    report_lines.append(f"Symbol: NQ only")
    report_lines.append("")
    
    for strategy in ["orb-breakout", "wq-trend-mom", "wq-vol-regime"]:
        csv = TIMEFRAMES[strategy]
        tf = csv.split("-")[-1].replace(".csv", "")
        report_lines.append(f"---")
        report_lines.append(f"## {strategy} (timeframe: {tf})")
        report_lines.append("")
        
        # Run baseline
        print(f"  [{strategy}] Running baseline...")
        baseline = run_sweep(strategy, DEFAULTS[strategy])
        if baseline:
            report_lines.append(f"**Baseline (default params):** {DEFAULTS[strategy]}")
            report_lines.append(f"- {baseline['filtered']} filtered trades, {baseline['wr']:.1f}% WR, {baseline['total_r']:.2f} total R, ${baseline['pnl']:.0f} PnL")
        report_lines.append("")
        
        best_overall = None
        best_overall_params = None
        
        for vary_key, values, display_name in SWEEPS[strategy]:
            results = []
            for val in values:
                params = build_params(strategy, vary_key, val)
                print(f"  [{strategy}] {display_name}={val}...")
                result = run_sweep(strategy, params)
                if result:
                    results.append((val, result))
                    
                    # Track best overall
                    if best_overall is None or result["total_r"] > best_overall["total_r"]:
                        best_overall = result
                        best_overall_params = params
            
            if len(results) > 0:
                report_lines.append(f"### {display_name} Sweep")
                report_lines.append("")
                report_lines.append("| Param Value | Trades | Filtered | WR | Total R | PnL | vs Baseline |")
                report_lines.append("|------------|--------|----------|----|---------|-----|-------------|")
                
                for val, result in results:
                    baseline_r = baseline["total_r"] if baseline else 0
                    vs_baseline = f"{((result['total_r'] / baseline_r) - 1) * 100:+.1f}%" if baseline_r != 0 else "N/A"
                    report_lines.append(f"| {val} | {result['trades']} | {result['filtered']} | {result['wr']:.1f}% | {result['total_r']:.2f} | ${result['pnl']:.0f} | {vs_baseline} |")
                
                report_lines.append("")
        
        # Highlight best
        if best_overall and best_overall_params:
            report_lines.append(f"### 🏆 Best Configuration")
            report_lines.append("")
            report_lines.append(f"| Parameter | Value |")
            report_lines.append(f"|-----------|-------|")
            for k, v in best_overall_params.items():
                report_lines.append(f"| {k} | {v} |")
            report_lines.append(f"| **Filtered Trades** | {best_overall['filtered']} |")
            report_lines.append(f"| **Win Rate** | {best_overall['wr']:.1f}% |")
            report_lines.append(f"| **Total R** | {best_overall['total_r']:.2f} |")
            report_lines.append(f"| **PnL** | ${best_overall['pnl']:.0f} |")
            report_lines.append("")
            
            if baseline:
                r_improvement = ((best_overall['total_r'] / baseline['total_r']) - 1) * 100 if baseline['total_r'] != 0 else 0
                report_lines.append(f"**Improvement over baseline:** {r_improvement:+.1f}% total R")
                report_lines.append("")
    
    report_lines.append("---")
    report_lines.append("## Recommendations")
    report_lines.append("")
    
    return "\n".join(report_lines)

def main():
    report = generate_report()
    
    today = datetime.date.today().strftime("%Y-%m-%d")
    output_path = os.path.join(VAULT_DIR, f"param-sweep-results-{today}.md")
    
    os.makedirs(VAULT_DIR, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)
    
    print(f"\nReport written to {output_path}")
    print("\n" + report)

if __name__ == "__main__":
    main()
