#!/usr/bin/env python3
"""DOM Micro-Structure Edges — Iceberg Detection, Cumulative Delta, Order Flow from 5m bars"""

__version__ = "1.0.0"

import json, subprocess, sys, os
import numpy as np
from datetime import datetime

def fetch_nq_bars(interval="5m", days=5):
    """Fetch NQ bars from Yahoo"""
    cmd = f"""cd /Users/brain/hedge && source ~/Library/Application\\ Support/AgentPay/bill/bill.env && npx tsx -e "
(async () => {{
  const q = await (await fetch('https://query1.finance.yahoo.com/v8/finance/chart/MNQ=F?interval={interval}&range={days}d')).json();
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

def running_sum(arr, window):
    """Rolling sum with edge handling"""
    result = np.full_like(arr, np.nan)
    for i in range(len(arr)):
        start = max(0, i - window + 1)
        result[i] = np.nansum(arr[start:i+1])
    return result

def analyze():
    data = fetch_nq_bars("5m", 5)
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
    timestamps = [t for i, t in enumerate(timestamps) if i < len(mask) and mask[i]]

    if len(closes) < 20:
        print("Not enough data"); return

    current = closes[-1]

    print("=" * 60)
    print("DOM MICRO-STRUCTURE EDGES")
    print("=" * 60)

    # ==========================================
    # 1. ICEBERG DETECTION RATIO (from DOM framework)
    # ==========================================
    print("\n--- ICEBERG DETECTION RATIO ---")
    # We don't have live DOM, so we approximate: 
    # Look for levels where volume traded >> expected for that price level
    # Key levels: round numbers (29000, 29100, etc), prior day HL
    
    # IDR proxy: volume at key levels as ratio of average bar volume
    avg_bar_vol = np.nanmean(volumes) if np.nanmean(volumes) > 0 else 1
    key_levels = [round(closes[-1] / 1000) * 1000, round(closes[-1] / 100) * 100,
                  round(closes[-1] / 50) * 50]
    
    print(f"Average bar volume: {avg_bar_vol:.0f}")
    print(f"Current: {current:.2f}")
    print(f"Key levels to watch: {', '.join(f'{x:.0f}' for x in key_levels)}")
    
    # Volume surge detection: bars where volume > 2x avg
    vol_surges = np.where(volumes > avg_bar_vol * 2.0)[0]
    iceberg_count = 0
    for idx in vol_surges[-5:]:  # Last 5 surges
        bar_vol = volumes[idx]
        bar_price = closes[idx]
        surge_ratio = bar_vol / avg_bar_vol
        # Check if adjacent bars also had high volume (iceberg signature)
        adj_vol = np.mean([volumes[max(0,idx-1)], volumes[min(len(volumes)-1, idx+1)]]) if idx > 0 and idx < len(volumes)-1 else 0
        multi_bar_surge = adj_vol / avg_bar_vol if adj_vol > 0 else 0
        
        if surge_ratio > 3.0 and multi_bar_surge > 1.5:
            iceberg_count += 1
            print(f"  ⚡ Bar {idx}: ICEBERG signal (vol {surge_ratio:.1f}x avg at {bar_price:.0f}, nearby {multi_bar_surge:.1f}x)")
        elif surge_ratio > 2.0:
            print(f"  📊 Bar {idx}: Volume surge (vol {surge_ratio:.1f}x avg at {bar_price:.0f})")
    
    print(f"\n  Active iceberg signals: {iceberg_count}")
    print(f"  Rule: >3x avg vol with >1.5x adjacent = iceberg footprint")

    # ==========================================
    # 2. CUMULATIVE DELTA SIMULATION
    # ==========================================
    print("\n--- CUMULATIVE DELTA (OHLC Proxy) ---")
    # Without tick data, approximate delta from OHLC:
    # Bullish bar = close > open → more buying pressure
    # Bearish bar = close < open → more selling pressure
    # Delta proxy = volume * (close - open) / (high - low) * 2
    
    deltas = np.zeros(len(closes))
    for i in range(len(closes)):
        rng = highs[i] - lows[i]
        if rng > 0:
            # Normalized within-bar delta: +1 = full bullish, -1 = full bearish
            direction = (closes[i] - opens[i]) / rng
            deltas[i] = direction * volumes[i] / avg_bar_vol  # Normalized by avg vol
    
    cum_delta = np.cumsum(deltas)
    cd_10 = cum_delta[-1] - cum_delta[-11] if len(cum_delta) >= 10 else cum_delta[-1]
    
    # Divergence detection
    last_30_close = closes[-30:] if len(closes) >= 30 else closes
    last_30_cd = cum_delta[-30:] if len(cum_delta) >= 30 else cum_delta
    
    if len(last_30_close) >= 5:
        price_trend = last_30_close[-1] - last_30_close[-5]
        cd_trend = last_30_cd[-1] - last_30_cd[-5] if len(last_30_cd) >= 5 else 0
        
        print(f"  Last 5 bars price: {price_trend:+.1f}")
        print(f"  Last 5 bars CD: {cd_trend:+.2f}")
        
        if price_trend > 0 and cd_trend < 0:
            print(f"  ⚠️  DIVERGENCE: Price UP, Delta DOWN → Buying exhaustion → SHORT SETUP")
        elif price_trend < 0 and cd_trend > 0:
            print(f"  ⚠️  DIVERGENCE: Price DOWN, Delta UP → Selling exhaustion → LONG SETUP")
        else:
            print(f"  ✅ Convergent: Price and Delta align → trend continuation")
    
    print(f"  Cumulative Delta (10-bar): {cd_10:+.2f}")

    # ==========================================  
    # 3. ORDER FLOW APPROXIMATION
    # ==========================================
    print("\n--- ORDER FLOW IMBALANCE (OFI Proxy) ---")
    # Proxy for OFI from bar data:
    # Upper wick = sellers overwhelmed buyers (size above close)
    # Lower wick = buyers overwhelmed sellers
    # Bullish bars with small upper wicks = aggressive buying
    
    ofi_values = []
    for i in range(len(closes)):
        rng = highs[i] - lows[i]
        if rng > 0:
            upper_wick = (highs[i] - closes[i]) / rng if closes[i] < highs[i] else 0
            lower_wick = (opens[i] - lows[i]) / rng if opens[i] > lows[i] else 0
            body = abs(closes[i] - opens[i]) / rng if rng > 0 else 0
            # OFI proxy: long bodies with small opposite wicks = directional conviction
            conviction = body - max(upper_wick, lower_wick) if body > 0 else 0
            is_bullish = closes[i] > opens[i]
            ofi = conviction if is_bullish else -conviction
            ofi_values.append(ofi)
    
    ofi_10 = np.mean(ofi_values[-10:]) if len(ofi_values) >= 10 else 0
    ofi_3 = np.mean(ofi_values[-3:]) if len(ofi_values) >= 3 else 0
    
    print(f"  OFI(30s proxy, last 10 bars): {ofi_10:+.4f}")
    print(f"  OFI(30s proxy, last 3 bars): {ofi_3:+.4f}")
    if ofi_3 > 0.2:
        print(f"  Signal: OFI > 0.2 → Buying pressure → LONG bias")
    elif ofi_3 < -0.2:
        print(f"  Signal: OFI < -0.2 → Selling pressure → SHORT bias")
    else:
        print(f"  Signal: OFI near 0 → No clear flow, stand aside")

    # ==========================================
    # 4. COMPOSITE DOM SCORE
    # ==========================================
    print("\n--- COMPOSITE DOM SIGNAL ---")
    # Combine iceberg, delta, and OFI into unified signal
    dom_signals = []
    if iceberg_count > 1:
        dom_signals.append("ICEBERG DETECTED")
    if cd_10 > 2:
        dom_signals.append("DELTA BULLISH")
    elif cd_10 < -2:
        dom_signals.append("DELTA BEARISH")
    if ofi_3 > 0.15:
        dom_signals.append("OFI LONG")
    elif ofi_3 < -0.15:
        dom_signals.append("OFI SHORT")
    
    print(f"  Active signals: {', '.join(dom_signals) if dom_signals else 'None — stand aside'}")
    output = {"timestamp": datetime.utcnow().isoformat(), "signals": dom_signals, "ofi_3": float(ofi_3), "cd_10": float(cd_10), "iceberg_count": iceberg_count}
    json_path = os.path.expanduser("~/.rumbling-hedge/state/dom_micro_edges.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(output, f, default=str)
    print(f"\nJSON output written to {json_path}")
    
    print(f"\n  Trade rule:")
    print(f"  ALL 3 agree → Full size")
    print(f"  2 of 3 agree → Half size")
    print(f"  1 or 0 → No trade")
    print(f"  Current: {len(dom_signals)} signals {'→ HALF SIZE' if len(dom_signals) >= 2 else '→ STAND ASIDE' if len(dom_signals) < 2 else ''}")

if __name__ == "__main__":
    analyze()
