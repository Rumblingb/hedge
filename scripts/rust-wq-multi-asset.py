#!/usr/bin/env python3
"""Multi-asset Rust pipeline test — run Rust on all available CSV data files.
Tests ES, NQ, GC, CL, 6E, ZN across available timeframes.
Writes results to state directory.
"""
import subprocess, json, os, sys
from pathlib import Path

HEDGE = "/Users/brain/hedge"
CARGO_DIR = f"{HEDGE}/bill-core"
STATE_DIR = f"{HEDGE}/.rumbling-hedge/state"

# CSV files to test (symbol, timeframe, path)
CSV_FILES = [
    ("ES+NQ", "1m-21d", "ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv"),
    ("ES", "1m-21d", "ES-1m-21d-normalized.csv"),
    ("NQ", "1m-21d", "NQ-1m-21d-normalized.csv"),
    ("ES+NQ", "1d-5y", "ALL-2MARKETS-NQ-ES-1d-5y.csv"),
]

def run_single_bridge(csv_path: str) -> dict:
    result = subprocess.run(
        ["python3", f"{HEDGE}/scripts/rust-wq-bridge.py", csv_path],
        capture_output=True, text=True, timeout=180
    )
    # Read from state file
    state_file = f"{STATE_DIR}/rust-wq-alpha-bridge.json"
    if not os.path.exists(state_file):
        return {"error": f"No output: {csv_path}"}
    try:
        return json.loads(Path(state_file).read_text())
    except:
        return {"error": "Bad JSON"}

def main():
    results = {}
    for symbol, tf, filename in CSV_FILES:
        csv_path = f"{HEDGE}/data/free/{filename}"
        if not os.path.exists(csv_path):
            results[f"{symbol}-{tf}"] = {"error": f"File not found"}
            continue
        
        print(f"Testing {symbol} on {tf}...", file=sys.stderr)
        data = run_single_bridge(csv_path)
        results[f"{symbol}-{tf}"] = {
            "trades": data.get("total_trades", 0),
            "win_rate": data.get("win_rate", 0),
            "net_pnl": data.get("net_pnl", 0),
            "kelly": data.get("kelly_fraction", 0),
            "error": data.get("error")
        }
        
        if "error" in data:
            print(f"  FAILED: {data['error'][:50]}", file=sys.stderr)
        else:
            print(f"  {data.get('total_trades', 0)} trades, {data.get('win_rate', 0)}% WR, +${data.get('net_pnl', 0):,.0f}", file=sys.stderr)
    
    # Write summary
    summary = {
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "results": results
    }
    summary_file = f"{STATE_DIR}/rust-wq-multi-asset.json"
    Path(summary_file).write_text(json.dumps(summary, indent=2))
    print(f"\nSummary written to {summary_file}", file=sys.stderr)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
