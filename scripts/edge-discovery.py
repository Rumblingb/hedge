#!/usr/bin/env python3
"""Direct Rust output parser — edge discovery from multi_pipeline stdout."""
import subprocess, json, os, re, sys
from pathlib import Path
from datetime import datetime

HEDGE = "/Users/brain/hedge"
CARGO = f"{HEDGE}/bill-core/target/debug/multi_pipeline"
OUT_DIR = f"{HEDGE}/.rumbling-hedge/state"

CSVS = {
    "NQ-1m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv",
    "ES-1m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv",
    "NQ-5m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-5m.csv",
    "ES-5m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-5m.csv",
    "NQ-15m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "ES-15m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
    "NQ-30m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "ES-30m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
    "NQ-60m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
    "ES-60m": "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
    "NQ-1d": "data/free/ALL-2MARKETS-NQ-ES-1d-5y.csv",
    "ES-1d": "data/free/ALL-2MARKETS-NQ-ES-1d-5y.csv",
}

def main():
    # Run each CSV separately with --symbol to get per-symbol results
    results = []
    
    for key, csv_path in CSVS.items():
        sym, tf = key.split("-", 1)
        full_path = f"{HEDGE}/{csv_path}"
        if not os.path.exists(full_path):
            continue
        
        print(f"Testing {key}...", file=sys.stderr)
        result = subprocess.run(
            [CARGO, full_path, "--symbol", sym],
            capture_output=True, text=True, timeout=180
        )
        
        if result.returncode != 0:
            print(f"  FAILED", file=sys.stderr)
            continue
        
        out = result.stdout
        # Parse Combined line
        m = re.search(r'Combined.*?(\d+) trades, (\d+)/(\d+) W/L \(([\d.]+)% WR\), PnL \+?\$?(-?[\d.]+)', out)
        if m:
            trades = int(m.group(1))
            wins = int(m.group(2))
            losses = int(m.group(3))
            wr = float(m.group(4))
            pnl = float(m.group(5))
            results.append({
                "key": key,
                "symbol": sym,
                "timeframe": tf,
                "trades": trades,
                "win_rate": wr,
                "pnl": pnl,
                "trades_per_day": round(trades / 21, 1) if tf != "1d" else round(trades / 1258, 1),
            })
            print(f"  {trades}t, {wr}% WR, ${pnl:+,.0f}", file=sys.stderr)
    
    # Build report
    positive = [r for r in results if r["pnl"] > 0 and r["trades"] >= 10]
    negative = [r for r in results if r["pnl"] <= 0 and r["trades"] >= 10]
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_edges_tested": len(results),
        "positive_edges": len(positive),
        "negative_edges": len(negative),
        "all_results": sorted(results, key=lambda x: -x["pnl"]),
        "positive_edges_detail": sorted(positive, key=lambda x: -x["pnl"]),
        "portfolio_total_pnl": sum(r["pnl"] for r in results if r["pnl"] > 0),
        "portfolio_total_trades": sum(r["trades"] for r in positive),
    }
    
    out_path = f"{OUT_DIR}/rust-edges-discovery.json"
    Path(out_path).write_text(json.dumps(report, indent=2))
    print(f"\nWritten to {out_path}", file=sys.stderr)
    print(f"\n=== EDGE REPORT ===")
    print(f"Total edges: {len(results)} ({len(positive)} positive, {len(negative)} negative)")
    print(f"Portfolio PnL: ${report['portfolio_total_pnl']:,.0f}")
    print(f"\nTop Edges:")
    for r in report["all_results"][:5]:
        print(f"  {r['key']}: {r['trades']}t, {r['win_rate']}% WR, ${r['pnl']:+,.0f}, {r['trades_per_day']}/day")

if __name__ == "__main__":
    main()
