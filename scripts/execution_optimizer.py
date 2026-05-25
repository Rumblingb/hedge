#!/usr/bin/env python3
"""GOLD #8: Execution Optimization Layer.

Calculates optimal order slicing using VWAP-based schedule
with volatility-adjusted participation rate.
Output: {ts, slices, total_est_slippage, recommended_algo}
"""
import json, math, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(os.path.expanduser("~/.rumbling-hedge"))
STATE_DIR = ROOT / "state"

def compute_vwap_schedule(contracts: int, volatility: float = 0.15, participation: float = 0.1):
    """Compute VWAP order slicing schedule.
    
    Args:
        contracts: Total contracts to execute
        volatility: Estimated volatility (NSR/100 proxy)
        participation: Target participation rate (fraction of volume)
    Returns:
        list of {minute, qty, price_est}
    """
    if contracts <= 1:
        return [{"minute": 0, "qty": contracts, "price_est": "market"}]
    
    # Spread execution over minutes proportional to volatility
    duration_min = max(5, min(60, int(volatility * 200)))
    
    # Volume profile: front-loaded (more volume early)
    slices = []
    remaining = contracts
    for m in range(duration_min):
        if remaining <= 0:
            break
        # Front-loaded volume distribution
        if m < duration_min * 0.2:
            chunk = max(1, int(remaining * 0.3))
        elif m < duration_min * 0.5:
            chunk = max(1, int(remaining * 0.3))
        else:
            chunk = max(1, int(remaining / max(1, duration_min - m)))
        chunk = min(chunk, remaining)
        slices.append({"minute": m, "qty": chunk, "price_est": "estimated"})
        remaining -= chunk
    
    return slices

def compute_estimated_slippage(contracts: int, volatility: float) -> float:
    """Estimate slippage in R units."""
    base = 0.05  # 0.05R base slippage for 1 contract
    return base * math.sqrt(contracts) * (1 + volatility * 2)

def main():
    ts = datetime.now(timezone.utc).isoformat()
    
    # Read current position to estimate execution needs
    pos_file = STATE_DIR / "current-position.json"
    contracts = 1
    volatility = 0.15
    if pos_file.exists():
        try:
            data = json.loads(pos_file.read_text())
            contracts = data.get("quantity", 1)
        except Exception:
            pass
    
    # Read noise analysis for volatility
    na_file = STATE_DIR / "noise-analysis.latest.json"
    if na_file.exists():
        try:
            na = json.loads(na_file.read_text())
            nsr = na.get("nq_nsr", na.get("nsr", 15))
            volatility = min(0.5, max(0.05, nsr / 100))
        except Exception:
            pass
    
    slices = compute_vwap_schedule(contracts, volatility)
    slippage = compute_estimated_slippage(contracts, volatility)
    
    output = {
        "ts": ts,
        "contracts": contracts,
        "volatility_est": round(volatility, 3),
        "duration_min": len(slices),
        "num_slices": len(slices),
        "slices": slices[:10],  # Preview first 10
        "total_est_slippage_r": round(slippage, 3),
        "recommended_algo": "VWAP" if contracts > 1 else "MARKET",
        "participation_rate": 0.1,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / "execution-optimizer.latest.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Execution Optimizer: {len(slices)} slices, est slippage {slippage:.3f}R")

if __name__ == "__main__":
    main()