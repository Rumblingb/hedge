#!/usr/bin/env python3
"""Asia session overnight signal for NQ — HEURISTIC_UNVERIFIED.

Strategy: Overnight mean-reversion anchored to prior RTH session range.
- Active window: 21:30-06:30 UTC (Sun 21:30 Mon-Fri 21:30 → next morning 06:30)
- Prior RTH range: 14:30-21:00 UTC high/low/close/ATR
- Mean reversion: price > prior_high + 0.5*ATR → bearish, < prior_low - 0.5*ATR → bullish
- Trend follow: price holding > prior_high for 3+ bars → bullish continuation
- VWAP from 21:00 UTC (Globex overnight open reference)
- Confidence derived from extension magnitude / ATR

No AI Scientist walkforward — HEURISTIC_UNVERIFIED.
promoted_for_execution=False, tradable_signal=False always.
"""
import json, os, sys
from datetime import datetime, timezone, time, timedelta
from pathlib import Path

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
BAR_ARCHIVE = ROOT / ".rumbling-hedge/research/topstep-readonly-bars"
SIGNAL_PATH = STATE / "asia-session-signal.latest.json"
NQ_CSV = BAR_ARCHIVE / "NQ-1m-topstep-readonly.csv"

ASIA_START_UTC = time(21, 30)
ASIA_END_UTC = time(6, 30)
RTH_START_UTC = time(14, 30)
RTH_END_UTC = time(21, 0)

MR_EXTENSION = 0.5   # ATR multiples beyond prior range for mean-reversion signal
TREND_EXTENSION = 0.25  # ATR multiples above range for trend-follow
TREND_CONFIRM_BARS = 3


def in_asia_signal_window(now_utc=None):
    t = (now_utc or datetime.now(timezone.utc)).time()
    # Overnight: 21:30+ or <06:30
    return t >= ASIA_START_UTC or t < ASIA_END_UTC


def load_bars():
    if not NQ_CSV.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_csv(NQ_CSV, parse_dates=["ts"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        return df.sort_values("ts").reset_index(drop=True)
    except Exception:
        return None


def compute_atr(bars, n=14):
    import numpy as np
    if len(bars) < n + 1:
        return float(bars["high"].iloc[-1] - bars["low"].iloc[-1]) or 20.0
    h, l, c = bars["high"].values, bars["low"].values, bars["close"].values
    tr = np.maximum(h[1:] - l[1:],
         np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-n:]))


def get_prior_rth(df, now_utc):
    """Return prior RTH session stats: high, low, close, atr."""
    import numpy as np
    import pandas as pd

    # Prior RTH = yesterday's 14:30-21:00 UTC (or most recent available)
    # Look back up to 3 days
    for delta_days in range(1, 4):
        ref = now_utc - timedelta(days=delta_days)
        rth = df[
            (df["ts"].dt.date == ref.date()) &
            (df["ts"].dt.hour >= 14) &
            ~((df["ts"].dt.hour == 14) & (df["ts"].dt.minute < 30))
        ]
        if len(rth) >= 20:
            atr = compute_atr(rth)
            return {
                "high": float(rth["high"].max()),
                "low": float(rth["low"].min()),
                "close": float(rth["close"].iloc[-1]),
                "atr": atr,
                "bars": len(rth),
                "date": ref.date().isoformat(),
            }
    return None


def session_vwap(df, session_start_ts):
    session = df[df["ts"] >= session_start_ts].copy()
    if len(session) == 0:
        return None
    typical = (session["high"] + session["low"] + session["close"]) / 3.0
    vol = session["volume"].replace(0, 1)
    vwap_val = float((typical * vol).sum() / vol.sum())
    return vwap_val


