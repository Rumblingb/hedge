#!/usr/bin/env python3
"""Orchestrate param_sweep for orb-breakout, wq-trend-mom, wq-vol-regime."""
import subprocess, json, sys, os, itertools, time
from datetime import datetime

WORKDIR = "/Users/brain/hedge/bill-core"
BINARY = "./target/release/param_sweep"
DATA = os.path.expanduser("~/hedge/data/free")
SYMBOL = "NQ"
RESULTS_FILE = os.path.expanduser(f"~/Documents/memorybrain/Agent-Hermes/daily/param-sweep-results-{datetime.now().strftime('%Y-%m-%d')}.md")

CSVS = {
    "15m": f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "30m": f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "60m": f"{DATA}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
}

def run_one(args):
    """Run param_sweep with given args, return parsed dict."""
    cmd = [BINARY] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=WORKDIR)
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "non-zero exit"}
        line = result.stdout.strip()
        if not line:
            return {"error": "empty stdout"}
        return json.loads(line)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except json.JSONDecodeError as e:
        return {"error": f"json: {e}", "raw": result.stdout[:500] if 'result' in dir() else ""}

def sweep_orb_breakout():
    """Sweep orb-breakout on 15m and 30m."""
    results = {"15m": [], "30m": []}
    range_windows = [8, 10, 12, 14, 16, 20]
    vol_thresholds = [1.3, 1.5, 2.0]
    exit_offsets = [3, 5, 8]
    total = len(range_windows) * len(vol_thresholds) * len(exit_offsets) * 2
    done = 0

    for tf in ["15m", "30m"]:
        csv = CSVS[tf]
        for rw in range_windows:
            for vt in vol_thresholds:
                for eo in exit_offsets:
                    args = [
                        "--csv", csv,
                        "--symbol", SYMBOL,
                        "--strategy", "orb-breakout",
                        "--range-window", str(rw),
                        "--vol-threshold", str(vt),
                        "--exit-offset", str(eo),
                    ]
                    data = run_one(args)
                    data.update({"range_window": rw, "vol_threshold": vt, "exit_offset": eo, "tf": tf})
                    results[tf].append(data)
                    done += 1
                    if data.get("error"):
                        print(f"  [{done}/{total}] ERR {tf} rw={rw} vt={vt} eo={eo}: {data['error']}", file=sys.stderr)
                    else:
                        print(f"  [{done}/{total}] {tf} rw={rw} vt={vt} eo={eo}: {data.get('trades',0)} trades, {data.get('total_r',0):+.2f}R", file=sys.stderr)
    return results

def sweep_wq_trend_mom():
    """Sweep wq-trend-mom on 30m."""
    results = {"30m": []}
    sma_shorts = [10, 15, 20, 30]
    sma_longs = [30, 40, 50, 60]
    vol_thresholds = [1.3, 1.5]
    exit_offsets = [3, 5, 8]
    total = len(sma_shorts) * len(sma_longs) * len(vol_thresholds) * len(exit_offsets)
    done = 0

    for ss in sma_shorts:
        for sl in sma_longs:
            if ss >= sl:
                continue  # short must be < long
            for vt in vol_thresholds:
                for eo in exit_offsets:
                    args = [
                        "--csv", CSVS["30m"],
                        "--symbol", SYMBOL,
                        "--strategy", "wq-trend-mom",
                        "--sma-short", str(ss),
                        "--sma-long", str(sl),
                        "--vol-threshold", str(vt),
                        "--exit-offset", str(eo),
                    ]
                    data = run_one(args)
                    data.update({"sma_short": ss, "sma_long": sl, "vol_threshold": vt, "exit_offset": eo, "tf": "30m"})
                    results["30m"].append(data)
                    done += 1
                    if data.get("error"):
                        print(f"  [{done}/{total}] ERR 30m ss={ss} sl={sl} vt={vt} eo={eo}: {data['error']}", file=sys.stderr)
                    else:
                        print(f"  [{done}/{total}] 30m ss={ss} sl={sl} vt={vt} eo={eo}: {data.get('trades',0)} trades, {data.get('total_r',0):+.2f}R", file=sys.stderr)
    return results

def sweep_wq_vol_regime():
    """Sweep wq-vol-regime on 60m."""
    results = {"60m": []}
    short_lookbacks = [5, 10, 15, 20]
    long_lookbacks = [20, 30, 40, 50]
    short_thresholds = [1.3, 1.4, 1.5, 1.6, 1.7, 2.0]
    long_thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
    total = len(short_lookbacks) * len(long_lookbacks) * len(short_thresholds) * len(long_thresholds)
    done = 0

    for slb in short_lookbacks:
        for llb in long_lookbacks:
            if slb >= llb:
                continue  # short lookback must be < long lookback
            for st in short_thresholds:
                for lt in long_thresholds:
                    args = [
                        "--csv", CSVS["60m"],
                        "--symbol", SYMBOL,
                        "--strategy", "wq-vol-regime",
                        "--short-lookback", str(slb),
                        "--long-lookback", str(llb),
                        "--short-threshold", str(st),
                        "--long-threshold", str(lt),
                        "--exit-offset", "5",
                    ]
                    data = run_one(args)
                    data.update({"short_lookback": slb, "long_lookback": llb, "short_threshold": st, "long_threshold": lt, "exit_offset": 5, "tf": "60m"})
                    results["60m"].append(data)
                    done += 1
                    if data.get("error"):
                        print(f"  [{done}/{total}] ERR 60m slb={slb} llb={llb} st={st} lt={lt}: {data['error']}", file=sys.stderr)
                    else:
                        print(f"  [{done}/{total}] 60m slb={slb} llb={llb} st={st} lt={lt}: {data.get('trades',0)} trades, {data.get('total_r',0):+.2f}R", file=sys.stderr)
    return results

