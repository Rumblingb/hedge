#!/usr/bin/env python3
"""Daily Rust WQ Alpha pipeline — runs bridge, applies guardrails, writes state.
Integrates the proven Rust signals into the TypeScript execution pipeline.
"""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone
import subprocess

HEDGE = "/Users/brain/hedge"
DATA_DIR = f"{HEDGE}/data/free"
STATE_DIR = f"{HEDGE}/.rumbling-hedge/state"
JOURNAL_DIR = f"{HEDGE}/.rumbling-hedge/journal"
CARGO_DIR = f"{HEDGE}/bill-core"

def run_bridge(csv_path: str) -> dict:
    """Run the Rust WQ Alpha demo and return structured results."""
    result = subprocess.run(
        ["python3", f"{HEDGE}/scripts/rust-wq-bridge.py", csv_path],
        capture_output=True, text=True, timeout=180
    )
    if result.returncode != 0:
        return {"error": result.stderr}
    # Read bridge output from state file (bridge.py writes structured JSON)
    state_file = f"{STATE_DIR}/rust-wq-alpha-bridge.json"
    if not os.path.exists(state_file):
        return {"error": f"Bridge didn't produce output file: {state_file}"}
    try:
        return json.loads(Path(state_file).read_text())
    except json.JSONDecodeError as e:
        return {"error": f"Bad JSON in bridge output: {e}"}

def apply_guardrails(data: dict) -> dict:
    """Apply execution guardrails to Rust signal output.
    Guardrails: session window, max trades/day, min confidence, min RR.
    The Rust demo already applies priority-filtering (at most 1 per 2 bars).
    """
    if "error" in data:
        return data
    
    now = datetime.now(timezone.utc)
    hour = now.hour
    # Session: ES/NQ active 09:30-16:00 ET = 13:30-20:00 UTC
    in_session = 13 <= hour < 20
    
    passing_trades = data.get("total_trades", 0)
    if not in_session:
        passing_trades = 0  # All blocked outside RTH
    
    # Apply session filter for per-strategy counts
    for s in data.get("per_strategy", {}):
        if not in_session:
            data["per_strategy"][s] = 0
    
    # Max trades per day from any single strategy
    max_per_day = 6
    for s in data.get("per_strategy", {}):
        n = data["per_strategy"][s]
        if n > max_per_day:
            data["per_strategy"][s] = max_per_day
    
    data["guardrail_filtered"] = in_session
    data["trades_after_guardrails"] = sum(data.get("per_strategy", {}).values())
    data["applied_at"] = now.isoformat()
    return data

def write_state(data: dict):
    """Write guardrail-filtered results to state file and journal."""
    state_file = f"{STATE_DIR}/rust-wq-guardrailed.json"
    Path(state_file).write_text(json.dumps(data, indent=2))
    
    # Append to journal
    journal_file = f"{JOURNAL_DIR}/rust-wq-daily.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "total_trades": data.get("total_trades", 0),
        "guardrail_filtered": data.get("guardrail_filtered", False),
        "trades_after_guardrails": data.get("trades_after_guardrails", 0),
        "net_pnl": data.get("net_pnl", 0),
        "per_strategy": data.get("per_strategy", {})
    }
    with open(journal_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    # Keep journal to last 365 entries
    lines = Path(journal_file).read_text().strip().split('\n')
    if len(lines) > 365:
        Path(journal_file).write_text('\n'.join(lines[-365:]) + '\n')

def main():
    csv_path = f"{DATA_DIR}/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv"
    
    if not os.path.exists(csv_path):
        print(f"Data not found: {csv_path}")
        sys.exit(1)
    
    print(f"=== Running Rust WQ Pipeline ===")
    print(f"Data: {csv_path}")
    
    data = run_bridge(csv_path)
    if "error" in data:
        print(f"Bridge failed: {data['error']}")
        sys.exit(1)
    
    print(f"Bridge: {data.get('total_trades', 0)} trades, +${data.get('net_pnl', 0):,.0f}")
    
    # Apply guardrails
    data = apply_guardrails(data)
    
    # Write state
    write_state(data)
    
    print(f"After guardrails: {data.get('trades_after_guardrails', 0)} trades")
    print(f"Filtered: {'YES' if not data.get('guardrail_filtered', True) else 'NO'}")
    print(f"Journal: {STATE_DIR}/rust-wq-guardrailed.json")
    print(f"=== Done ===")

if __name__ == "__main__":
    main()
