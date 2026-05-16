#!/usr/bin/env python3
"""
UNIFIED PRE-TRADE CHECKER — Institutional Quality
Merges ALL edge signals into ONE deterministic go/no-go decision.
Outputs JSON that signalRouter can consume directly.

Run: python3 scripts/pre_trade_check.py
"""

__version__ = "2.0.0"

import json, subprocess, sys, os
import numpy as np
from datetime import datetime, timezone
from typing import TypedDict, Optional

class TradeDecision(TypedDict, total=False):
    timestamp: str
    decision: str  # "TRADE" | "NO_TRADE" | "REDUCED"
    regime: str
    direction: str  # "LONG" | "SHORT" | "FLAT"
    composite_score: float
    conviction: str  # "HIGH" | "MEDIUM" | "LOW"
    max_contracts: int
    suggested_contracts: int
    atr: float
    stop_loss_pts: float
    target1_pts: float
    target2_pts: float
    trail_pts: float
    safety_checks: dict
    warnings: list[str]

def fetch_nq_data() -> dict:
    """Fetch NQ 5m bars with error handling"""
    cmd = f"""cd /Users/brain/hedge && source ~/Library/Application\\ Support/AgentPay/bill/bill.env && npx tsx -e "
(async () => {{
  try {{
    const q = await (await fetch('https://query1.finance.yahoo.com/v8/finance/chart/MNQ=F?interval=5m&range=5d')).json();
    const r = q.chart?.result?.[0];
    process.stdout.write(JSON.stringify({{
      opens: r?.indicators?.quote?.[0]?.open || [],
      highs: r?.indicators?.quote?.[0]?.high || [],
      lows: r?.indicators?.quote?.[0]?.low || [],
      closes: r?.indicators?.quote?.[0]?.close || [],
      volumes: r?.indicators?.quote?.[0]?.volume || [],
      timestamps: r?.timestamp || []
    }}));
  }} catch(e) {{
    process.stdout.write(JSON.stringify({{error: e.message}}));
  }}
}})()
" 2>/dev/null"""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return {"error": "parse_failed"}


def check_data_freshness(timestamps: list) -> tuple[bool, str]:
    """Check if data is fresh enough to trade. Returns (pass, message)."""
    if not timestamps or len(timestamps) == 0:
        return False, "NO DATA — cannot trade"
    
    last_ts = timestamps[-1]
    if isinstance(last_ts, int) and last_ts > 1000000000:
        last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        age_minutes = (now - last_dt).total_seconds() / 60
        
        if age_minutes > 30:
            return False, f"Data {age_minutes:.0f} min stale — MAX 30 min allowed"
        elif age_minutes > 15:
            return True, f"WARNING: Data {age_minutes:.0f} min stale — verify with MCP scanner"
        else:
            return True, f"Data {age_minutes:.0f} min fresh — OK"
    
    return True, "Data age unknown — proceed with caution"


def compute_fft_regime(closes: list) -> tuple[str, float]:
    """FFT regime detection"""
    arr = np.array(closes, dtype=np.float64)
    log_returns = np.diff(np.log(arr))
    n = len(log_returns)
    if n < 20:
        return "UNKNOWN", 0.5
    
    from scipy import fft
    freq = fft.rfft(log_returns - np.mean(log_returns))
    power = np.abs(freq) ** 2
    trend_band = int(n * 0.05)
    medium_band = int(n * 0.15)
    
    trend_energy = float(np.sum(power[:trend_band])) if trend_band > 0 else 0
    mid_energy = float(np.sum(power[trend_band:medium_band])) if medium_band > trend_band else 0
    noise_energy = float(np.sum(power[medium_band:])) if medium_band < len(power) else 0
    total = trend_energy + mid_energy + noise_energy
    ratio = trend_energy / total if total > 0 else 0.5
    
    regime = "RANGE" if ratio < 0.3 else ("TRENDING" if ratio > 0.6 else "MIXED")
    return regime, ratio


