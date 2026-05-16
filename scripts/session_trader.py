#!/usr/bin/env python3
"""Session Phase Trader — What to trade in each session phase + position size from ATR"""

__version__ = "1.0.0"

import json, subprocess, sys, os
import numpy as np
from datetime import datetime, timezone

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
  const t = r?.timestamp || [];
  process.stdout.write(JSON.stringify({{closes:c, highs:h, lows:l, volumes:v, timestamps:t}}));
}})()
" 2>/dev/null"""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return json.loads(r.stdout)

def get_session_phase():
    """Determine current/next session phase"""
    now = datetime.now(timezone.utc)
    et_minutes = now.hour * 60 + now.minute - 4 * 60  # UTC to ET
    
    phases = [
        (570, 600, "📗 OPEN", "09:30-10:00 ET", "OBSERVE. First 5min HL = absorption ref. No trades."),
        (600, 720, "📗 MID-MORNING", "10:00-12:00 ET", "TRADE. ORB breakouts, mean-reversion. Best window."),
        (720, 840, "📕 LUNCH", "12:00-14:00 ET", "SIZE DOWN or SKIP. Thin DOM, low conviction."),
        (840, 960, "📗 POWER HOUR", "14:00-16:00 ET", "ACTIVE. Institutional rebalancing. Watch close-auction."),
    ]
    
    if et_minutes < 570:
        return ("⏳ PRE-MARKET", f"{max(0, 570 - et_minutes)} min to open", 
                "Prepare. Run FFT + TimesFM + cross-asset engine.")
    elif et_minutes >= 960:
        return ("🌙 CLOSED", "Session over",
                "Post-market. Log trades, update edge tracker.")
    
    for start, end, name, time_str, desc in phases:
        if start <= et_minutes < end:
            remaining = end - et_minutes
            return (name, f"{time_str} ({remaining} min remaining)", desc)
    
    return ("⏰ UNKNOWN", f"ET minutes: {et_minutes}", "")

