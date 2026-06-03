#!/usr/bin/env python3
"""
SIGNAL ARBITRATION LAYER — Resolves 12 signal conflicts into 1 decision
Reads canonical hedge/.rumbling-hedge/state first, with legacy home state as
read-only fallback for migration.
"""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone

HOME = Path.home()
STATE1 = HOME / "hedge" / ".rumbling-hedge" / "state"
STATE2 = HOME / ".rumbling-hedge" / "state"

SIGNALS = {
    "pead-signal": {"weight": 1.5, "type": "fundamental"},
    "sr-proximity-signal": {"weight": 1.0, "type": "technical"},
    "donchian-signal": {"weight": 0.8, "type": "trend"},
    "ichimoku-signal": {"weight": 1.2, "type": "technical"},
    "insider-signal": {"weight": 1.5, "type": "fundamental"},
    "noise-analysis": {"weight": 0.8, "type": "regime"},
    "cot-signal": {"weight": 1.0, "type": "fundamental"},
    "vwap-signal": {"weight": 0.8, "type": "mean_rev"},
    "heiken-ashi-signal": {"weight": 0.6, "type": "trend"},
    "fibonacci-signal": {"weight": 0.5, "type": "technical"},
    "kalman-pairs-signal": {"weight": 0.8, "type": "stat_arb"},
    "whale-flow-signal": {"weight": 0.5, "type": "flow"},
}

PROMOTION_REQUIRED = {
    "pead-signal",
    "sr-proximity-signal",
    "donchian-signal",
    "ichimoku-signal",
    "insider-signal",
    "noise-analysis",
    "cot-signal",
    "vwap-signal",
    "heiken-ashi-signal",
    "fibonacci-signal",
    "kalman-pairs-signal",
    "whale-flow-signal",
}

def promoted_execution_overlay(data):
    return (
        isinstance(data, dict)
        and data.get("promoted_for_execution") is True
        and data.get("tradable_signal") is True
    )

def requires_promotion(name):
    return name in PROMOTION_REQUIRED

def load_state(file):
    for base in [STATE1, STATE2]:
        path = base / f"{file}.latest.json"
        if path.exists():
            try: return json.loads(path.read_text())
            except: pass
    return None

def extract_direction(name, data):
    if not data: return (0, 0)
    if requires_promotion(name) and not promoted_execution_overlay(data):
        return (0, 0)
    if name == "pead-signal":
        bias = data.get("nq_bias", "neutral")
        conf = data.get("confidence", 0.5)
        m = {"bullish": 1, "bearish": -1, "neutral": 0}
        return (m.get(bias, 0), conf)
    elif name == "sr-proximity-signal":
        conf = data.get("confidence", 0.5)
        sigs = data.get("signals", [])
        d = sum(1 for s in sigs if "LONG" in str(s)) - sum(1 for s in sigs if "SHORT" in str(s))
        return (d / max(len(sigs), 1), conf * 0.8)
    elif name == "donchian-signal":
        a = data.get("signal", "HOLD")
        m = {"LONG": 1, "SHORT": -1, "ENTER_LONG": 1, "ENTER_SHORT": -1, "HOLD": 0, "EXIT": 0}
        return (m.get(a, 0), 0.5)
    elif name == "ichimoku-signal":
        a = data.get("action", "HOLD")
        st = data.get("trend_strength", 0.5)
        m = {"BUY": 1, "SELL": -1, "ENTER": 0.5, "HOLD": 0}
        return (m.get(a, 0), st)
    elif name == "insider-signal":
        bias = data.get("nq_bias", "neutral")
        conf = data.get("confidence", 0.5)
        m = {"bullish": 1, "bearish": -1, "neutral": 0}
        return (m.get(bias, 0), conf)
    elif name == "noise-analysis":
        for sym in ["NQ", "ES"]:
            sf = data.get(sym, {}).get("step_forward", {})
            if sf.get("oos_consistency", 0) > 0.6: return (0.5, 0.6)
        return (0, 0.3)
    elif name == "cot-signal":
        nq = data.get("markets", {}).get("NQ", {})
        m = {"bullish": 1, "bearish": -1, "neutral": 0}
        nq_d = nq.get("direction", data.get("nq_bias", "neutral"))
        dealer_z = nq.get("dealer", {}).get("z_score", 0)
        conf = min(abs(dealer_z) / 2, 0.4)
        return (m.get(nq_d, 0), conf)
    elif name == "vwap-signal":
        nq = data.get("NQ", {})
        if nq.get("confidence", 0) > 0.3:
            m = {"long": 1, "short": -1, "neutral": 0}
            return (m.get(nq.get("direction", "neutral"), 0), nq.get("confidence", 0))
        return (0, 0)
    elif name == "heiken-ashi-signal":
        nq = data.get("NQ", {})
        c = nq.get("color", "green")
        if nq.get("flip", False):
            return (0.5 if c == "green" else -0.5, 0.3)
        m = {"green": 0.2, "red": -0.2, "neutral": 0}
        return (m.get(c, 0), 0.2)
    elif name == "fibonacci-signal":
        nq = data.get("NQ", {}).get("signal", {})
        d = nq.get("direction", "neutral")
        m = {"bullish": 0.3, "bearish": -0.3, "neutral": 0}
        return (m.get(d, 0), 0.3)
    elif name == "kalman-pairs-signal":
        a = data.get("strategy", "HOLD")
        m = {"ENTRY_LONG": 0.5, "ENTRY_SHORT": -0.5, "EXIT": 0, "HOLD": 0}
        return (m.get(a, 0), 0.4)
    elif name == "whale-flow-signal":
        d = data.get("direction", "neutral")
        c = data.get("confidence", 0)
        m = {"bullish": 1, "bearish": -1, "neutral": 0}
        return (m.get(d, 0), c)
    return (0, 0)

