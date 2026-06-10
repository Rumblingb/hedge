#!/usr/bin/env python3
"""GC PJI Reversal 1h live signal generator — HEURISTIC_UNVERIFIED.

Strategy: Price Jerk Indicator (PJI) for reversal detection.
Based on SSRN 6487618 — third derivative of price.

Jerk[i] = P[i] - 3*P[i-1] + 3*P[i-2] - P[i-3], normalized by price level
PJI = rolling mean of jerk over pji_lookback (smoothing)

Signal rules:
  - PJI crosses below -threshold (from above): LONG  (decelerating decline → reversal up)
  - PJI crosses above +threshold (from below): SHORT (decelerating rise → reversal down)

AI Scientist verified run (run_p3b_pji):
  - Strategy: pji, Symbol: GC, Timeframe: 1h
  - Data: data/free/GC-1h-2000-2026.csv
  - Params: pji_lookback=8, pji_threshold=0.002, hold_bars=10
  - OOS PF: 1.586, Total trades: 37, Win rate: 59.5%
  - Walkforward: 100% positive folds (5/5)
  - Total net points: +974.4

HEURISTIC_UNVERIFIED — promoted_for_execution=False.
Contributes to arbitration consensus but cannot trigger trades alone.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, time
from pathlib import Path

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge" / "state"
SIGNAL_PATH = STATE / "gc-pjireversal-signal.latest.json"

# GC 1h data source
GC_1H_CSV = ROOT / "data" / "free" / "GC-1h-2000-2026.csv"

# Strategy parameters (from AI Scientist run_p3b_pji optimal)
PJI_LOOKBACK = 8
PJI_THRESHOLD = 0.002
HOLD_BARS = 10

# AI Scientist verified metrics
SOURCE_RUN = "run_p3b_pji"
OOS_PF = 1.586
WALKFORWARD_FOLDS = 5
WALKFORWARD_POSITIVE = 5
WALKFORWARD_PCT = 100.0
OOS_TRADES = 37
OOS_WIN_RATE = 59.5
OOS_NET_POINTS = 974.4

# GC RTH (COMEX pit session): 9:00 AM - 2:30 PM ET
# During EDT (June): 13:00-18:30 UTC
GC_RTH_START_UTC = time(13, 0)
GC_RTH_END_UTC = time(18, 30)


def in_gc_rth_window(now_utc: datetime | None = None) -> bool:
    """Check if current time falls within GC RTH hours."""
    t = (now_utc or datetime.now(timezone.utc)).time()
    return GC_RTH_START_UTC <= t < GC_RTH_END_UTC


def load_gc_1h_bars() -> any:
    """Load latest GC 1h bars from data/free archive."""
    import pandas as pd
    if not GC_1H_CSV.exists():
        return None
    try:
        df = pd.read_csv(GC_1H_CSV, parse_dates=["ts"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df = df.sort_values("ts").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"GC PJI: error loading bars: {e}", file=sys.stderr)
        return None


def compute_pji_signal(closes: any) -> tuple[str, float, dict]:
    """Compute PJI indicator and return (direction, confidence, meta)."""
    import numpy as np
    if len(closes) < PJI_LOOKBACK + 5:
        return "neutral", 0.0, {"reason": "insufficient bars"}

    # Compute jerk: Jerk[i] = P[i] - 3P[i-1] + 3P[i-2] - P[i-3]
    # Normalized by price level
    series = closes.values if hasattr(closes, 'values') else np.array(closes)
    shift3 = np.roll(series, 3)
    shift2 = np.roll(series, 2)
    shift1 = np.roll(series, 1)
    jerk = series - 3 * shift1 + 3 * shift2 - shift3
    jerk[:3] = np.nan  # first 3 values are invalid
    # Normalize by price level
    jerk = jerk / (np.abs(shift3) + 1e-10)

    # PJI = rolling mean of jerk over lookback
    pji = np.convolve(jerk, np.ones(PJI_LOOKBACK) / PJI_LOOKBACK, mode="valid")
    # Pad front to align
    pad = np.full(PJI_LOOKBACK - 1, np.nan)
    pji_padded = np.concatenate([pad, pji])

    if len(pji_padded) < 2:
        return "neutral", 0.0, {"reason": "insufficient PJI values"}
    if np.isnan(pji_padded[-1]) or np.isnan(pji_padded[-2]):
        return "neutral", 0.0, {"reason": "PJI value is NaN"}

    prev_pji = float(pji_padded[-2])
    curr_pji = float(pji_padded[-1])

    direction = "neutral"
    confidence = 0.0
    signal_type = "none"

    # Cross below -threshold (from above) = LONG reversal signal
    if prev_pji > -PJI_THRESHOLD and curr_pji <= -PJI_THRESHOLD:
        direction = "bullish"
        # Confidence scales with cross magnitude
        magnitude = abs(curr_pji) / PJI_THRESHOLD
        confidence = round(min(0.35 + magnitude * 0.15, 0.65), 3)
        signal_type = "pji_long_reversal"
    # Cross above +threshold (from below) = SHORT reversal signal
    elif prev_pji < PJI_THRESHOLD and curr_pji >= PJI_THRESHOLD:
        direction = "bearish"
        magnitude = abs(curr_pji) / PJI_THRESHOLD
        confidence = round(min(0.35 + magnitude * 0.15, 0.65), 3)
        signal_type = "pji_short_reversal"

    meta = {
        "prev_pji": round(prev_pji, 6),
        "curr_pji": round(curr_pji, 6),
        "pji_threshold": PJI_THRESHOLD,
        "pji_lookback": PJI_LOOKBACK,
        "hold_bars": HOLD_BARS,
        "signal_type": signal_type,
        "last_close": float(closes.iloc[-1]) if hasattr(closes, 'iloc') else float(closes[-1]),
    }
    return direction, confidence, meta


def main():
    import pandas as pd
    import numpy as np  # ensure available

    now_utc = datetime.now(timezone.utc)
    ts = now_utc.isoformat()

    # Check RTH window — self-zero outside RTH hours
    if not in_gc_rth_window(now_utc):
        result = {
            "ts": ts,
            "signal": "gc-pjireversal",
            "strategy": "pji",
            "direction": "neutral",
            "confidence": 0.0,
            "promoted_for_execution": False,
            "active_window": False,
            "symbol": "GC",
            "timeframe": "1h",
            "window": "13:00-18:30 UTC (GC RTH 9:00-14:30 ET)",
            "implementation_status": "HEURISTIC_UNVERIFIED",
            "tradable_signal": False,
            "researchOnly": True,
            "writesOrders": False,
            "note": "Outside GC RTH window — signal zeroed",
            "metadata": {
                "source_run": SOURCE_RUN,
                "oos_pf": OOS_PF,
                "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE}/{WALKFORWARD_FOLDS}",
                "walkforward_pct": f"{WALKFORWARD_PCT}%",
                "oos_trades": OOS_TRADES,
                "oos_win_rate_pct": OOS_WIN_RATE,
                "oos_net_points": OOS_NET_POINTS,
                "params": {"pji_lookback": PJI_LOOKBACK, "pji_threshold": PJI_THRESHOLD, "hold_bars": HOLD_BARS},
                "note": "AI Scientist verified run_p3b_pji — HEURISTIC_UNVERIFIED signal generator",
            },
        }
        # Atomic write
        tmp = SIGNAL_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2, default=str))
        tmp.rename(SIGNAL_PATH)
        print(f"GC PJI: outside RTH window ({now_utc.strftime('%H:%M')} UTC) — neutral, zeroed")
        return

    # Load bars
    df = load_gc_1h_bars()
    if df is None or len(df) < PJI_LOOKBACK + 10:
        # Write neutral signal rather than exiting non-zero
        result = {
            "ts": ts,
            "signal": "gc-pjireversal",
            "strategy": "pji",
            "direction": "neutral",
            "confidence": 0.0,
            "promoted_for_execution": False,
            "active_window": True,
            "symbol": "GC",
            "timeframe": "1h",
            "implementation_status": "HEURISTIC_UNVERIFIED",
            "tradable_signal": False,
            "researchOnly": True,
            "writesOrders": False,
            "note": "Insufficient GC 1h bar data",
            "bars_available": len(df) if df is not None else 0,
            "bars_required": PJI_LOOKBACK + 10,
            "metadata": {
                "source_run": SOURCE_RUN,
                "oos_pf": OOS_PF,
                "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE}/{WALKFORWARD_FOLDS}",
                "walkforward_pct": f"{WALKFORWARD_PCT}%",
                "oos_trades": OOS_TRADES,
                "oos_win_rate_pct": OOS_WIN_RATE,
                "oos_net_points": OOS_NET_POINTS,
                "params": {"pji_lookback": PJI_LOOKBACK, "pji_threshold": PJI_THRESHOLD, "hold_bars": HOLD_BARS},
                "note": "AI Scientist verified run_p3b_pji — HEURISTIC_UNVERIFIED signal generator",
            },
        }
        tmp = SIGNAL_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2, default=str))
        tmp.rename(SIGNAL_PATH)
        print(f"GC PJI: insufficient bars ({len(df) if df is not None else 0}) — neutral")
        return

    closes = df["close"]
    direction, confidence, meta = compute_pji_signal(closes)

    result = {
        "ts": ts,
        "signal": "gc-pjireversal",
        "strategy": "pji",
        "direction": direction,
        "confidence": confidence,
        "promoted_for_execution": False,
        "active_window": True,
        "symbol": "GC",
        "timeframe": "1h",
        "implementation_status": "HEURISTIC_UNVERIFIED",
        "tradable_signal": False,
        "researchOnly": True,
        "writesOrders": False,
        "pji_lookback": PJI_LOOKBACK,
        "pji_threshold": PJI_THRESHOLD,
        "hold_bars": HOLD_BARS,
        "signal_type": meta.get("signal_type", "none"),
        "prev_pji": meta.get("prev_pji"),
        "curr_pji": meta.get("curr_pji"),
        "last_close": meta.get("last_close"),
        "metadata": {
            "source_run": SOURCE_RUN,
            "oos_pf": OOS_PF,
            "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE}/{WALKFORWARD_FOLDS}",
            "walkforward_pct": f"{WALKFORWARD_PCT}%",
            "oos_trades": OOS_TRADES,
            "oos_win_rate_pct": OOS_WIN_RATE,
            "oos_net_points": OOS_NET_POINTS,
            "params": {"pji_lookback": PJI_LOOKBACK, "pji_threshold": PJI_THRESHOLD, "hold_bars": HOLD_BARS},
            "note": "AI Scientist verified run_p3b_pji — HEURISTIC_UNVERIFIED signal generator (not a replication)",
        },
    }

    # Atomic write: tmp + rename
    tmp = SIGNAL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2, default=str))
    tmp.rename(SIGNAL_PATH)

    print(f"GC PJI: {direction} conf={confidence:.3f} type={meta.get('signal_type')} "
          f"pji={meta.get('curr_pji')} price={meta.get('last_close')} "
          f"[HEURISTIC_UNVERIFIED]")


if __name__ == "__main__":
    main()
