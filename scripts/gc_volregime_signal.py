#!/usr/bin/env python3
"""GC wq_vol_regime 1h live signal generator — HEURISTIC_UNVERIFIED.

Strategy: Bollinger Band width squeeze/expansion regime for GC.
Detects volatility contraction (squeeze) followed by directional expansion.

Bollinger Bands (long_lookback=20, stddev_mult=short_threshold=1.2):
  - BB width = (upper - lower) / sma  (normalized)
  - Current width < avg(prior short_lookback widths) * long_threshold (0.8)
    → squeeze detected (volatility contraction)
  - Price > upper BB after squeeze → LONG expansion
  - Price < lower BB after squeeze → SHORT expansion

AI Scientist verified run (run_p3b_vol):
  - Strategy: wq_vol_regime, Symbol: GC, Timeframe: 1h
  - Data: data/free/GC-1h-2000-2026.csv
  - Params: short_lookback=10, long_lookback=20, short_threshold=1.2,
            long_threshold=0.8, hold_bars=8
  - OOS PF: 3.066, Total trades: 128, Win rate: 65.6%
  - Walkforward: 80% (4/5 folds positive)
  - Total net points: +1,894.9

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
SIGNAL_PATH = STATE / "gc-volregime-signal.latest.json"

# GC 1h data source
GC_1H_CSV = ROOT / "data" / "free" / "GC-1h-2000-2026.csv"

# Strategy parameters (from AI Scientist run_p3b_vol optimal)
SHORT_LOOKBACK = 10   # lookback for comparing prior BB widths
LONG_LOOKBACK = 20    # BB calculation window
SHORT_THRESHOLD = 1.2  # stddev multiplier for BB
LONG_THRESHOLD = 0.8   # width ratio threshold for squeeze detection
HOLD_BARS = 8

# AI Scientist verified metrics
SOURCE_RUN = "run_p3b_vol"
OOS_PF = 3.066
WALKFORWARD_FOLDS = 5
WALKFORWARD_POSITIVE = 4
WALKFORWARD_PCT = 80.0
OOS_TRADES = 128
OOS_WIN_RATE = 65.6
OOS_NET_POINTS = 1894.9

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
        print(f"GC volregime: error loading bars: {e}", file=sys.stderr)
        return None


def bb_width(close: any, index: int, lookback: int, stddev_mult: float) -> tuple[float, float, float, float] | None:
    """Compute Bollinger Band width and bands at given index.
    
    Returns (width_norm, upper, lower, sma) or None if insufficient data.
    width_norm = (upper - lower) / sma  (normalized width).
    """
    import numpy as np
    if index < lookback - 1:
        return None
    window = close.iloc[index - lookback + 1:index + 1] if hasattr(close, 'iloc') else close[index - lookback + 1:index + 1]
    sma = float(np.mean(window))
    stddev = float(np.std(window, ddof=0))
    if sma <= 0 or stddev <= 0:
        return None
    upper = sma + stddev_mult * stddev
    lower = sma - stddev_mult * stddev
    width_norm = (upper - lower) / sma
    return width_norm, upper, lower, sma


def compute_volregime_signal(closes: any, highs: any, lows: any) -> tuple[str, float, dict]:
    """Compute vol_regime signal and return (direction, confidence, meta).
    
    Logic from AI Scientist wq_vol_regime:
    1. Compute BB width at current position
    2. Compare with average of prior SHORT_LOOKBACK widths
    3. If current_width < avg_width * LONG_THRESHOLD → squeeze detected
    4. If squeezed and price > upper BB → LONG (bullish expansion)
    5. If squeezed and price < lower BB → SHORT (bearish expansion)
    """
    import numpy as np
    n = len(closes)
    warmup = LONG_LOOKBACK + SHORT_LOOKBACK
    if n < warmup + 2:
        return "neutral", 0.0, {"reason": "insufficient bars"}

    # Check the most recent bar for a squeeze/expansion signal
    pos = n - 1  # latest bar
    current = bb_width(closes, pos, LONG_LOOKBACK, SHORT_THRESHOLD)
    if current is None:
        return "neutral", 0.0, {"reason": "cannot compute BB at latest bar"}

    current_width, upper, lower, sma = current
    last_close = float(closes.iloc[pos]) if hasattr(closes, 'iloc') else float(closes[pos])

    # Gather prior widths
    prior_widths = []
    for j in range(1, SHORT_LOOKBACK + 1):
        p = pos - j
        if p >= LONG_LOOKBACK:
            val = bb_width(closes, p, LONG_LOOKBACK, SHORT_THRESHOLD)
            if val is not None:
                prior_widths.append(val[0])
    if not prior_widths:
        return "neutral", 0.0, {"reason": "no prior BB widths"}

    avg_width = float(np.mean(prior_widths))
    width_ratio = current_width / avg_width if avg_width > 0 else 999.0

    direction = "neutral"
    confidence = 0.0
    signal_type = "none"

    # Squeeze detection: current width significantly below average
    is_squeeze = avg_width > 0 and current_width < avg_width * LONG_THRESHOLD

    if is_squeeze:
        # Squeeze detected — check expansion direction
        if last_close > upper:
            squeeze_magnitude = 1.0 - width_ratio  # 0 = no squeeze, closer to 1 = extreme
            confidence = round(min(0.4 + squeeze_magnitude * 0.35, 0.75), 3)
            direction = "bullish"
            signal_type = "squeeze_expansion_long"
        elif last_close < lower:
            squeeze_magnitude = 1.0 - width_ratio
            confidence = round(min(0.4 + squeeze_magnitude * 0.35, 0.75), 3)
            direction = "bearish"
            signal_type = "squeeze_expansion_short"
        else:
            # Squeeze but no breakout yet — monitor
            confidence = round(min(width_ratio * 0.3, 0.25), 3)
            direction = "neutral"
            signal_type = "squeeze_forming"
    else:
        # No squeeze — check if we're in a strong trend regime
        if width_ratio > 1.5 and last_close > upper:
            # Wide bands, price above upper → strong uptrend (lower confidence for vol_regime)
            confidence = round(min((width_ratio - 1.0) * 0.15, 0.3), 3)
            direction = "bullish"
            signal_type = "high_vol_trend_long"
        elif width_ratio > 1.5 and last_close < lower:
            confidence = round(min((width_ratio - 1.0) * 0.15, 0.3), 3)
            direction = "bearish"
            signal_type = "high_vol_trend_short"

    meta = {
        "current_bb_width": round(current_width, 6),
        "avg_prior_width": round(avg_width, 6),
        "width_ratio": round(width_ratio, 4),
        "upper_bb": round(upper, 2),
        "lower_bb": round(lower, 2),
        "sma": round(sma, 2),
        "is_squeeze": is_squeeze,
        "short_lookback": SHORT_LOOKBACK,
        "long_lookback": LONG_LOOKBACK,
        "short_threshold": SHORT_THRESHOLD,
        "long_threshold": LONG_THRESHOLD,
        "hold_bars": HOLD_BARS,
        "signal_type": signal_type,
        "last_close": last_close,
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
            "signal": "gc-volregime",
            "strategy": "wq_vol_regime",
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
                "params": {
                    "short_lookback": SHORT_LOOKBACK,
                    "long_lookback": LONG_LOOKBACK,
                    "short_threshold": SHORT_THRESHOLD,
                    "long_threshold": LONG_THRESHOLD,
                    "hold_bars": HOLD_BARS,
                },
                "note": "AI Scientist verified run_p3b_vol — HEURISTIC_UNVERIFIED signal generator",
            },
        }
        # Atomic write
        tmp = SIGNAL_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2, default=str))
        tmp.rename(SIGNAL_PATH)
        print(f"GC volregime: outside RTH window ({now_utc.strftime('%H:%M')} UTC) — neutral, zeroed")
        return

    # Load bars
    df = load_gc_1h_bars()
    min_bars = LONG_LOOKBACK + SHORT_LOOKBACK + 2
    if df is None or len(df) < min_bars:
        # Write neutral signal rather than exiting non-zero
        result = {
            "ts": ts,
            "signal": "gc-volregime",
            "strategy": "wq_vol_regime",
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
            "bars_required": min_bars,
            "metadata": {
                "source_run": SOURCE_RUN,
                "oos_pf": OOS_PF,
                "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE}/{WALKFORWARD_FOLDS}",
                "walkforward_pct": f"{WALKFORWARD_PCT}%",
                "oos_trades": OOS_TRADES,
                "oos_win_rate_pct": OOS_WIN_RATE,
                "oos_net_points": OOS_NET_POINTS,
                "params": {
                    "short_lookback": SHORT_LOOKBACK,
                    "long_lookback": LONG_LOOKBACK,
                    "short_threshold": SHORT_THRESHOLD,
                    "long_threshold": LONG_THRESHOLD,
                    "hold_bars": HOLD_BARS,
                },
                "note": "AI Scientist verified run_p3b_vol — HEURISTIC_UNVERIFIED signal generator",
            },
        }
        tmp = SIGNAL_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2, default=str))
        tmp.rename(SIGNAL_PATH)
        print(f"GC volregime: insufficient bars ({len(df) if df is not None else 0}) — neutral")
        return

    closes = df["close"]
    highs = df["high"]
    lows = df["low"]
    direction, confidence, meta = compute_volregime_signal(closes, highs, lows)

    result = {
        "ts": ts,
        "signal": "gc-volregime",
        "strategy": "wq_vol_regime",
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
        "short_lookback": SHORT_LOOKBACK,
        "long_lookback": LONG_LOOKBACK,
        "short_threshold": SHORT_THRESHOLD,
        "long_threshold": LONG_THRESHOLD,
        "hold_bars": HOLD_BARS,
        "signal_type": meta.get("signal_type", "none"),
        "is_squeeze": meta.get("is_squeeze"),
        "current_bb_width": meta.get("current_bb_width"),
        "avg_prior_width": meta.get("avg_prior_width"),
        "width_ratio": meta.get("width_ratio"),
        "upper_bb": meta.get("upper_bb"),
        "lower_bb": meta.get("lower_bb"),
        "sma": meta.get("sma"),
        "last_close": meta.get("last_close"),
        "metadata": {
            "source_run": SOURCE_RUN,
            "oos_pf": OOS_PF,
            "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE}/{WALKFORWARD_FOLDS}",
            "walkforward_pct": f"{WALKFORWARD_PCT}%",
            "oos_trades": OOS_TRADES,
            "oos_win_rate_pct": OOS_WIN_RATE,
            "oos_net_points": OOS_NET_POINTS,
            "params": {
                "short_lookback": SHORT_LOOKBACK,
                "long_lookback": LONG_LOOKBACK,
                "short_threshold": SHORT_THRESHOLD,
                "long_threshold": LONG_THRESHOLD,
                "hold_bars": HOLD_BARS,
            },
            "note": "AI Scientist verified run_p3b_vol — HEURISTIC_UNVERIFIED signal generator (not a replication)",
        },
    }

    # Atomic write: tmp + rename
    tmp = SIGNAL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2, default=str))
    tmp.rename(SIGNAL_PATH)

    print(f"GC volregime: {direction} conf={confidence:.3f} squeeze={meta.get('is_squeeze')} "
          f"ratio={meta.get('width_ratio')} price={meta.get('last_close')} "
          f"BB=[{meta.get('lower_bb')},{meta.get('upper_bb')}] "
          f"[HEURISTIC_UNVERIFIED]")


if __name__ == "__main__":
    main()
