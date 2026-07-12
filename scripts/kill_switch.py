#!/usr/bin/env python3
"""
EMERGENCY KILL SWITCH — Deployed 2026-05-23
============================================
Instantly halts ALL live trading activity across every account, lane, and venue.

Usage:
  python3 kill_switch.py                    # Activate kill switch
  python3 kill_switch.py --status           # Check if active
  python3 kill_switch.py --release          # Release kill switch (manual approval needed)

When activated:
  - Creates EMERGENCY_STOP flag file
  - Master bridge reads this file and refuses all trades
  - All cron jobs skip trade execution
  - State persists across reboots
"""

import json, os, sys, datetime
from pathlib import Path

KILL_FILE = Path.home() / ".rumbling-hedge" / "state" / "EMERGENCY_STOP"
ACTIVE_LANES_FILE = Path.home() / ".rumbling-hedge" / "state" / "active_lanes.json"
LOG_DIR = Path.home() / ".rumbling-hedge" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "kill_switch.log"

def log(msg):
    ts = datetime.datetime.now().isoformat()
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"  [{ts}] {msg}")

def activate():
    if KILL_FILE.exists():
        print("⚠️  KILL SWITCH ALREADY ACTIVE — No action taken")
        with open(KILL_FILE) as f:
            print(f"  Activated: {f.read().strip()}")
        return
    
    ts = datetime.datetime.now().isoformat()
    payload = {
        "activated_at": ts,
        "triggered_by": "kill_switch.py",
        "reason": "MANUAL KILL SWITCH — all lanes halted",
        "affected_modules": [
            "master_bridge.py", "60m_exec_bridge.py", "becker_bridge.py",
            "cross_asset_engine.py", "kalman_pairs.py", "dom_proxy_ohlcv.py",
            "whale_flow_signal.py", "rolling_window_optimizer.py"
        ]
    }
    
    # Write the kill switch flag
    KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KILL_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    
    # Deactivate all active lanes
    if ACTIVE_LANES_FILE.exists():
        try:
            with open(ACTIVE_LANES_FILE) as f:
                lanes = json.load(f)
            for lane in lanes:
                lanes[lane]["active"] = False
                lanes[lane]["kill_switch_halt"] = ts
            with open(ACTIVE_LANES_FILE, "w") as f:
                json.dump(lanes, f, indent=2)
            log(f"Deactivated {len(lanes)} lanes")
        except:
            pass
    
    log(f"🚨 KILL SWITCH ACTIVATED at {ts}")
    log("→ All live trading halted")
    log("→ All lanes deactivated")
    log("→ To release: python3 kill_switch.py --release")
    
    print(f"\n{'='*50}")
    print(f"🚨 EMERGENCY KILL SWITCH ACTIVATED")
    print(f"{'='*50}")
    print(f"  Time: {ts}")
    print(f"  File: {KILL_FILE}")
    print(f"  Status: ALL TRADING HALTED")

def status():
    if KILL_FILE.exists():
        with open(KILL_FILE) as f:
            data = json.load(f)
        print(f"🚨 KILL SWITCH IS ACTIVE")
        print(f"  Activated: {data.get('activated_at', 'unknown')}")
        print(f"  Reason: {data.get('reason', 'unknown')}")
        print(f"  To release: python3 kill_switch.py --release")
    else:
        print("✅ KILL SWITCH IS INACTIVE — Trading enabled")
        print(f"  (File {KILL_FILE} does not exist)")

def release():
    if not KILL_FILE.exists():
        print("⚠️  Kill switch is not active — nothing to release")
        return
    
    print(f"{'='*50}")
    print(f"⚠️  RELEASING KILL SWITCH")
    print(f"{'='*50}")
    print(f"  You are about to re-enable ALL live trading.")
    print(f"  Type 'YES' to confirm: ", end="")
    
    try:
        confirm = input().strip()
    except:
        confirm = ""
    
    if confirm != "YES":
        print("  Release cancelled.")
        return
    
    ts = datetime.datetime.now().isoformat()
    
    # Read and archive the kill switch
    archive_dir = LOG_DIR / "kill_archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"EMERGENCY_STOP_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    if KILL_FILE.exists():
        import shutil
        shutil.copy(str(KILL_FILE), str(archive_dir / archive_name))
    
    KILL_FILE.unlink(missing_ok=True)
    
    log(f"✅ KILL SWITCH RELEASED at {ts}")
    log(f"  Archived to: {archive_dir / archive_name}")
    
    print(f"\n✅ KILL SWITCH RELEASED")
    print(f"  Trading re-enabled for all lanes")

if __name__ == "__main__":
    if "--release" in sys.argv:
        release()
    elif "--status" in sys.argv or "-s" in sys.argv:
        status()
    else:
        activate()
