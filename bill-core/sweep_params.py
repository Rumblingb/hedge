#!/usr/bin/env python3
"""Parameter sweep runner for top strategies on best timeframes."""
import subprocess, json, sys, os
from itertools import product
from datetime import datetime

BINARY = "./target/release/param_sweep"
CSV_DIR = "../data/free"
TIMEFRAMES = {
    "15m": f"{CSV_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "30m": f"{CSV_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "60m": f"{CSV_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
}

# Strategy sweep definitions
# Format: (strategy_id, list_of_timeframes, [(param_name, [values]), ...])
SWEEPS = [
    {
        "strategy": "orb-breakout",
        "timeframes": ["15m", "30m"],
        "params": {
            "--range-window": [8, 10, 12, 14, 16, 20],
            "--vol-threshold": [1.3, 1.5, 2.0],
            "--exit-offset": [3, 5, 8],
        },
    },
    {
        "strategy": "wq-trend-mom",
        "timeframes": ["30m"],
        "params": {
            "--sma-short": [10, 15, 20, 30],
            "--sma-long": [30, 40, 50, 60],
            "--vol-threshold": [1.3, 1.5],
            "--exit-offset": [3, 5, 8],
        },
    },
    {
        "strategy": "wq-vol-regime",
        "timeframes": ["60m"],
        "params": {
            "--short-lookback": [5, 10, 15, 20],
            "--long-lookback": [20, 30, 40, 50],
            "--short-threshold": [1.3, 1.4, 1.5, 1.6, 1.7, 2.0],
            "--long-threshold": [0.5, 0.6, 0.7, 0.8, 0.9],
        },
    },
]

def run_one(strategy, csv_path, params_dict):
    """Run param_sweep binary with given params, return (params_dict, result_json) or None."""
    cmd = [BINARY, "--strategy", strategy, "--csv", csv_path, "--symbol", "NQ"]
    for k, v in params_dict.items():
        cmd.extend([k, str(v)])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return (params_dict, None, r.stderr.strip())
        return (params_dict, json.loads(r.stdout.strip()), None)
    except Exception as e:
        return (params_dict, None, str(e))

def fmt_params(d):
    return ", ".join(f"{k.split('--')[1] if '--' in k else k}={v}" for k, v in sorted(d.items()))

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    all_results = []
    total = sum(
        len(list(product(*[v for _, vv in sweep["params"].items() for v in [vv]][:0])))  # hack: count combos
        for sweep in SWEEPS
    )
    # Actually count properly:
    total = 0
    for sweep in SWEEPS:
        n_params = 1
        for vals in sweep["params"].values():
            n_params *= len(vals)
        total += n_params * len(sweep["timeframes"])
    print(f"Total runs: {total}")

    run_count = 0
    for sweep in SWEEPS:
        strategy = sweep["strategy"]
        keys = list(sweep["params"].keys())
        value_lists = list(sweep["params"].values())
        param_combos = [dict(zip(keys, combo)) for combo in product(*value_lists)]

        for tf in sweep["timeframes"]:
            csv_path = TIMEFRAMES[tf]
            print(f"\n=== {strategy} on {tf} ({len(param_combos)} combos) ===")

            best = None
            for combo in param_combos:
                params, result, err = run_one(strategy, csv_path, combo)
                run_count += 1
                if result is not None:
                    all_results.append({
                        "strategy": strategy,
                        "timeframe": tf,
                        "params": combo,
                        **result,
                    })
                    total_r = result.get("total_r", 0)
                    wr = result.get("wr", 0)
                    trades_n = result.get("trades", 0)
                    if best is None or total_r > best["total_r"]:
                        best = {"params": combo, "total_r": total_r, "wr": wr, "trades": trades_n, "result": result}
                    if run_count % 50 == 0:
                        print(f"  [{run_count}/{total}] {strategy}/{tf} | {fmt_params(combo)} -> R={total_r:.1f} WR={wr:.0f}% T={trades_n}")
                else:
                    print(f"  ERROR: {fmt_params(combo)} -> {err}")

            if best:
                print(f"  ** BEST {strategy}/{tf}: {fmt_params(best['params'])} -> R={best['total_r']:.1f} WR={best['wr']:.0f}% T={best['trades']}")

    # Write results
    report_path = f"/Users/brain/Documents/memorybrain/Agent-Hermes/daily/param-sweep-results-{datetime.now().strftime('%Y-%m-%d')}.md"
    lines = [
        f"# Parameter Sweep Results — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Total runs: {run_count}",
        "",
    ]

    for sweep in SWEEPS:
        strategy = sweep["strategy"]
        for tf in sweep["timeframes"]:
            lines.append(f"## {strategy} — {tf}")
            lines.append("")
            lines.append("| # | Params | Trades | Wins | Losses | WR% | Total R | Avg R | Longs | Shorts | Long R | Short R |")
            lines.append("|---|--------|--------|------|--------|-----|---------|-------|-------|--------|--------|---------|")

            tf_results = sorted(
                [r for r in all_results if r["strategy"] == strategy and r["timeframe"] == tf],
                key=lambda r: r["total_r"],
                reverse=True,
            )

            for i, r in enumerate(tf_results):
                p = fmt_params(r["params"])
                lines.append(
                    f"| {i+1} | {p} | {r.get('trades',0)} | {r.get('wins',0)} | {r.get('losses',0)} | "
                    f"{r.get('wr',0):.1f} | {r.get('total_r',0):.2f} | {r.get('avg_r',0):.2f} | "
                    f"{r.get('longs',0)} | {r.get('shorts',0)} | {r.get('long_r',0):.2f} | {r.get('short_r',0):.2f} |"
                )

            # Top 5
            top5 = tf_results[:5]
            lines.append("")
            lines.append("### Top 5")
            for i, r in enumerate(top5):
                p = fmt_params(r["params"])
                lines.append(f"{i+1}. R={r['total_r']:.2f}, WR={r['wr']:.1f}%, T={r['trades']} — {p}")

            # Summary stats for top param
            best = tf_results[0]
            lines.append("")
            lines.append(f"**Best params**: {fmt_params(best['params'])}")
            lines.append(f"- Total R: {best.get('total_r',0):.2f}")
            lines.append(f"- Win rate: {best.get('wr',0):.1f}%")
            lines.append(f"- Trades: {best.get('trades',0)}")
            lines.append(f"- Avg R per trade: {best.get('avg_r',0):.2f}")
            lines.append(f"- Longs: {best.get('longs',0)} ({best.get('long_r',0):.2f}R) | Shorts: {best.get('shorts',0)} ({best.get('short_r',0):.2f}R)")
            lines.append("")

    lines.append("---")
    lines.append("")

    # Cross-strategy comparison: best per strategy/timeframe
    lines.append("## Best Per Strategy")
    lines.append("")
    lines.append("| Strategy | TF | Best Total R | WR% | Trades | Best Params |")
    lines.append("|----------|----|-------------|-----|--------|-------------|")
    for sweep in SWEEPS:
        for tf in sweep["timeframes"]:
            tf_results = sorted(
                [r for r in all_results if r["strategy"] == sweep["strategy"] and r["timeframe"] == tf],
                key=lambda r: r["total_r"],
                reverse=True,
            )
            best = tf_results[0]
            lines.append(
                f"| {sweep['strategy']} | {tf} | {best.get('total_r',0):.2f} | "
                f"{best.get('wr',0):.1f}% | {best.get('trades',0)} | {fmt_params(best['params'])} |"
            )

    report = "\n".join(lines)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nResults written to {report_path}")
    print(report)

if __name__ == "__main__":
    main()
