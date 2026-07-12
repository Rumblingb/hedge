#!/usr/bin/env python3
"""VWAP Mean-Reversion System — Entry/Exit signals from VWAP deviation"""

__version__ = "1.0.0"

import json, subprocess, sys, os
import numpy as np
from datetime import datetime

def fetch_nq_bars(days=5):
    """Fetch NQ 5m bars"""
    cmd = f"""cd /Users/brain/hedge && source ~/Library/Application\\ Support/AgentPay/bill/bill.env && npx tsx -e "
(async () => {{
  const q = await (await fetch('https://query1.finance.yahoo.com/v8/finance/chart/MNQ=F?interval=5m&range={days}d')).json();
  const r = q.chart?.result?.[0];
  const c = r?.indicators?.quote?.[0]?.close || [];
  const h = r?.indicators?.quote?.[0]?.high || [];
  const l = r?.indicators?.quote?.[0]?.low || [];
  const v = r?.indicators?.quote?.[0]?.volume || [];
  const o = r?.indicators?.quote?.[0]?.open || [];
  const t = r?.timestamp || [];
  process.stdout.write(JSON.stringify({{opens:o, highs:h, lows:l, closes:c, volumes:v, timestamps:t}}));
}})()
" 2>/dev/null"""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return json.loads(r.stdout)

