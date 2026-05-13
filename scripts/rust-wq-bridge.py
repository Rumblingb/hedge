#!/usr/bin/env python3
"""Rust WQ Alpha pipeline bridge — run the proven Rust demo and output structured JSON."""
import subprocess, json, re, sys
from pathlib import Path

CARGO_DIR = "/Users/brain/hedge/bill-core"
OUT_DIR = "/Users/brain/hedge/.rumbling-hedge/state"
DEFAULT_CSV = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv"

def run_demo(csv_path: str) -> dict:
    result = subprocess.run(
        ["cargo", "run", "--bin", "demo_profit", "--", csv_path],
        cwd=CARGO_DIR, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        return {"error": result.stderr, "stdout": result.stdout}
    
    out = result.stdout
    
    # Parse structured output
    def extract(pattern, default=0):
        m = re.search(pattern, out)
        return float(m.group(1)) if m else default
    
    data = {
        "total_trades": int(extract(r"Total trades.*?: (\d+)")),
        "wins": int(extract(r"Wins/Losses: (\d+)")),
        "losses": int(extract(r"Wins/Losses: \d+/(\d+)")),
        "win_rate": extract(r"Win rate: ([\d.]+)%"),
        "gross_r": extract(r"Gross R-multiple: ([\d.]+)R"),
        "avg_risk_pts": extract(r"\(([\d.]+) pts\)"),
        "avg_risk_dollars": extract(r"Avg risk per trade: \$([\d.]+)"),
        "gross_pnl": extract(r"Gross PnL: \$([\d.]+)"),
        "friction": extract(r"Friction.*?\$([\d.]+)"),
        "net_pnl": extract(r"Net PnL: \$([\d.]+)"),
        "topstep_pass": "PASS" in out,
        "profitable": "PROFITABLE" in out,
    }
    
    # Per-strategy breakdown
    data["per_strategy"] = {}
    for s in ["wq-alpha-009", "wq-alpha-001", "wq-alpha-012"]:
        m = re.search(rf"\{s}: (\d+) trades", out)
        if m:
            data["per_strategy"][s] = int(m.group(1))
    
    return data

if __name__ == "__main__":
    csv = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    print(f"Running Rust WQ Alphas on: {csv}", file=sys.stderr)
    data = run_demo(csv)
    
    if "error" in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        print(json.dumps(data, indent=2))
        sys.exit(1)
    
    # Write structured output
    out_path = Path(OUT_DIR) / "rust-wq-alpha-bridge.json"
    out_path.write_text(json.dumps(data, indent=2))
    print(f"Written to: {out_path}", file=sys.stderr)
    print(json.dumps(data, indent=2))