def format_sweep_results(results, title):
    """Format sweep results as markdown table, sorted by total_r descending."""
    lines = [f"\n## {title}\n"]
    if not results:
        lines.append("No results.\n")
        return "\n".join(lines)

    # Determine params from first result
    param_keys = [k for k in results[0].keys() if k not in ("trades", "wins", "losses", "wr", "total_r", "avg_r", "tf", "csv", "symbol", "strategy", "error", "raw")]
    
    # Sort by total_r descending
    sorted_results = sorted(results, key=lambda r: r.get("total_r", 0.0), reverse=True)

    # Header
    header = "| " + " | ".join(p.replace("_", " ") for p in param_keys) + " | Trades | W/L | WR% | Total R | Avg R |"
    sep = "| " + " | ".join("---" for _ in param_keys) + " | --- | --- | --- | --- | --- |"
    lines.append(header)
    lines.append(sep)

    for r in sorted_results:
        vals = [str(r.get(p, "")) for p in param_keys]
        trades = r.get("trades", 0)
        wins = r.get("wins", 0)
        losses = r.get("losses", 0)
        wr = r.get("wr", 0.0)
        total_r = r.get("total_r", 0.0)
        avg_r = r.get("avg_r", 0.0)
        row = "| " + " | ".join(vals) + f" | {trades} | {wins}/{losses} | {wr:.1f} | {total_r:+.2f} | {avg_r:.2f} |"
        lines.append(row)

    # Top 5 highlight
    lines.append("\n**Top 5 by Total R:**\n")
    for i, r in enumerate(sorted_results[:5]):
        vals_str = ", ".join(f"{k}={r.get(k, '')}" for k in param_keys)
        lines.append(f"   {i+1}. {vals_str} → {r.get('trades',0)} trades, {r.get('total_r',0):+.2f}R, {r.get('wr',0):.1f}% WR")

    return "\n".join(lines)

def main():
    print("="*60, file=sys.stderr)
    print("PARAM SWEEP RUNNER", file=sys.stderr)
    print(f"Started: {datetime.now().isoformat()}", file=sys.stderr)
    print("="*60, file=sys.stderr)
    sys.stderr.flush()

    all_sections = []
    all_sections.append(f"# Param Sweep Results — {datetime.now().strftime('%Y-%m-%d')}\n")
    all_sections.append("**Note:** All runs on NQ only (faster, primary target).\n")

    # 1. orb-breakout on 15m
    print("\n--- ORB-BREAKOUT ON 15m ---", file=sys.stderr)
    sys.stderr.flush()
    t0 = time.time()
    orb_15m = sweep_orb_breakout()["15m"]
    dt = time.time() - t0
    print(f"  Done in {dt:.1f}s", file=sys.stderr)
    all_sections.append(format_sweep_results(orb_15m, "orb-breakout on 15m"))

    # 2. orb-breakout on 30m
    print("\n--- ORB-BREAKOUT ON 30m ---", file=sys.stderr)
    sys.stderr.flush()
    t0 = time.time()
    orb_30m = sweep_orb_breakout()["30m"]
    dt = time.time() - t0
    print(f"  Done in {dt:.1f}s", file=sys.stderr)
    all_sections.append(format_sweep_results(orb_30m, "orb-breakout on 30m"))

    # 3. wq-trend-mom on 30m
    print("\n--- WQ-TREND-MOM ON 30m ---", file=sys.stderr)
    sys.stderr.flush()
    t0 = time.time()
    trend = sweep_wq_trend_mom()["30m"]
    dt = time.time() - t0
    print(f"  Done in {dt:.1f}s", file=sys.stderr)
    all_sections.append(format_sweep_results(trend, "wq-trend-mom on 30m"))

    # 4. wq-vol-regime on 60m
    print("\n--- WQ-VOL-REGIME ON 60m ---", file=sys.stderr)
    sys.stderr.flush()
    t0 = time.time()
    vol = sweep_wq_vol_regime()["60m"]
    dt = time.time() - t0
    print(f"  Done in {dt:.1f}s", file=sys.stderr)
    all_sections.append(format_sweep_results(vol, "wq-vol-regime on 60m"))

    # Write results file
    content = "\n".join(all_sections)
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        f.write(content)
    print(f"\nResults written to: {RESULTS_FILE}", file=sys.stderr)
    
    # Also print summary to stdout
    print(content)

if __name__ == "__main__":
    main()