def compute_signal(df, now_utc):
    import numpy as np
    import pandas as pd

    prior_rth = get_prior_rth(df, now_utc)
    if prior_rth is None:
        return "neutral", 0.0, {}

    rth_high = prior_rth["high"]
    rth_low = prior_rth["low"]
    rth_close = prior_rth["close"]
    atr = prior_rth["atr"]

    # Current overnight session bars
    # Session starts at 21:00 UTC on the prior day
    if now_utc.time() < ASIA_END_UTC:
        # Early morning — session started yesterday at 21:00
        session_date = now_utc.date() - timedelta(days=1)
    else:
        session_date = now_utc.date()

    session_start_ts = pd.Timestamp(
        year=session_date.year, month=session_date.month, day=session_date.day,
        hour=21, minute=0, tzinfo=timezone.utc
    )
    overnight = df[df["ts"] >= session_start_ts]
    if len(overnight) < 5:
        return "neutral", 0.0, prior_rth

    last_close = float(overnight["close"].iloc[-1])
    recent = overnight.tail(TREND_CONFIRM_BARS)

    vwap = session_vwap(df, session_start_ts)

    direction = "neutral"
    confidence = 0.0
    signal_type = "none"

    upper_mr_level = rth_high + MR_EXTENSION * atr
    lower_mr_level = rth_low - MR_EXTENSION * atr
    upper_trend_level = rth_high + TREND_EXTENSION * atr
    lower_trend_level = rth_low - TREND_EXTENSION * atr

    # Mean reversion: price has extended beyond prior range + buffer
    if last_close > upper_mr_level:
        extension = (last_close - rth_high) / atr
        confidence = round(min(0.25 + extension * 0.2, 0.55), 3)
        direction = "bearish"
        signal_type = "mean_reversion"

    elif last_close < lower_mr_level:
        extension = (rth_low - last_close) / atr
        confidence = round(min(0.25 + extension * 0.2, 0.55), 3)
        direction = "bullish"
        signal_type = "mean_reversion"

    # Trend follow: holding above/below prior range for N bars
    elif all(recent["close"] > upper_trend_level):
        breakout = (last_close - rth_high) / atr
        confidence = round(min(0.3 + breakout * 0.15, 0.5), 3)
        direction = "bullish"
        signal_type = "overnight_trend"

    elif all(recent["close"] < lower_trend_level):
        breakout = (rth_low - last_close) / atr
        confidence = round(min(0.3 + breakout * 0.15, 0.5), 3)
        direction = "bearish"
        signal_type = "overnight_trend"

    meta = {
        **prior_rth,
        "last_close": round(last_close, 2),
        "upper_mr": round(upper_mr_level, 2),
        "lower_mr": round(lower_mr_level, 2),
        "vwap": round(vwap, 2) if vwap else None,
        "signal_type": signal_type,
        "overnight_bars": len(overnight),
    }
    return direction, confidence, meta


def main():
    import numpy  # ensure available
    now_utc = datetime.now(timezone.utc)
    ts = now_utc.isoformat()

    if not in_asia_signal_window(now_utc):
        result = {
            "ts": ts, "symbol": "NQ", "session": "asia",
            "direction": "neutral", "confidence": 0.0,
            "active_window": False,
            "window": "21:30-06:30 UTC",
            "note": "outside Asia session window — signal zeroed",
            "promoted_for_execution": False, "tradable_signal": False,
            "implementation_status": "HEURISTIC_UNVERIFIED",
            "researchOnly": True, "writesOrders": False,
        }
        SIGNAL_PATH.write_text(json.dumps(result, indent=2))
        print(f"NQ asia: outside window ({now_utc.strftime('%H:%M')} UTC) — neutral")
        return

    df = load_bars()
    if df is None or len(df) < 30:
        print("NQ asia: no bar data — exiting without writing signal", file=sys.stderr)
        sys.exit(1)

    direction, confidence, meta = compute_signal(df, now_utc)

    result = {
        "ts": ts, "symbol": "NQ", "session": "asia",
        "direction": direction, "confidence": confidence,
        "active_window": True,
        "window": "21:30-06:30 UTC",
        "prior_rth_high": meta.get("high"),
        "prior_rth_low": meta.get("low"),
        "prior_rth_close": meta.get("close"),
        "prior_rth_atr": round(meta.get("atr", 0), 2) if meta.get("atr") else None,
        "upper_mr_level": meta.get("upper_mr"),
        "lower_mr_level": meta.get("lower_mr"),
        "vwap": meta.get("vwap"),
        "last_close": meta.get("last_close"),
        "signal_type": meta.get("signal_type", "none"),
        "implementation_status": "HEURISTIC_UNVERIFIED",
        "promoted_for_execution": False,
        "tradable_signal": False,
        "researchOnly": True,
        "writesOrders": False,
        "note": "Asia overnight — no AI Scientist OOS validation. Not in PROMOTION_REQUIRED.",
    }
    SIGNAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"NQ asia: {direction} conf={confidence:.3f} type={meta.get('signal_type')} "
          f"price={meta.get('last_close')} rth=[{meta.get('high')},{meta.get('low')}]")


if __name__ == "__main__":
    main()
