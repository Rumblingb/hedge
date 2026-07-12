#!/usr/bin/env python3
"""orb3m_es_signal.py — ES ORB 3m vt=1.6 signal generator (DEMO lane B).

Faithful ES sibling of orb3m_vt16_signal.py. Reads live ES 1m bars from the
read-only Topstep archive, resamples to 3m, computes the SAME blessed ORB config
(range 6, hold 6, vt 1.6, stop_atr 1.0, tp_rr 2.0) and writes an ES signal that
the Lane-B bridge submits to the ES DEMO account 23268236.

Founder-approved 2026-06-13 (demo-only). Evidence: ORB-3m structurally confirmed
on 20yr ES (2000-2019) — PF>=1.5 + positive net across dot-com/GFC/QE regime
blocks, 5/5 walkforward, shuffle-robust (loop-research/es20yr-orb-robustness.json).
DEMO-only: routes only through the guarded bridge, gated by the Lane-B daily-plan
approval token, 2-trade/day cap, and a bounded experiment budget. No live flag.
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import atomic_write_json

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
BARS = ROOT / ".rumbling-hedge/research/topstep-readonly-bars"
SIGNAL_PATH = STATE / "es-orb3m-signal.latest.json"

RANGE_BARS = 6
HOLD_BARS = 6
VOL_THRESH = 1.6
ENTRY_OFFSET = 0
TICK_SIZE = 0.25
STOP_ATR = 1.0
TP_RR = 2.0


def load_es_bars():
    csv_path = BARS / "ES-1m-topstep-readonly.csv"
    if not csv_path.exists():
        for cand in ("data/free/ES-1m-gap-2026.csv", "data/free/ES-1m-2020-2024.csv"):
            if (ROOT / cand).exists():
                csv_path = ROOT / cand
                break
    import pandas as pd
    df = pd.read_csv(csv_path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    if "symbol" in df.columns:
        df = df[df["symbol"] == "ES"].copy()
    df = df.sort_values("ts").set_index("ts")
    resampled = df.resample("3min", label="right", closed="right").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum" if "volume" in df.columns else "first",
    }).dropna().reset_index()
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
    df = load_es_bars()
    if df.empty:
        return None
    today = datetime.now(timezone.utc).astimezone().date()
    today_bars = df[df["date"] == today].copy()
    if today_bars.empty:
        return None
    opening = today_bars[today_bars["minutes_from_open"] < RANGE_BARS * 3].copy()
    after = today_bars[today_bars["minutes_from_open"] >= RANGE_BARS * 3].copy()
    if opening.empty or after.empty:
        return None
    range_high = opening["high"].max()
    range_low = opening["low"].min()
    atr = compute_atr(df)
    atr_val = float(atr.iloc[-1]) if not atr.empty else 4.0
    recent = after.tail(3)
    if recent.empty:
        return None
    vol_floor = float(opening["volume"].rolling(5, min_periods=3).mean().iloc[-1]) * VOL_THRESH
    if recent["high"].max() > range_high + ENTRY_OFFSET * TICK_SIZE:
        entry_bar = recent[recent["high"] > range_high].iloc[0]
        if VOL_THRESH <= 1 or entry_bar["volume"] >= vol_floor:
            entry = range_high
            sl = entry - atr_val * STOP_ATR
            tp = entry + (entry - sl) * TP_RR
            rr = (tp - entry) / (entry - sl) if (entry - sl) > 0 else 0
            return {"side": "long", "entry": entry, "stop": sl, "target": tp, "rr": rr,
                    "reason": f"long_breakout_{range_high:.2f}", "price_now": float(recent.iloc[-1]["close"])}
    if recent["low"].min() < range_low - ENTRY_OFFSET * TICK_SIZE:
        entry_bar = recent[recent["low"] < range_low].iloc[0]
        if VOL_THRESH <= 1 or entry_bar["volume"] >= vol_floor:
            entry = range_low
            sl = entry + atr_val * STOP_ATR
            tp = entry - (sl - entry) * TP_RR
            rr = (entry - tp) / (sl - entry) if (sl - entry) > 0 else 0
            return {"side": "short", "entry": entry, "stop": sl, "target": tp, "rr": rr,
                    "reason": f"short_breakout_{range_low:.2f}", "price_now": float(recent.iloc[-1]["close"])}
    return None


def write_signal(signal):
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "ts": now,
        "signal": f"{signal['side']}@es-orb3m-vt16",
        "strategy": "es-orb3m-vt16",
        "side": signal["side"],
        "direction": signal["side"],
        "entry": signal["entry"],
        "stop": signal["stop"],
        "target": signal["target"],
        "rr": round(signal["rr"], 2),
        "contracts": 1,
        "route": "topstep_demo",
        "submitted": False,
        "status": "signal_generated",
        "price_now": signal["price_now"],
        "reason": signal["reason"],
        "confidence": 0.8,
        "promoted_for_execution": True,
        "tradable_signal": True,
        "execution_firewall": {"allowed": False, "blockers": ["pending_bridge_check"]},
    }
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(SIGNAL_PATH, payload)
    print(f"ES signal: {signal['side']} @ {signal['entry']:.2f} "
          f"(SL={signal['stop']:.2f}, TP={signal['target']:.2f}, RR={signal['rr']:.2f})")
    return payload


if __name__ == "__main__":
    sig = generate_signal()
    if sig:
        write_signal(sig)
    else:
        print("No ES signal — no breakout detected")
        sys.exit(0)
