#!/usr/bin/env python3
"""Direct param sweep runner — uses compiled binary, no cargo dependency."""
import subprocess
import sys
import os
from datetime import date
from dataclasses import dataclass

BINARY = "/Users/brain/hedge/bill-core/target/release/param_sweep"
WORKDIR = "/Users/brain/hedge/bill-core"
DATA_DIR = "/Users/brain/hedge/data/free"
ENV = dict(os.environ, PATH="/Users/brain/.cargo/bin:/usr/local/bin:/usr/bin:/bin")

CSVS = {
    "5m":  f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-5m.csv",
    "15m": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "30m": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "60m": f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
}

@dataclass
class Result:
    symbol: str; strategy: str; params: str; trades: int
    wins: int; losses: int; wr: float; total_r: float; avg_r: float; max_r: float; min_r: float

def run_sweep(csv_path: str, strategy: str, params_str: str) -> list[Result]:
    cmd = [BINARY, "--csv", csv_path, "--symbol", "NQ", "--strategy", strategy, "--params", params_str]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=WORKDIR, env=ENV)
        if result.returncode != 0:
            print(f"  [ERROR] code={result.returncode} stderr={result.stderr[:120]}", file=sys.stderr)
            return []
        output = result.stdout
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT]", file=sys.stderr); return []
    except Exception as e:
        print(f"  [EXCEPTION] {e}", file=sys.stderr); return []

    results = []
    for line in output.strip().split('\n'):
        if line.startswith("RESULT|"):
            parts = line.split('|')
            if len(parts) >= 11:
                try:
                    symbol, strat, params, trades_s, wl, wr_s, total_r_s, avg_r_s, max_r_s, min_r_s = parts[1:11]
                    trades = int(trades_s)
                    wl_parts = wl.split('/')
                    wins = int(wl_parts[0]); losses = int(wl_parts[1]) if len(wl_parts) > 1 else 0
                    wr = float(wr_s.rstrip('%')); total_r = float(total_r_s)
                    avg_r = float(avg_r_s); max_r = float(max_r_s); min_r = float(min_r_s)
                    results.append(Result(symbol, strat, params, trades, wins, losses, wr, total_r, avg_r, max_r, min_r))
                except (ValueError, IndexError) as e:
                    print(f"  [PARSE ERROR] {line}: {e}", file=sys.stderr)
    return results

def render_table(results: list[Result], title: str, top_n: int = 15):
    ranked = sorted(results, key=lambda r: r.total_r, reverse=True)
    lines = [f"### {title}\n", "| Rank | Strategy | Params | Trades | W/L | WR% | Total R | Avg R |"] 
    lines.append("|------|----------|--------|--------|-----|-----|---------|-------|")
    for rank, r in enumerate(ranked[:top_n], 1):
        lines.append(f"| {rank} | {r.strategy} | {r.params} | {r.trades} | {r.wins}/{r.losses} | {r.wr:.1f}% | {r.total_r:+.2f} | {r.avg_r:+.2f} |")
    lines.append("")
    return "\n".join(lines)

# === SWEEP DEFINITIONS ===

# 1. ORB-BREAKOUT: 15m and 30m
orb_params = []
for rw in [8, 10, 12, 14, 16, 20]:
    orb_params.append((CSVS["15m"], "orb-breakout", f"range_window={rw},vol_threshold=1.3,exit_offset=5,vol_window=10"))
    orb_params.append((CSVS["30m"], "orb-breakout", f"range_window={rw},vol_threshold=1.3,exit_offset=5,vol_window=10"))
for vt in [1.3, 1.5, 2.0]:
    orb_params.append((CSVS["15m"], "orb-breakout", f"range_window=12,vol_threshold={vt},exit_offset=5,vol_window=10"))
    orb_params.append((CSVS["30m"], "orb-breakout", f"range_window=12,vol_threshold={vt},exit_offset=5,vol_window=10"))
for eo in [3, 5, 8]:
    orb_params.append((CSVS["15m"], "orb-breakout", f"range_window=12,vol_threshold=1.3,exit_offset={eo},vol_window=10"))
    orb_params.append((CSVS["30m"], "orb-breakout", f"range_window=12,vol_threshold=1.3,exit_offset={eo},vol_window=10"))
# Best known config
orb_params.append((CSVS["15m"], "orb-breakout", "range_window=12,vol_threshold=1.3,exit_offset=8,vol_window=10"))
orb_params.append((CSVS["30m"], "orb-breakout", "range_window=12,vol_threshold=1.3,exit_offset=8,vol_window=10"))

# 2. WQ-TREND-MOM: 30m
trend_params = []
for ss in [10, 15, 20, 30]:
    trend_params.append((CSVS["30m"], "wq-trend-mom", f"sma_short={ss},sma_long=50,vol_threshold=1.3,exit_offset=5,vol_lookback=10"))
for sl in [30, 40, 50, 60]:
    trend_params.append((CSVS["30m"], "wq-trend-mom", f"sma_short=20,sma_long={sl},vol_threshold=1.3,exit_offset=5,vol_lookback=10"))
for vt in [1.3, 1.5]:
    trend_params.append((CSVS["30m"], "wq-trend-mom", f"sma_short=20,sma_long=50,vol_threshold={vt},exit_offset=5,vol_lookback=10"))
