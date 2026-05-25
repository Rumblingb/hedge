#!/usr/bin/env python3
"""Fill gaps in today's parameter sweeps: eo=8 combined with other params."""

import subprocess
import re
import sys
import os
from datetime import date
from dataclasses import dataclass

BINARY = "./target/release/param_sweep"
WORKDIR = "/Users/brain/hedge/bill-core"
DATA_DIR = "/Users/brain/hedge/data/free"

CSVS = {
    "15m": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "30m": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "60m": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
}

@dataclass
class Result:
    symbol: str
    strategy: str
    params: str
    trades: int
    wins: int
    losses: int
    wr: float
    total_r: float
    avg_r: float
    max_r: float
    min_r: float

    def __str__(self):
        return (f"{self.strategy:20s} | {self.params:50s} | "
                f"{self.trades:4d} tr | "
                f"{self.wins}/{self.losses} W/L | "
                f"{self.wr:5.1f}% WR | "
                f"R={self.total_r:+8.2f} | "
                f"avg={self.avg_r:+.2f} | "
                f"max={self.max_r:+.2f}")

def run_sweep(csv_path: str, strategy: str, params_str: str) -> list[Result]:
    cmd = [BINARY, "--csv", csv_path, "--symbol", "NQ", "--strategy", strategy, "--params", params_str]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, cwd=WORKDIR
        )
        output = result.stdout
        if result.returncode != 0:
            print(f"  [ERROR] rc={result.returncode} stderr={result.stderr[:200]}", file=sys.stderr)
            return []
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT]", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  [EXCEPTION] {e}", file=sys.stderr)
        return []

    results = []
    for line in output.strip().split('\n'):
        if line.startswith("RESULT|"):
            parts = line.split('|')
            if len(parts) >= 11:
                try:
                    symbol, strat, params, trades_s, wl, wr_s, total_r_s, avg_r_s, max_r_s, min_r_s = parts[1:11]
                    trades = int(trades_s)
                    wl_parts = wl.split('/')
                    wins = int(wl_parts[0])
                    losses = int(wl_parts[1]) if len(wl_parts) > 1 else 0
                    wr = float(wr_s.rstrip('%'))
                    total_r = float(total_r_s)
                    avg_r = float(avg_r_s)
                    max_r = float(max_r_s)
                    min_r = float(min_r_s)
                    results.append(Result(symbol, strat, params, trades, wins, losses, wr, total_r, avg_r, max_r, min_r))
                except (ValueError, IndexError) as e:
                    print(f"  [PARSE ERROR] line={line}: {e}", file=sys.stderr)
    return results


def rank_results(results: list[Result]) -> list[Result]:
    return sorted(results, key=lambda r: r.total_r, reverse=True)


