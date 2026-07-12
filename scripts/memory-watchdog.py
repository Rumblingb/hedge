#!/usr/bin/env python3
"""Memory watchdog — kills non-critical processes when swap > 80%.
Runs from launchd every 5 minutes. Protects the trading pipeline from OOM.
"""
import subprocess, json, os, sys
from pathlib import Path

SWAP_THRESHOLD = 80  # percent
CRITICAL_PROCS = [
    "com.agentpay.bill.gengar-monitor",
    "com.agentpay.bill.prediction-cycle",
    "com.agentpay.bill.research-collect",
    "com.agentpay.bill.health",
    "com.agentpay.bill.paper-loop",
    "ai.hermes.gateway",
    "com.agentpay.bill.rust-wq-pipeline",
    "com.agentpay.bill.macro-context-free",
]
NON_CRITICAL_PROCS = [
    "com.agentpay.postiz-backend",
    "com.agentpay.postiz-frontend",
    "com.agentpay.content-generator",
    "com.agentpay.founder-attention",
    "com.agentpay.full-brain-dashboard",
    "com.agentpay.full-brain-orchestrator",
    "com.agentpay.brain-sync",
    "com.agentpay.kronos.sidecar",
    "homebrew.mxcl.ollama",
    "com.agentpay.agentpay-labs-bridge",
]
LOG_FILE = "/Users/brain/hedge/.rumbling-hedge/logs/memory-watchdog.log"

def log(msg: str):
    with open(LOG_FILE, "a") as f:
        f.write(f"{msg}\n")
    print(msg)

def get_swap_pct() -> float:
    result = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True)
    m = __import__('re').search(r"used = ([\d.]+)([MG])", result.stdout)
    if not m:
        return 0.0
    used = float(m.group(1))
    unit = m.group(2)
    if unit == 'G':
        used *= 1024
    # total is 8192 MB (8GB)
    total = 8192.0
    return (used / total) * 100

def kill_process(name: str):
    """Unload launchd plist for a service."""
    subprocess.run(["launchctl", "unload", f"/Users/brain/Library/LaunchAgents/{name}.plist"],
                   capture_output=True)
    log(f"KILLED: {name}")

def main():
    swap_pct = get_swap_pct()
    log(f"Swap: {swap_pct:.1f}% (threshold: {SWAP_THRESHOLD}%)")
    
    # Check which critical processes are alive
    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    running = result.stdout
    
    if swap_pct > SWAP_THRESHOLD:
        log(f"SWAP CRITICAL: {swap_pct:.1f}% > {SWAP_THRESHOLD}% — killing non-critical processes")
        killed = []
        for proc in NON_CRITICAL_PROCS:
            if proc in running:
                kill_process(proc)
                killed.append(proc)
        
        if killed:
            log(f"Killed {len(killed)} non-critical processes: {', '.join(killed)}")
        else:
            log("No non-critical processes running to kill")
    else:
        log(f"Swap OK ({swap_pct:.1f}%)")

if __name__ == "__main__":
    main()