def analyze():
    data = fetch_nq_bars(3)
    closes = np.array(data.get("closes", []), dtype=np.float64)
    highs = np.array(data.get("highs", []), dtype=np.float64)
    lows = np.array(data.get("lows", []), dtype=np.float64)
    volumes = np.array(data.get("volumes", []), dtype=np.float64)
    opens = np.array(data.get("opens", []), dtype=np.float64)
    timestamps = data.get("timestamps", [])
    
    # Filter NaN
    mask = ~(np.isnan(closes) | np.isnan(highs) | np.isnan(lows) | np.isnan(volumes) | np.isnan(opens))
    closes = closes[mask]
    highs = highs[mask]
    lows = lows[mask]
    volumes = volumes[mask]
    opens = opens[mask]

    if len(closes) < 10:
        print("Not enough data"); return
    
    current = closes[-1]
    
    # ==========================================
    # VWAP Calculation (Session VWAP)
    # ==========================================
    # Typical price = (H + L + C) / 3
    typical_prices = (highs + lows + closes) / 3
    pv = typical_prices * volumes
    cum_pv = np.cumsum(pv)
    cum_vol = np.cumsum(volumes)
    vwap = cum_pv / np.maximum(cum_vol, 1)
    
    session_vwap = vwap[-1]
    
    # VWAP standard deviation bands (1σ, 2σ)
    # σ = sqrt(sum(V * (TP - VWAP)^2) / sum(V))
    variance = np.sum(volumes * (typical_prices - session_vwap) ** 2) / max(np.sum(volumes), 1)
    vwap_std = np.sqrt(variance)
    
    # Current deviation
    deviation = (current - session_vwap) / max(vwap_std, 1)
    
    print("=" * 60)
    print("VWAP MEAN-REVERSION SYSTEM")
    print("=" * 60)
    
    print(f"\n  VWAP: {session_vwap:.2f}")
    print(f"  VWAP σ: {vwap_std:.2f}")
    print(f"  Current: {current:.2f}")
    print(f"  Deviation: {deviation:+.2f}σ")
    print(f"  Distance from VWAP: {current - session_vwap:+.2f} pts")
    
    # ==========================================
    # Entry Signals
    # ==========================================
    print("\n--- ENTRY SIGNALS ---")
    
    if deviation > 2.0:
        print(f"  🔴 SHORT: Price is {deviation:.1f}σ above VWAP (extreme)")
        print(f"     Entry: {current:.2f}")
        print(f"     Target: VWAP at {session_vwap:.2f} ({current - session_vwap:+.0f} pts)")
        print(f"     Stop: +1σ above entry at {current + vwap_std:.2f}")
    elif deviation > 1.0:
        print(f"  🟡 SHORT WATCH: Price {deviation:.1f}σ above VWAP")
        print(f"     Wait for 2σ or reversal candlestick pattern")
    elif deviation < -2.0:
        print(f"  🟢 LONG: Price is {abs(deviation):.1f}σ below VWAP (extreme)")
        print(f"     Entry: {current:.2f}")
        print(f"     Target: VWAP at {session_vwap:.2f} ({current - session_vwap:+.0f} pts)")
        print(f"     Stop: -1σ below entry at {current - vwap_std:.2f}")
    elif deviation < -1.0:
        print(f"  🟡 LONG WATCH: Price {abs(deviation):.1f}σ below VWAP")
        print(f"     Wait for 2σ or reversal candlestick pattern")
    else:
        print(f"  ⚪ NO SIGNAL: Price within 1σ of VWAP")
        print(f"     Mean-reversion not actionable in this zone")
    
    # ==========================================
    # Session Type from VWAP Perspective
    # ==========================================
    print("\n--- SESSION TYPE (VWAP Context) ---")
    
    # Recent VWAP path
    last_20_vwap = vwap[-20:] if len(vwap) >= 20 else vwap
    vwap_slope = (last_20_vwap[-1] - last_20_vwap[0]) / len(last_20_vwap)
    
    print(f"  VWAP slope (20 bars): {vwap_slope:+.2f} pts/bar")
    
    if abs(vwap_slope) < 0.5:
        print(f"  Type: RANGE — VWAP flat. Mean-reversion IDEAL")
    elif vwap_slope > 0:
        print(f"  Type: TREND UP — VWAP rising. Mean-reversion less ideal, favor pullbacks to VWAP")
    else:
        print(f"  Type: TREND DOWN — VWAP falling. Mean-reversion less ideal, favor bounces to VWAP")
    
    # ==========================================
    # Previous Day's VWAP for Multi-Day Context
    # ==========================================
    print("\n--- MULTI-DAY VWAP CONTEXT ---")
    data2 = fetch_nq_bars(1)
    closes2 = np.array(data2.get("closes", []), dtype=np.float64)
    highs2 = np.array(data2.get("highs", []), dtype=np.float64)
    lows2 = np.array(data2.get("lows", []), dtype=np.float64)
    volumes2 = np.array(data2.get("volumes", []), dtype=np.float64)
    
    mask2 = ~(np.isnan(closes2) | np.isnan(highs2) | np.isnan(lows2) | np.isnan(volumes2))
    closes2 = closes2[mask2]
    highs2 = highs2[mask2]
    lows2 = lows2[mask2]
    volumes2 = volumes2[mask2]
    
    if len(closes2) > 5:
        tp2 = (highs2 + lows2 + closes2) / 3
        prev_vwap = np.sum(tp2 * volumes2) / max(np.sum(volumes2), 1)
        print(f"  Yesterday VWAP: {prev_vwap:.2f}")
        print(f"  Current vs Prev VWAP: {current - prev_vwap:+.2f} pts")
        
        if current > prev_vwap + vwap_std * 2:
            print(f"  Price far above yesterday's VWAP → bearish lean (profit-taking zone)")
        elif current < prev_vwap - vwap_std * 2:
            print(f"  Price far below yesterday's VWAP → bullish lean (value zone)")
        else:
            print(f"  Price near yesterday's VWAP → neutral, normal range")
    
    # ==========================================
    # Trade Plan
    # ==========================================
    print("\n--- TRADE PLAN ---")
    if abs(deviation) > 1.5:
        direction = "SHORT" if deviation > 0 else "LONG"
        size = "FULL" if abs(deviation) > 2.0 else "HALF"
        print(f"  Direction: {direction}")
        print(f"  Size: {size}")
        print(f"  Entry: Market order at {current:.2f}")
        print(f"  Target 1 (50%): VWAP at {session_vwap:.2f}")
        print(f"  Target 2 (30%): Overshoot target at {session_vwap + (current - session_vwap) * 0.5:.2f}")
        print(f"  Trail (20%): From 50% target, trail 30pts")
        print(f"  SL: {vwap_std:.0f} pts from entry = {current + (-deviation/abs(deviation)) * vwap_std:.2f}")
    else:
        print(f"  No actionable signal. Wait for deviation > 1.5σ")

if __name__ == "__main__":
    analyze()