def run():
    # Fetch data
    data = fetch_nq_bars(5)
    closes = np.array(data.get("closes", []), dtype=np.float64)
    highs = np.array(data.get("highs", []), dtype=np.float64)
    lows = np.array(data.get("lows", []), dtype=np.float64)
    volumes = np.array(data.get("volumes", []), dtype=np.float64)
    
    if len(closes) < 14 or np.isnan(closes[-1]):
        print("No recent NQ data — using last known values")
        current = 29231.75  # Last known NQ close
        atr14 = 11.23
        atr20 = 12.95
    else:
        current = closes[-1]
    
    # ATR(14)
    tr_values = []
    for i in range(1, min(15, len(closes))):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr_values.append(max(hl, hc, lc))
    atr14 = np.mean(tr_values)
    
    # ATR(20) on 5m data
    tr_values_20 = []
    for i in range(1, min(21, len(closes))):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr_values_20.append(max(hl, hc, lc))
    atr20 = np.mean(tr_values_20)
    
    # Returns for vol calc
    returns = np.diff(np.log(closes))
    recent_vol = np.std(returns[-20:]) if len(returns) >= 20 else np.std(returns)
    overall_vol = np.std(returns)
    vol_regime = "HIGH" if recent_vol > overall_vol * 1.3 else ("LOW" if recent_vol < overall_vol * 0.7 else "NORMAL")
    
    # ==========================================
    # POSITION SIZING TABLE
    # ==========================================
    print("=" * 65)
    print("  SESSION PHASE TRADER + ATR POSITION SIZING")
    print("=" * 65)
    
    # Session phase
    phase, time_info, phase_desc = get_session_phase()
    print(f"\n  Session: {phase}")
    print(f"  Time: {time_info}")
    print(f"  Guide: {phase_desc}")
    
    print(f"\n  NQ: {current:.2f} | ATR(14) 5m: {atr14:.2f} | ATR(20) 5m: {atr20:.2f}")
    print(f"  Vol regime: {vol_regime} (recent std {recent_vol:.4f} vs overall {overall_vol:.4f})")
    
    # ==========================================
    # Position Size Calculator (for prop firms)
    # ==========================================
    print("\n--- POSITION SIZE (per account) ---")
    
    accounts = [
        ("LucidFlex $50K 1", 50000, 450, 2000),
        ("LucidFlex $50K 2", 50000, 450, 2000),
        ("FundedNext $100K", 100000, 750, 2500),
        ("Topstep $100K", 100000, 900, 3000),
    ]
    
    # Adjust ATR for timeframe
    # 5m ATR * sqrt(12) ≈ 1h ATR, * sqrt(3) ≈ 15m ATR
    atr_15m = atr20 * np.sqrt(3)  # ~5m bars to 15m
    atr_1h = atr20 * np.sqrt(12)  # ~5m bars to 1h
    
    print(f"  ATR(15m): {atr_15m:.1f}")
    print(f"  ATR(1h): {atr_1h:.1f}")
    
    for name, size, daily_loss, max_dd in accounts:
        # Risk per trade: 1% of account = $500 for $50K, $1000 for $100K
        # But constrained by daily loss limit
        risk_pct = min(0.01, daily_loss / size * 0.5)  # Max 1% or half daily limit
        risk_dollars = size * risk_pct
        
        # SL in points (use ATR-based)
        if vol_regime == "HIGH":
            sl_points = atr_15m * 1.5  # Tighter in high vol
        elif vol_regime == "LOW":
            sl_points = atr_15m * 2.0  # Wider in low vol (less noise stops)
        else:
            sl_points = atr_15m * 1.8  # Normal
        
        # MNQ contract value: $2 per point
        contracts = max(1, int(risk_dollars / (sl_points * 2)))
        
        print(f"\n  {name}:")
        print(f"    Risk/trade: ${risk_dollars:.0f} ({risk_pct*100:.1f}%)")
        print(f"    SL: {sl_points:.0f} pts")
        print(f"    Contracts: {contracts} MNQ")
        print(f"    Target 1: +{sl_points * 1.5:.0f} pts (${sl_points * 1.5 * 2 * contracts:.0f})")
        print(f"    Target 2: +{sl_points * 3:.0f} pts (${sl_points * 3 * 2 * contracts:.0f})")
    
    # ==========================================
    # Trade Filter (should we even trade today?)
    # ==========================================
    print("\n--- TRADE FILTER ---")
    
    # Volume check
    avg_vol = np.nanmean(volumes) if np.nanmean(volumes) > 0 else 1
    last_vol = np.nanmean(volumes[-5:]) if len(volumes) >= 5 else avg_vol
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1
    
    print(f"  Volume ratio (last 5 bars / avg): {vol_ratio:.2f}")
    
    filters_passed = 0
    filters_total = 3
    
    if 570 <= datetime.now(timezone.utc).hour * 60 + datetime.now(timezone.utc).minute - 4 * 60 < 960:
        print(f"  ✅ In session hours")
        filters_passed += 1
    else:
        print(f"  ❌ Outside session hours — no trades")
    
    if vol_ratio > 0.5:
        print(f"  ✅ Volume adequate")
        filters_passed += 1
    else:
        print(f"  ⚠️  Low volume — reduce size")
    
    if vol_regime != "HIGH":
        print(f"  ✅ Volatility stable ({vol_regime})")
        filters_passed += 1
    else:
        print(f"  ⚠️  High volatility regime — reduce size 50%")
    
    print(f"\n  Trade filter: {filters_passed}/{filters_total} passed")
    if filters_passed < 2:
        print(f"  ❌ NO TRADE — insufficient conditions")
    elif filters_passed < 3:
        print(f"  ⚠️  REDUCED TRADE — half size")
    else:
        print(f"  ✅ FULL TRADE — all conditions met")

if __name__ == "__main__":
    run()
