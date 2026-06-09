#!/usr/bin/env python3
"""orb3m_vt16_signal.py — NQ ORB 3m vt=1.6 signal generator.
Reads live Topstep bars, computes ORB, writes to master-signal.latest.json.
Bridge picks it up and submits to Topstep demo account.
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

# Use hedge .venv Python (has pandas, numpy, etc.)
VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
BARS = ROOT / ".rumbling-hedge/research/topstep-readonly-bars"
SIGNAL_PATH = STATE / "master-signal.latest.json"

# Optimal config from Phase 2
RANGE_BARS = 6      # range_window_bars
HOLD_BARS = 6       # hold_bars (post-breakout)
VOL_THRESH = 1.6    # volume_threshold
ENTRY_OFFSET = 0    # entry_offset_ticks
TICK_SIZE = 0.25
COST = 1.5          # cost_points
STOP_ATR = 1.0      # stop_loss_atr
TP_RR = 2.0         # take_profit_rr

def read_json(path):
    try: return json.loads(path.read_text())
    except: return {}

def load_nq_bars():
    csv_path = BARS / "NQ-1m-topstep-readonly.csv"
    if not csv_path.exists():
        csv_path = ROOT / "data/free/NQ-1m-combined.csv"
    import pandas as pd
    df = pd.read_csv(csv_path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    if "symbol" in df.columns:
        df = df[df["symbol"] == "NQ"].copy()
    df = df.sort_values("ts")
    # Resample to 3m
    df = df.set_index("ts")
    resampled = df.resample("3min", label="right", closed="right").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum" if "volume" in df.columns else "first"
    }).dropna().reset_index()
    # Compute session
    et = resampled["ts"].dt.tz_convert("America/New_York")
    resampled["minutes_from_open"] = et.dt.hour * 60 + et.dt.minute - (9 * 60 + 30)
    resampled["date"] = et.dt.date
    return resampled

def compute_atr(df, period=14):
    import pandas as pd
    tr = pd.concat([
        abs(df["high"] - df["low"]),
        abs(df["high"] - df["close"].shift(1)),
        abs(df["low"] - df["close"].shift(1)),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=7).mean()

def generate_signal():
    import pandas as pd
    df = load_nq_bars()
    if df.empty:
        return None
    
    today = datetime.now(timezone.utc).astimezone().date()
    today_bars = df[df["date"] == today].copy()
    if today_bars.empty:
        return None
    
    # Opening range: first RANGE_BARS bars after NY open (minutes_from_open >= 0)
    opening = today_bars[today_bars["minutes_from_open"] < RANGE_BARS * 3].copy()
    after = today_bars[today_bars["minutes_from_open"] >= RANGE_BARS * 3].copy()
    
    if opening.empty or after.empty:
        return None
    
    range_high = opening["high"].max()
    range_low = opening["low"].min()
    atr = compute_atr(df)
    atr_val = float(atr.iloc[-1]) if not atr.empty else 15.0
    
    # Check for breakout
    recent = after.tail(3)  # Check last 3 bars
    if recent.empty:
        return None
    
    vol_floor = float(opening["volume"].rolling(5, min_periods=3).mean().iloc[-1]) * VOL_THRESH
    
    # Long breakout
    if recent["high"].max() > range_high + ENTRY_OFFSET * TICK_SIZE:
        entry_bar = recent[recent["high"] > range_high].iloc[0]
        if VOL_THRESH <= 1 or entry_bar["volume"] >= vol_floor:
            entry = range_high
            sl = entry - atr_val * STOP_ATR
            tp = entry + (entry - sl) * TP_RR
            rr = (tp - entry) / (entry - sl) if (entry - sl) > 0 else 0
            return {"side": "long", "entry": entry, "stop": sl, "target": tp, "rr": rr,
                    "reason": f"long_breakout_{range_high:.1f}", "price_now": float(recent.iloc[-1]["close"])}
    
    # Short breakout
    if recent["low"].min() < range_low - ENTRY_OFFSET * TICK_SIZE:
        entry_bar = recent[recent["low"] < range_low].iloc[0]
        if VOL_THRESH <= 1 or entry_bar["volume"] >= vol_floor:
            entry = range_low
            sl = entry + atr_val * STOP_ATR
            tp = entry - (sl - entry) * TP_RR
            rr = (entry - tp) / (sl - entry) if (sl - entry) > 0 else 0
            return {"side": "short", "entry": entry, "stop": sl, "target": tp, "rr": rr,
                    "reason": f"short_breakout_{range_low:.1f}", "price_now": float(recent.iloc[-1]["close"])}
    
    return None

SIGNAL_WEIGHT = 2.0  # Highest weight — this is our verified PF 4.44 edge

def write_signal(signal):
    now = datetime.now(timezone.utc).isoformat()
    now_iso = now
    payload = {
        "ts": now,
        "signal": f"{signal['side']}@orb3m-vt16",
        "strategy": "orb3m-vt16",
        "side": signal["side"],
        "direction": signal["side"],
        "entry": signal["entry"],
        "stop": signal["stop"],
        "target": signal["target"],
        "rr": round(signal["rr"], 2),
        "contracts": 1,
        "research_contracts": 3,
        "accounts": 1,
        "route": "topstep_demo",
        "submitted": False,
        "status": "signal_generated",
        "price_now": signal["price_now"],
        "reason": signal["reason"],
        "confidence": 0.8,
        "promoted_for_execution": True,
        "tradable_signal": True,
        "execution_firewall": {"allowed": False, "blockers": ["pending_bridge_check"]}
    }
    
    # Write master-signal for the bridge
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_PATH.write_text(json.dumps(payload, indent=2, default=str))
    
    # Write orb-signal for arbitration (13th signal)
    orb_signal = {
        "ts": now_iso,
        "direction": signal["side"],
        "side": signal["side"],
        "confidence": 0.8,
        "entry": signal["entry"],
        "stop": signal["stop"],
        "target": signal["target"],
        "rr": round(signal["rr"], 2),
        "reason": signal["reason"],
        "price_now": signal["price_now"],
        "promoted_for_execution": True,
        "tradable_signal": True,
    }
    orb_path = STATE / "orb-signal.latest.json"
    orb_path.write_text(json.dumps(orb_signal, indent=2, default=str))
    
    print(f"✅ Signal written: {signal['side']} @ {signal['entry']:.1f} (SL={signal['stop']:.1f}, TP={signal['target']:.1f}, RR={signal['rr']:.2f})")
    print(f"   → master-signal.latest.json (bridge)")
    print(f"   → orb-signal.latest.json (arbitration)")
    return payload

if __name__ == "__main__":
    sig = generate_signal()
    if sig:
        write_signal(sig)
        print(f"Price now: {sig['price_now']:.1f}")
    else:
        print("No signal — no breakout detected")
        sys.exit(0)
