#!/usr/bin/env python3
"""System Black-Box Dashboard — one-shot view of everything trading.
Usage: python3 /Users/brain/hedge/scripts/dashboard.py
"""
import json, os, subprocess
from datetime import datetime

def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except: return default or {}

print("=" * 66)
print("  BILL/HEDGE SYSTEM DASHBOARD")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
print("=" * 66)
print()

# Rust pipeline state
guardrail = read_json("/Users/brain/hedge/.rumbling-hedge/state/rust-wq-guardrailed.json")
if guardrail:
    print(f"  Rust Bridge:     {guardrail.get('total_trades', 0)} raw signals")
    print(f"  After Guardrails: {guardrail.get('trades_after_guardrails', 0)}")
    print(f"  Kelly:            {guardrail.get('kelly_fraction', 0)*100:.1f}%")
    print(f"  Filtered:         {'YES' if guardrail.get('guardrail_filtered', True) else 'NO'}")
print()

# PM Whale tracker
whales = read_json("/Users/brain/hedge/.rumbling-hedge/state/pm-whale-signals.json")
if whales:
    print(f"  PM Data:          {whales.get('total_trades_analyzed', 0):,} trades")
    print(f"  Whales:           {whales.get('whale_count', 0):,}")
    print(f"  Large trades:     {whales.get('edge_summary', {}).get('large_trades_count', 0):,}")
print()

# Memory
mem = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True)
disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
print(f"  Swap: {mem.stdout.strip().split()[-1] if mem.stdout else '?'}")
for line in disk.stdout.split('\n'):
    if line.endswith('/'):
        parts = line.split()
        print(f"  Disk: {parts[4]} used ({parts[3]} free)")
print()

# n8n
n8n = subprocess.run(["sqlite3", "/Users/brain/.n8n/database.sqlite", 
    "SELECT count(*) FROM workflow_entity WHERE active=1"], capture_output=True, text=True)
print(f"  n8n workflows:    {n8n.stdout.strip()} active")
print()
print("=" * 66)