def render_table(results: list[Result], title: str, top_n: int = 999):
    lines = [f"### {title}\n"]
    lines.append("| Rank | Strategy | Params | Trades | W/L | WR% | Total R | Avg R | Max R |")
    lines.append("|------|----------|--------|--------|-----|-----|---------|-------|-------|")
    for rank, r in enumerate(rank_results(results)[:top_n], 1):
        lines.append(
            f"| {rank} | {r.strategy} | {r.params} | {r.trades} | "
            f"{r.wins}/{r.losses} | {r.wr:.1f}% | {r.total_r:+.2f} | {r.avg_r:+.2f} | {r.max_r:+.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main():
    today = date.today().isoformat()
    report = f"# Parameter Sweep Fill-In Results — {today}\n\n"
    report += "Filling gaps where exit_offset=8 wasn't combined with other param variants.\n\n"
    report += "---\n\n"

    all_results = []
    total_combos = 0

    # ============================
    # 1. WQ-TREND-MOM 30m — eo=8 × SMA variants
    # ============================
    print(f"\n{'='*60}")
    print(f"WQ-TREND-MOM (30m): eo=8 × SMA/vol variants")
    print(f"{'='*60}")
    trend_results = []

    # eo=8 × sma_short variants (sma_long=50, vol_threshold=1.3)
    for ss in [10, 15, 30]:
        p = f"sma_short={ss},sma_long=50,vol_threshold=1.3,exit_offset=8,vol_lookback=10"
        print(f"  Running: {p}")
        for r in run_sweep(CSVS["30m"], "wq-trend-mom", p):
            trend_results.append(r)
            print(f"    -> {r}")
            total_combos += 1

    # eo=8 × sma_long variants (sma_short=20, vol_threshold=1.3)
    for sl in [30, 40, 60]:
        p = f"sma_short=20,sma_long={sl},vol_threshold=1.3,exit_offset=8,vol_lookback=10"
        print(f"  Running: {p}")
        for r in run_sweep(CSVS["30m"], "wq-trend-mom", p):
            trend_results.append(r)
            print(f"    -> {r}")
            total_combos += 1

    # eo=8 × vol_threshold=1.5 (sma_short=20, sma_long=50)
    p = f"sma_short=20,sma_long=50,vol_threshold=1.5,exit_offset=8,vol_lookback=10"
    print(f"  Running: {p}")
    for r in run_sweep(CSVS["30m"], "wq-trend-mom", p):
        trend_results.append(r)
        print(f"    -> {r}")
        total_combos += 1

    report += render_table(trend_results, "WQ-Trend-Mom (30m) — eo=8 × SMA/Vol Variants (Gap Fill)")
    all_results.extend(trend_results)

    # ============================
    # 2. WQ-VOL-REGIME 60m — eo=8 × full grid
    # ============================
    print(f"\n{'='*60}")
    print(f"WQ-VOL-REGIME (60m): eo=8 × full short_threshold × long_threshold grid")
    print(f"{'='*60}")
    volreg_results = []

    # eo=8 × st ∈ [1.3, 1.4, 1.5, 1.6, 1.7] × lt ∈ [0.6, 0.7, 0.8, 0.9]
    # (slb=10, llb=30)
    for st in [1.3, 1.4, 1.5, 1.6, 1.7]:
        for lt in [0.6, 0.7, 0.8, 0.9]:
            p = f"short_lookback=10,long_lookback=30,short_threshold={st},long_threshold={lt},exit_offset=8"
            print(f"  Running: {p}")
            for r in run_sweep(CSVS["60m"], "wq-vol-regime", p):
                volreg_results.append(r)
                print(f"    -> {r}")
                total_combos += 1

    report += render_table(volreg_results, "WQ-Vol-Regime (60m) — eo=8 × st × lt Grid (Gap Fill)")
    all_results.extend(volreg_results)

    # ============================
    # 3. ORB-BREAKOUT 30m — eo=8 × range_window/vol_threshold variants
    # ============================
    print(f"\n{'='*60}")
    print(f"ORB-BREAKOUT (30m): eo=8 × range/vol variants")
    print(f"{'='*60}")
    orb30_results = []

    # eo=8 × range_window variants (vol_threshold=1.3, vol_window=10)
    for rw in [8, 10, 14, 16, 20]:
        p = f"range_window={rw},vol_threshold=1.3,exit_offset=8,vol_window=10"
        print(f"  Running: {p}")
        for r in run_sweep(CSVS["30m"], "orb-breakout", p):
            orb30_results.append(r)
            print(f"    -> {r}")
            total_combos += 1

    # eo=8 × vol_threshold variants (range_window=12, vol_window=10)
    for vt in [1.5, 2.0]:
        p = f"range_window=12,vol_threshold={vt},exit_offset=8,vol_window=10"
        print(f"  Running: {p}")
        for r in run_sweep(CSVS["30m"], "orb-breakout", p):
            orb30_results.append(r)
            print(f"    -> {r}")
            total_combos += 1

    report += render_table(orb30_results, "ORB-Breakout (30m) — eo=8 × Range/Vol Variants (Gap Fill)")
    all_results.extend(orb30_results)

    # ============================
    # 4. ORB-BREAKOUT 15m — eo=8 × range_window/vol_threshold variants
    # ============================
    print(f"\n{'='*60}")
    print(f"ORB-BREAKOUT (15m): eo=8 × range/vol variants")
    print(f"{'='*60}")
    orb15_results = []

    # eo=8 × range_window variants (vol_threshold=1.3, vol_window=10)
    for rw in [8, 10, 14, 16, 20]:
        p = f"range_window={rw},vol_threshold=1.3,exit_offset=8,vol_window=10"
        print(f"  Running: {p}")
        for r in run_sweep(CSVS["15m"], "orb-breakout", p):
            orb15_results.append(r)
            print(f"    -> {r}")
            total_combos += 1

    # eo=8 × vol_threshold variants (range_window=12, vol_window=10)
    for vt in [1.5, 2.0]:
        p = f"range_window=12,vol_threshold={vt},exit_offset=8,vol_window=10"
        print(f"  Running: {p}")
        for r in run_sweep(CSVS["15m"], "orb-breakout", p):
            orb15_results.append(r)
            print(f"    -> {r}")
            total_combos += 1

    report += render_table(orb15_results, "ORB-Breakout (15m) — eo=8 × Range/Vol Variants (Gap Fill)")
    all_results.extend(orb15_results)

    # ============================
    # OVERALL RANKING
    # ============================
    report += "\n---\n\n"
    report += "## Overall Gap-Fill Results\n\n"
    report += f"**Total combos tested:** {total_combos}\n\n"
    report += render_table(all_results, "All Gap-Fill Results (Top 20)", top_n=20)

    # Identify entries that beat the current best in each category
    report += "\n### Key Findings\n\n"

    trend_best = rank_results(trend_results)
    if trend_best:
        report += f"- **wq-trend-mom 30m eo=8 variants:** Best = `{trend_best[0].params}` → R={trend_best[0].total_r:+.2f}\n"
        if trend_best[0].total_r > 252.22:
            report += f"  🏆 **NEW BEST!** Beats previous best (+252.22R) by {trend_best[0].total_r - 252.22:+.2f}R\n"
        else:
            report += f"  Default eo=8 (ss=20,sl=50,vt=1.3) = +252.22R. Best variant = {trend_best[0].total_r:+.2f}R (Δ={trend_best[0].total_r - 252.22:+.2f}R)\n"

    volreg_best = rank_results(volreg_results)
    if volreg_best:
        report += f"- **wq-vol-regime 60m eo=8 full grid:** Best = `{volreg_best[0].params}` → R={volreg_best[0].total_r:+.2f}\n"
        if volreg_best[0].total_r > 252.41:
            report += f"  🏆 **NEW BEST!** Beats previous best (+252.41R) by {volreg_best[0].total_r - 252.41:+.2f}R\n"
        else:
            report += f"  Previous best eo=8 (st=1.6,lt=0.9) = +252.41R. Best in grid = {volreg_best[0].total_r:+.2f}R\n"

    orb30_best = rank_results(orb30_results)
    if orb30_best:
        report += f"- **orb-breakout 30m eo=8 variants:** Best = `{orb30_best[0].params}` → R={orb30_best[0].total_r:+.2f}\n"
        prev_orb30 = 73.86
        if orb30_best[0].total_r > prev_orb30:
            report += f"  🏆 **NEW BEST!** Beats previous best (+{prev_orb30}R) by {orb30_best[0].total_r - prev_orb30:+.2f}R\n"
        else:
            report += f"  Previous best (rw=12,vt=1.3,eo=8) = +{prev_orb30}R. Best variant = {orb30_best[0].total_r:+.2f}R (Δ={orb30_best[0].total_r - prev_orb30:+.2f}R)\n"

    orb15_best = rank_results(orb15_results)
    if orb15_best:
        report += f"- **orb-breakout 15m eo=8 variants:** Best = `{orb15_best[0].params}` → R={orb15_best[0].total_r:+.2f}\n"
        prev_orb15 = 20.17
        if orb15_best[0].total_r > prev_orb15:
            report += f"  🏆 **NEW BEST!** Beats previous best (+{prev_orb15}R) by {orb15_best[0].total_r - prev_orb15:+.2f}R\n"
        else:
            report += f"  Previous best (rw=12,vt=1.3,eo=8) = +{prev_orb15}R. Best variant = {orb15_best[0].total_r:+.2f}R\n"

    # ============================
    # FINAL RECOMMENDATIONS
    # ============================
    report += "\n### Updated Recommendations\n\n"

    # Combine with previous best-known results
    all_prev_best = {
        "wq-trend-mom-30m": ("vol_threshold=1.3,exit_offset=8,sma_long=50,vol_lookback=10,sma_short=20", 252.22, 60.7, 173),
        "wq-vol-regime-60m": ("short_lookback=10,long_lookback=30,short_threshold=1.6,long_threshold=0.9,exit_offset=8", 252.41, 67.7, 158),
        "orb-breakout-30m": ("vol_window=10,range_window=12,exit_offset=8,vol_threshold=1.3", 73.86, 58.2, 79),
        "orb-breakout-15m": ("exit_offset=8,vol_threshold=1.3,vol_window=10,range_window=12", 20.17, 45.3, 161),
    }

    for key, best_list, label in [
        ("wq-trend-mom-30m", trend_results, "wq-trend-mom (30m)"),
        ("wq-vol-regime-60m", volreg_results, "wq-vol-regime (60m)"),
        ("orb-breakout-30m", orb30_results, "orb-breakout (30m)"),
        ("orb-breakout-15m", orb15_results, "orb-breakout (15m)"),
    ]:
        ranked = rank_results(best_list)
        prev = all_prev_best[key]
        best_in_group = ranked[0] if ranked else None

        if best_in_group and best_in_group.total_r > prev[1]:
            report += f"- **{label}**: 🏆 **NEW BEST** = `{best_in_group.params}` → R={best_in_group.total_r:+.2f}, {best_in_group.wr:.1f}% WR, {best_in_group.trades} trades\n"
            report += f"  (Previous best was `{prev[0]}` → R={prev[1]:+.2f}, WR={prev[2]:.1f}%, {prev[3]} trades)\n"
        else:
            report += f"- **{label}**: Best confirmed = `{prev[0]}` → R={prev[1]:+.2f}, WR={prev[2]:.1f}%, {prev[3]} trades\n"
            if best_in_group:
                report += f"  Best in gap-fill: `{best_in_group.params}` → R={best_in_group.total_r:+.2f} (Δ={best_in_group.total_r - prev[1]:+.2f}R from prev best)\n"

    # Write report
    report_path = f"/Users/brain/Documents/memorybrain/Agent-Hermes/daily/param-sweep-results-{today}.md"
    with open(report_path, 'w') as f:
        f.write(report)

    print(f"\n\n{'='*60}")
    print(f"Report written to: {report_path}")
    print(f"Total combos tested: {total_combos}")
    print(f"{'='*60}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY:")
    print(f"{'='*60}")

    for label, results in [
        ("wq-trend-mom eo=8 SMA/vol variants", trend_results),
        ("wq-vol-regime eo=8 full grid", volreg_results),
        ("orb-breakout 30m eo=8 variants", orb30_results),
        ("orb-breakout 15m eo=8 variants", orb15_results),
    ]:
        ranked = rank_results(results)
        if ranked:
            print(f"\n{label}:")
            for i, r in enumerate(ranked[:5], 1):
                print(f"  {i}. {r}")

    return all_results


if __name__ == "__main__":
    main()