def compute_composite_score(closes: list, highs: list, lows: list, volumes: list) -> dict:
    """Compute 7-factor composite edge score"""
    current = closes[-1]
    n = len(closes)
    
    scores = {}
    bearish = 0
    bullish = 0
    
    # 1. FFT Regime & Oscillator
    arr = np.array(closes, dtype=np.float64)
    log_returns = np.diff(np.log(arr))
    n_r = len(log_returns)
    from scipy import fft
    freq = fft.rfft(log_returns - np.mean(log_returns))
    power = np.abs(freq)
    
    # Oscillator
    if len(power) > 1:
        dom_idx = int(np.argmax(power[1:])) + 1
        dom_phase = np.angle(freq[dom_idx])
        osc = float(np.sin(dom_phase))
    else:
        osc = 0.0
    
    scores["fft_osc"] = osc
    if osc < -0.5:
        scores["fft_verdict"] = "bearish"
        bearish += 1
    elif osc > 0.5:
        scores["fft_verdict"] = "bullish"
        bullish += 1
    else:
        scores["fft_verdict"] = "neutral"
    
    # 2. Price vs VWAP
    typical = (np.array(highs) + np.array(lows) + np.array(closes)) / 3
    cum_pv = np.cumsum(typical * np.array(volumes))
    cum_v = np.cumsum(np.array(volumes))
    vwap = cum_pv / np.maximum(cum_v, 1)
    current_vwap = float(vwap[-1])
    
    if current < current_vwap:
        scores["vwap_verdict"] = "bearish"
        bearish += 1
    else:
        scores["vwap_verdict"] = "bullish"
        bullish += 1
    
    scores["vwap_deviation"] = round((current - current_vwap), 1)
    
    # 3. Volume profile — recent surge?
    avg_vol = float(np.nanmean(volumes)) if len(volumes) > 0 else 1
    recent_vol = float(np.nanmean(volumes[-5:])) if len(volumes) >= 5 else avg_vol
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
    
    if vol_ratio > 1.5:
        # High volume = conviction. Check direction.
        scores["volume_verdict"] = "high_conviction"
        # Last bar direction
        if closes[-1] > (closes[-2] if len(closes) > 1 else closes[-1]):
            bullish += 1
        else:
            bearish += 1
    elif vol_ratio < 0.5:
        scores["volume_verdict"] = "low_volume"
        bearish += 1  # Thin market = unreliable
    else:
        scores["volume_verdict"] = "normal"
    
    # 4. Momentum (1h = 12 bars on 5m)
    if n >= 13:
        mom_1h = (closes[-1] - closes[-13]) / closes[-13] * 100
    else:
        mom_1h = 0
    
    scores["momentum_1h_pct"] = round(mom_1h, 4)
    if mom_1h > 0.1:
        bullish += 1
        scores["momentum_verdict"] = "bullish"
    elif mom_1h < -0.1:
        bearish += 1
        scores["momentum_verdict"] = "bearish"
    else:
        scores["momentum_verdict"] = "neutral"
    
    # 5. OFI proxy (last 5 bars)
    ofi_vals = []
    for i in range(max(0, n - 5), n):
        rng = highs[i] - lows[i]
        if rng > 0:
            body = abs(closes[i] - opens[i]) / rng
            upper = (highs[i] - max(closes[i], opens[i])) / rng if highs[i] > max(closes[i], opens[i]) else 0
            lower = (min(closes[i], opens[i]) - lows[i]) / rng if min(closes[i], opens[i]) > lows[i] else 0
            conv = body - max(upper, lower)
            is_bull = closes[i] > opens[i]
            ofi_vals.append(conv if is_bull else -conv)
    
    ofi_avg = float(np.mean(ofi_vals)) if ofi_vals else 0
    scores["ofi"] = round(ofi_avg, 4)
    
    if ofi_avg > 0.15:
        bullish += 1
        scores["ofi_verdict"] = "bullish"
    elif ofi_avg < -0.15:
        bearish += 1
        scores["ofi_verdict"] = "bearish"
    else:
        scores["ofi_verdict"] = "neutral"
    
    # 6. ATR volatility check
    tr = []
    for i in range(1, min(15, n)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr.append(max(hl, hc, lc))
    atr = float(np.mean(tr)) if tr else 10.0
    
    scores["atr_5m"] = round(atr, 2)
    atr_15m = atr * np.sqrt(3)
    
    # 7. Session phase
    et_minutes = datetime.now(timezone.utc).hour * 60 + datetime.now(timezone.utc).minute - 4 * 60
    
    if 570 <= et_minutes < 600:  # Open
        scores["session_phase"] = "OPEN — OBSERVE ONLY"
        scores["session_ok"] = False
    elif 600 <= et_minutes < 720:  # Mid-morning
        scores["session_phase"] = "MID-MORNING — TRADE"
        scores["session_ok"] = True
        bullish += 1
    elif 720 <= et_minutes < 840:  # Lunch
        scores["session_phase"] = "LUNCH — REDUCE SIZE"
        scores["session_ok"] = False
    elif 840 <= et_minutes < 960:  # Power hour
        scores["session_phase"] = "POWER HOUR — ACTIVE"
        scores["session_ok"] = True
        bullish += 1
    else:
        scores["session_phase"] = "CLOSED"
        scores["session_ok"] = False
    
    total_signals = bearish + bullish
    net_score = bearish / total_signals if total_signals > 0 else 0.5
    
    scores["net_bearish_pct"] = round(net_score, 4)
    scores["total_bullish"] = bullish
    scores["total_bearish"] = bearish
    
    return scores, atr, atr_15m


def make_decision(scores: dict, atr: float, atr_15m: float, 
                  data_fresh: bool, data_msg: str) -> TradeDecision:
    """Deterministic trade decision from composite scores"""
    
    now = datetime.now(timezone.utc).isoformat()
    decision = TradeDecision(
        timestamp=now,
        decision="NO_TRADE",
        regime="UNKNOWN",
        direction="FLAT",
        composite_score=0.5,
        conviction="LOW",
        max_contracts=0,
        suggested_contracts=0,
        atr=round(atr, 2),
        stop_loss_pts=0,
        target1_pts=0,
        target2_pts=0,
        trail_pts=0,
        safety_checks={},
        warnings=[data_msg]
    )
    
    # Safety check 1: Data freshness
    if not data_fresh:
        decision["warnings"].append("C1: STALE DATA — cannot trade")
        return decision
    
    # Safety check 2: Session hours
    if not scores.get("session_ok", False):
        decision["warnings"].append(f"C2: Outside optimal session ({scores.get('session_phase', 'unknown')})")
        if "OPEN" in scores.get("session_phase", ""):
            # Open = observe only
            return decision
        # Lunch and closed still allow reduced trades
    
    # Safety check 3: Volume adequacy
    if scores.get("volume_verdict") == "low_volume":
        decision["warnings"].append("C3: Low volume — unreliable signals")
    
    # Determine direction from composite
    bullish = scores.get("total_bullish", 0)
    bearish = scores.get("total_bearish", 0)
    total = bullish + bearish
    
    if total == 0:
        decision["warnings"].append("No signals computed")
        return decision
    
    net = (bullish / total) - (bearish / total)
    decision["composite_score"] = round(net, 4)
    
    # Conviction levels
    if net > 0.3:  # >65% bullish
        decision["direction"] = "LONG"
        decision["conviction"] = "HIGH" if net > 0.5 else "MEDIUM"
    elif net < -0.3:  # >65% bearish
        decision["direction"] = "SHORT"
        decision["conviction"] = "HIGH" if abs(net) > 0.5 else "MEDIUM"
    else:
        decision["direction"] = "FLAT"
        decision["conviction"] = "LOW"
    
    # Regime from FFT
    regime = scores.get("fft_verdict", "neutral")
    if regime == "bearish":
        decision["regime"] = "BEARISH/range"
        if decision["direction"] == "SHORT":
            decision["conviction"] = "HIGH"  # Regime confirms direction
        elif decision["direction"] == "LONG":
            decision["conviction"] = "LOW"  # Regime contradicts direction
    elif regime == "bullish":
        decision["regime"] = "BULLISH/trending"
        if decision["direction"] == "LONG":
            decision["conviction"] = "HIGH"
        elif decision["direction"] == "SHORT":
            decision["conviction"] = "LOW"
    else:
        decision["regime"] = "NEUTRAL/range"
    
    # Position sizing from ATR
    atr_sl = atr_15m * 1.8  # 1.8x ATR(15m) for SL
    
    if decision["conviction"] == "HIGH":
        max_contracts = 4
        if decision["direction"] == "FLAT":
            max_contracts = 0
    elif decision["conviction"] == "MEDIUM":
        max_contracts = 2
    else:
        max_contracts = 1 if decision["direction"] != "FLAT" else 0
    
    decision["max_contracts"] = max_contracts
    decision["stop_loss_pts"] = round(atr_sl, 1)
    decision["target1_pts"] = round(atr_sl * 1.5, 1)
    decision["target2_pts"] = round(atr_sl * 3.0, 1)
    decision["trail_pts"] = round(atr_sl * 0.8, 1)
    
    # Account isolation: split contracts across accounts
    if max_contracts >= 4:
        decision["suggested_contracts"] = 4
        decision["account_split"] = {
            "lucidflex_1": 1,
            "lucidflex_2": 1,
            "fundednext": 1,
            "topstep": 1
        }
    elif max_contracts >= 2:
        decision["suggested_contracts"] = 2
        decision["account_split"] = {
            "lucidflex_1": 1,
            "lucidflex_2": 0,
            "fundednext": 1,
            "topstep": 0
        }
    elif max_contracts >= 1:
        decision["suggested_contracts"] = 1
        decision["account_split"] = {
            "lucidflex_1": 1,
            "lucidflex_2": 0,
            "fundednext": 0,
            "topstep": 0
        }
    else:
        decision["suggested_contracts"] = 0
        decision["account_split"] = {a: 0 for a in ["lucidflex_1", "lucidflex_2", "fundednext", "topstep"]}
    
    # Stagger entries (5 min delay between accounts)
    if max_contracts > 0:
        decision["stagger_minutes"] = 5
    
    # Final go/no-go
    if decision["direction"] == "FLAT" or max_contracts == 0:
        decision["decision"] = "NO_TRADE"
    elif decision["conviction"] == "LOW" and max_contracts <= 1:
        decision["decision"] = "NO_TRADE"
    elif decision["conviction"] == "MEDIUM":
        decision["decision"] = "REDUCED"
    else:
        decision["decision"] = "TRADE"
    
    return decision


def main():
    print("=" * 65)
    print("  UNIFIED PRE-TRADE CHECKER v2.0 — Institutional Grade")
    print("=" * 65)
    print()
    
    # 1. Fetch data
    print("[1/5] Fetching NQ data...", end=" ")
    sys.stdout.flush()
    data = fetch_nq_data()
    
    if "error" in data:
        print(f"\n  ❌ FETCH FAILED: {data['error']}")
        sys.exit(1)
    
    closes = data.get("closes", [])
    highs = data.get("highs", [])
    lows = data.get("lows", [])
    opens = data.get("opens", [])
    volumes = data.get("volumes", [])
    timestamps = data.get("timestamps", [])
    
    # Filter NaN
    arr_c = np.array(closes, dtype=np.float64)
    arr_h = np.array(highs, dtype=np.float64)
    arr_l = np.array(lows, dtype=np.float64)
    arr_o = np.array(opens, dtype=np.float64) if opens else arr_c
    arr_v = np.array(volumes, dtype=np.float64)
    
    # Use minimum length for all arrays
    min_len = min(len(arr_c), len(arr_h), len(arr_l), len(arr_v), len(arr_o))
    arr_c = arr_c[:min_len]
    arr_h = arr_h[:min_len]
    arr_l = arr_l[:min_len]
    arr_o = arr_o[:min_len]
    arr_v = arr_v[:min_len]
    
    mask = ~(np.isnan(arr_c) | np.isnan(arr_h) | np.isnan(arr_l))
    closes = arr_c[mask].tolist()
    highs = arr_h[mask].tolist()
    lows = arr_l[mask].tolist()
    opens = arr_o[mask].tolist()
    volumes = arr_v[mask].tolist()
    
    print(f"✅ {len(closes)} bars")
    
    # 2. Data freshness
    print("[2/5] Checking data freshness...", end=" ")
    sys.stdout.flush()
    fresh, msg = check_data_freshness(timestamps)
    print(f"{'✅' if fresh else '❌'} {msg}")
    
    if len(closes) < 20:
        print("\n  ❌ INSUFFICIENT DATA — need at least 20 bars")
        sys.exit(1)
    
    # 3. Composite score
    print("[3/5] Computing composite edge score...", end=" ")
    sys.stdout.flush()
    scores, atr, atr_15m = compute_composite_score(closes, highs, lows, volumes)
    print(f"✅ Bullish={scores['total_bullish']} Bearish={scores['total_bearish']}")
    
    # 4. Decision
    print("[4/5] Making deterministic decision...")
    sys.stdout.flush()
    decision = make_decision(scores, atr, atr_15m, fresh, msg)
    
    # 5. Output
    print(f"[5/5] Decision: {decision['decision']}")
    print()
    
    # Display
    emoji = "✅" if decision["decision"] == "TRADE" else ("⚠️" if decision["decision"] == "REDUCED" else "❌")
    print(f"  {emoji} DECISION: {decision['decision']}")
    print(f"  Direction: {decision['direction']} | Conviction: {decision['conviction']}")
    print(f"  Regime: {decision['regime']} | Composite: {decision['composite_score']:+.4f}")
    print()
    
    if decision["max_contracts"] > 0:
        print(f"  Position (total): {decision['max_contracts']} MNQ")
        print(f"  Suggested split: {decision.get('account_split', {})}")
        print(f"  Stagger: {decision.get('stagger_minutes', 0)} min between accounts")
        print(f"  SL: {decision['stop_loss_pts']} pts | TP1: {decision['target1_pts']} | TP2: {decision['target2_pts']}")
        print(f"  Trail: {decision['trail_pts']} pts")
    else:
        print("  NO POSITION recommended")
    
    if decision["warnings"]:
        print(f"\n  ⚠️  WARNINGS ({len(decision['warnings'])}):")
        for w in decision["warnings"]:
            print(f"    • {w}")
    
    # Save for signalRouter consumption
    output_path = os.path.expanduser("~/.rumbling-hedge/state/pre_trade_decision.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(decision, f, indent=2, default=str)
    print(f"\n  💾 Saved to {output_path}")
    print()

if __name__ == "__main__":
    main()