for eo in [3, 5, 8]:
    trend_params.append((CSVS["30m"], "wq-trend-mom", f"sma_short=20,sma_long=50,vol_threshold=1.3,exit_offset={eo},vol_lookback=10"))
trend_params.append((CSVS["30m"], "wq-trend-mom", "sma_short=20,sma_long=50,vol_threshold=1.3,exit_offset=8,vol_lookback=10"))

# 3. WQ-VOL-REGIME: 60m
volreg_params = []
for svl in [5, 10, 15, 20]:
    volreg_params.append((CSVS["60m"], "wq-vol-regime", f"short_lookback={svl},long_lookback=30,short_threshold=1.5,long_threshold=0.7,exit_offset=5"))
for lvl in [20, 30, 40, 50]:
    volreg_params.append((CSVS["60m"], "wq-vol-regime", f"short_lookback=10,long_lookback={lvl},short_threshold=1.5,long_threshold=0.7,exit_offset=5"))
for st in [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]:
    volreg_params.append((CSVS["60m"], "wq-vol-regime", f"short_lookback=10,long_lookback=30,short_threshold={st},long_threshold=0.7,exit_offset=5"))
for lt in [0.5, 0.6, 0.7, 0.8, 0.9]:
    volreg_params.append((CSVS["60m"], "wq-vol-regime", f"short_lookback=10,long_lookback=30,short_threshold=1.5,long_threshold={lt},exit_offset=5"))
volreg_params.append((CSVS["60m"], "wq-vol-regime", "short_lookback=10,long_lookback=30,short_threshold=1.5,long_threshold=0.7,exit_offset=5"))

# === Also test exit_offset on vol-regime ===
for eo in [3, 5, 8]:
    volreg_params.append((CSVS["60m"], "wq-vol-regime", f"short_lookback=10,long_lookback=30,short_threshold=1.5,long_threshold=0.7,exit_offset={eo}"))

def run_all():
    today = date.today().isoformat()
    report_path = f"/Users/brain/Documents/memorybrain/Agent-Hermes/daily/param-sweep-results-{today}.md"
    
    report = f"# Parameter Sweep Results — {today}\n\nSymbol: NQ only\n\n---\n\n"
    
    all_results = {}
    
    for label, tf, params_list in [
        ("orb-breakout-15m", "15m", [p for p in orb_params if "15m" in p[0]]),
        ("orb-breakout-30m", "30m", [p for p in orb_params if "30m" in p[0]]),
        ("wq-trend-mom-30m", "30m", trend_params),
        ("wq-vol-regime-60m", "60m", volreg_params),
    ]:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"SWEEP: {label} ({len(params_list)} combos)", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        
        results = []
        for csv, strat, params in params_list:
            print(f"  Running: {strat} params={params}", file=sys.stderr)
            res = run_sweep(csv, strat, params)
            results.extend(res)
            for r in res:
                print(f"    -> {r}", file=sys.stderr)
        
        all_results[label] = results
        report += render_table(results, f"{label} — All Parameter Variants", top_n=15)
    
    # Overall top performers
    flat = []
    for k, v in all_results.items():
        flat.extend(v)
    report += "\n---\n\n## Overall Top Performers\n\n"
    report += render_table(flat, "All Strategies — Top 20", top_n=20)
    
    # Best per strategy
    report += "\n---\n\n## Best Parameter Combos Per Strategy\n\n"
    for strategy_key, results in all_results.items():
        ranked = sorted(results, key=lambda r: r.total_r, reverse=True)
        if ranked:
            best = ranked[0]
            report += f"### {strategy_key}\n\n"
            report += f"**Best:** `{best.params}` → {best.trades} trades, {best.wins}/{best.losses} W/L, "
            report += f"WR={best.wr:.1f}%, Total R={best.total_r:+.2f}, Avg R={best.avg_r:+.2f}\n\n"
    
    # Recommendations
    report += "\n---\n\n## Recommendations\n\n"
    for strategy_key, results in [
        ("orb-breakout-15m", all_results.get("orb-breakout-15m", [])),
        ("orb-breakout-30m", all_results.get("orb-breakout-30m", [])),
        ("wq-trend-mom-30m", all_results.get("wq-trend-mom-30m", [])),
        ("wq-vol-regime-60m", all_results.get("wq-vol-regime-60m", [])),
    ]:
        ranked = sorted(results, key=lambda r: r.total_r, reverse=True)
        if ranked:
            report += f"- **{strategy_key}**: Best = `{ranked[0].params}` (R={ranked[0].total_r:+.2f}, {ranked[0].trades} trades, {ranked[0].wr:.1f}% WR)\n"
            if len(ranked) > 1:
                report += f"  Runner-up: `{ranked[1].params}` (R={ranked[1].total_r:+.2f}, {ranked[1].trades} trades, {ranked[1].wr:.1f}% WR)\n"
    
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w') as f:
        f.write(report)
    
    print(f"\n\nReport: {report_path}", file=sys.stderr)
    print(f"\n{'='*60}", file=sys.stderr)
    print("SUMMARY:", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    for strategy_key, results in all_results.items():
        ranked = sorted(results, key=lambda r: r.total_r, reverse=True)
        if ranked:
            print(f"\n{strategy_key}:", file=sys.stderr)
            for i, r in enumerate(ranked[:5], 1):
                print(f"  {i}. {r}", file=sys.stderr)
    
    return all_results, report

if __name__ == "__main__":
    all_results, report = run_all()
    print(report)
