#!/usr/bin/env python3
"""
New Arsenal Gate — Pre-trade filter module
===========================================
Reads all new arsenal signals and blocks/confirms trades.
Imported by master_bridge.py to add the new arsenal gate.

Usage:
    from new_arsenal_gate import new_arsenal_gate
    
    # In master_bridge, after best signal is selected:
    result = new_arsenal_gate(best)
    if result["verdict"] == "NO_TRADE":
        print(f"Blocked: {result['reasons']}")
        return
    modifier = result["confidence_modifier"]
"""
import json, os
from pathlib import Path

STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/state"))

def read_signal(name):
    """Read any state file from the new arsenal"""
    try:
        p = STATE_DIR / name
        if p.exists():
            return json.loads(p.read_text())
    except:
        pass
    return {}

def new_arsenal_gate(best_signal):
    """
    Pre-trade gate using all new arsenal signals.
    
    Reads PEAD, S/R, Donchian, Ichimoku, Insider, COT, DOM, Kalman
    Computes consensus NQ bias and compares against proposed trade direction.
    
    Returns: {"verdict": "TRADE"/"NO_TRADE"/"CAUTION", 
              "confidence_modifier": float,
              "reasons": [str]}
    """
    reasons = []
    modifier = 1.0
    side = best_signal.get("side", "long") if best_signal else "neutral"
    verdict = "TRADE"
    
    # Read all signals
    pead = read_signal("pead-signal.latest.json")
    sr = read_signal("sr-proximity-signal.latest.json")
    donchian = read_signal("donchian-signal.latest.json")
    ichimoku = read_signal("ichimoku-signal.latest.json")
    insider = read_signal("insider-signal.latest.json")
    cot = read_signal("cot-signal.latest.json")
    kalman = read_signal("kalman-pairs-signal.latest.json")
    dom = read_signal("dom-proxy-signal.latest.json")
    
    # Check kill switch first
    emergency = STATE_DIR / "EMERGENCY_STOP"
    if emergency.exists():
        reasons.append("🚨 KILL SWITCH ACTIVE — no trades permitted")
        return {"verdict": "NO_TRADE", "confidence_modifier": 0.0, "reasons": reasons}
    
    # 1. Insider Trading Signal
    insider_bias = insider.get("nq_bias", "neutral") if insider else "neutral"
    insider_conf = insider.get("confidence", 0.0) if insider else 0.0
    if insider_bias in ("bearish", "very_bearish") and side == "long":
        if insider_conf > 0.6:
            reasons.append(f"🔴 INSIDER OVERRIDE: SEC insiders aggressively selling (conf={insider_conf:.2f})")
            modifier *= 0.3
            verdict = "CAUTION"
        elif insider_conf > 0.4:
            reasons.append(f"🟡 Insider selling detected, reducing size")
            modifier *= 0.6
    elif insider_bias in ("bullish", "very_bullish") and side == "short":
        if insider_conf > 0.6:
            reasons.append(f"🔴 INSIDER OVERRIDE: Insiders buying, short trade at risk")
            modifier *= 0.3
            verdict = "CAUTION"
    elif insider_bias in ("bullish", "very_bullish") and side == "long":
        modifier *= 1.15
        reasons.append(f"✅ Insider buying confirms direction")
    
    # 2. Ichimoku System
    ichi_trend = ichimoku.get("trend", "neutral") if ichimoku else "neutral"
    if ichi_trend == "bearish" and side == "long":
        reasons.append("🌊 Ichimoku bearish (price rejecting at Kijun)")
        modifier *= 0.7
    elif ichi_trend == "bullish" and side == "short":
        reasons.append("🌊 Ichimoku bullish (price above cloud)")
        modifier *= 0.7
    elif ichi_trend == "neutral":
        modifier *= 0.9  # Neutral trend → less conviction
        reasons.append("🌊 Ichimoku neutral — no trend confirmation")
    
    # 3. COT (Government Filing) Signal
    cot_bias = cot.get("nq_bias", "neutral") if cot else "neutral"
    if cot_bias in ("bullish", "very_bullish") and side == "long":
        modifier *= 1.1
        reasons.append("📊 COT: Commercials positioned bullish")
    elif cot_bias in ("bearish", "very_bearish") and side == "short":
        modifier *= 1.1
        reasons.append("📊 COT: Commercials positioned bearish")
    
    # 4. Donchian Channel
    if donchian:
        donch_dir = donchian.get("direction", "neutral")
        if donch_dir == "long" and side == "long":
            modifier *= 1.2
            reasons.append("📐 Donchian breakout supports direction")
        elif donch_dir == "short" and side == "short":
            modifier *= 1.2
            reasons.append("📐 Donchian breakdown supports direction")
    
    # 5. DOM Proxy — order flow confirmation
    dom_dir = dom.get("direction", "neutral") if dom else "neutral"
    dom_conf = dom.get("confidence", 0.0) if dom else 0.0
    if dom_dir == side and dom_conf > 0.5:
        modifier *= 1.15
        reasons.append("📈 DOM order flow confirms direction")
    elif dom_dir != "neutral" and dom_dir != side and dom_conf > 0.5:
        modifier *= 0.6
        reasons.append(f"📉 DOM order flow ({dom_dir}) opposes {side} trade")
    
    # 6. Kalman Pairs
    kalman_action = kalman.get("action", "HOLD") if kalman else "HOLD"
    kalman_dir = kalman.get("direction", "neutral") if kalman else "neutral"
    if kalman_action != "HOLD" and kalman_dir == side:
        modifier *= 1.1
        reasons.append(f"🔗 Kalman pairs confirms with {kalman_dir} bias")
    
    # Clamp modifier
    modifier = max(0.0, min(modifier, 2.0))
    
    if modifier < 0.3:
        verdict = "NO_TRADE"
    elif modifier < 0.6:
        verdict = "CAUTION"
    
    return {"verdict": verdict, "confidence_modifier": round(modifier, 3), "reasons": reasons}
