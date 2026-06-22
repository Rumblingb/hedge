#!/usr/bin/env python3
"""gc_orb_5m_signal.py — GC ORB 5m signal generator.

Reads GC 5m bars, computes opening-range breakout, writes signal state.
Parameters: range_window=6, hold=6, vol_threshold=1.6 (from cross-instrument test).

Research basis: orb_cross_instrument_test.py on GC-5m-60d → PF 1.91, +175.8 pts.
This is a candidate signal pending full experiment.py OOS gate.

promoted_for_execution=False until gated.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Use hedge .venv Python
VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge" / "state"
DATA = ROOT / "data" / "free"
SIGNAL_PATH = STATE / "gc-orb-5m-signal.latest.json"

sys.path.insert(0, str(ROOT / "scripts"))
from common import atomic_write_json

RANGE_BARS = 6
HOLD_BARS = 6
VOL_THRESH = 1.6
COST = 1.5


def load_gc_5m():
    path = DATA / "GC-5m-60d.csv"
    if not path.exists():
        return None
    rows = []
    with open(path, "r") as f:
        header = None
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if header is None:
                header = parts
                continue
            try:
                ts = parts[0]
                o = float(parts[2])
                h = float(parts[3])
                l = float(parts[4])
                c = float(parts[5])
                v = float(parts[6]) if len(parts) > 6 else 0.0
                rows.append({
                    "ts": ts, "open": o, "high": h,
                    "low": l, "close": c, "volume": v,
                })
            except (ValueError, IndexError):
                continue
    return rows


def session_key(ts):
    # UTC calendar day as session proxy
    return ts[:10]


def compute_signal(bars):
    sessions = {}
    for b in bars:
        sessions.setdefault(session_key(b["ts"]), []).append(b)

    today = datetime.now(timezone.utc).date().isoformat()
    if today not in sessions:
        return None

    sb = sessions[today]
    if len(sb) < RANGE_BARS + HOLD_BARS + 1:
        return None

    orb = sb[:RANGE_BARS]
    orb_high = max(x["high"] for x in orb)
    orb_low = min(x["low"] for x in orb)
    orb_range = orb_high - orb_low
    if orb_range <= 0:
        return None

    # Average volume over range window
    avg_vol = sum(x["volume"] for x in orb) / len(orb) if orb[0]["volume"] > 0 else 0

    # Find first breakout after range with volume confirmation
    breakout_idx = None
    direction = None
    for i in range(RANGE_BARS, len(sb) - HOLD_BARS):
        b = sb[i]
        if b["close"] > orb_high:
            direction = "bullish"
            breakout_idx = i
            break
        if b["close"] < orb_low:
            direction = "bearish"
            breakout_idx = i
            break

    if direction is None or breakout_idx is None:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal_name": "gc-orb-5m",
            "direction": "neutral",
            "confidence": 0.0,
            "promoted_for_execution": False,
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "readyForExecution": False,
            "readyForDemoExpansion": False,
            "readyForLive": False,
            "active_window": True,
            "metadata": {
                "reason": "no_breakout",
                "orb_high": round(orb_high, 2),
                "orb_low": round(orb_low, 2),
                "orb_range": round(orb_range, 2),
            },
        }

    # Volume confirmation
    breakout_vol = sb[breakout_idx]["volume"]
    vol_ok = avg_vol > 0 and (breakout_vol / avg_vol) >= VOL_THRESH

    # Confidence: stronger on wider range + volume confirmation
    range_conf = min(orb_range / 20.0, 0.5)  # normalized
    vol_conf = 0.3 if vol_ok else 0.0
    confidence = round(min(range_conf + vol_conf, 0.5), 3)

    entry = sb[breakout_idx]["close"]
    exit_idx = breakout_idx + HOLD_BARS
    if exit_idx >= len(sb):
        return None

    exit_price = sb[exit_idx]["close"]
    net = (exit_price - entry) * (1 if direction == "bullish" else -1) - COST

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_name": "gc-orb-5m",
        "direction": direction,
        "confidence": confidence,
        "promoted_for_execution": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "active_window": True,
        "metadata": {
            "orb_high": round(orb_high, 2),
            "orb_low": round(orb_low, 2),
            "orb_range": round(orb_range, 2),
            "avg_vol": round(avg_vol, 1),
            "breakout_vol": round(breakout_vol, 1),
            "vol_confirmed": vol_ok,
            "entry_bar": breakout_idx,
            "exit_bar": exit_idx,
            "net_points": round(net, 2),
            "timeframe": "5m",
            "symbol": "GC",
            "source": "orb_cross_instrument_test_2026-06-16",
        },
    }


def main():
    bars = load_gc_5m()
    if bars is None:
        print("gc-orb-5m: data not available", file=sys.stderr)
        sys.exit(1)

    signal = compute_signal(bars)
    if signal is None:
        print("gc-orb-5m: insufficient data or no valid signal")
        sys.exit(0)

    atomic_write_json(SIGNAL_PATH, signal, indent=2)
    print(json.dumps(signal, indent=2))


if __name__ == "__main__":
    main()