def arbitrate():
    print(f"SIGNAL ARBITRATION — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    total_w, weighted_d, active = 0, 0, 0
    details = []
    for name, meta in SIGNALS.items():
        data = load_state(name)
        direction, confidence = extract_direction(name, data)
        ignored_unpromoted = bool(data) and requires_promotion(name) and not promoted_execution_overlay(data)
        if data and confidence > 0:
            active += 1
            w = meta["weight"] * confidence
            weighted_d += direction * w
            total_w += w
            arrow = "🟢" if direction > 0.3 else ("🔴" if direction < -0.3 else "⚪")
            print(f"  {arrow} {name:<20s} d={direction:+.2f} c={confidence:.2f} w={meta['weight']}")
            details.append({"signal": name, "type": meta["type"],
                "direction": round(direction, 3), "confidence": round(confidence, 3),
                "weight": meta["weight"], "promotedForExecution": promoted_execution_overlay(data),
                "ignoredUnpromoted": False})
        elif ignored_unpromoted:
            details.append({"signal": name, "type": meta["type"],
                "direction": 0, "confidence": 0, "weight": meta["weight"],
                "promotedForExecution": False, "ignoredUnpromoted": True})
    if total_w > 0: final_d = weighted_d / total_w
    else: final_d = 0
    print(f"\n  Active: {active}/{len(SIGNALS)}, Direction: {final_d:+.3f}")
    
    if abs(final_d) < 0.15:
        dec, dire, conv, reason = "NO_TRADE", "FLAT", "LOW", f"No consensus"
    elif final_d > 0.3:
        dec, dire, conv = "TRADE", "LONG", "HIGH" if final_d > 0.5 else "MEDIUM"
        reason = f"Bullish consensus"
    elif final_d < -0.3:
        dec, dire, conv = "TRADE", "SHORT", "HIGH" if final_d < -0.5 else "MEDIUM"
        reason = f"Bearish consensus"
    else:
        dire = "LONG" if final_d > 0 else "SHORT"
        dec, conv, reason = "REDUCED", "LOW", f"Weak {dire}"
    
    sb = sum(1 for d in details if d["direction"] > 0.3 and d["confidence"] > 0.5)
    ss = sum(1 for d in details if d["direction"] < -0.3 and d["confidence"] > 0.5)
    conflicts = []
    if sb > 0 and ss > 0:
        conflicts.append(f"{sb} bullish vs {ss} bearish strong signals")
    
    result = {"timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": "NQ", "decision": dec, "direction": dire,
        "conviction": conv, "weighted_dir": round(final_d, 3),
        "active_signals": active, "total_signals": len(SIGNALS),
        "conflicts": conflicts, "reason": reason, "details": details}
    
    out1 = STATE1 / "arbitration.latest.json"
    out2 = STATE2 / "arbitration.latest.json"
    data = json.dumps(result, indent=2, default=str)
    out1.write_text(data); out2.write_text(data)
    
    print(f"  {dec} | {dire} | {conv}")
    print(f"  Conflicts: {conflicts if conflicts else 'none'}")
    print(f"✅ Arbitration written to both locations")
    return result

if __name__ == "__main__":
    arbitrate()
