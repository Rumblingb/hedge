#!/usr/bin/env python3
"""London session ORB signal for NQ — HEURISTIC_UNVERIFIED.

Strategy: Opening Range Breakout anchored to London open (07:00 UTC / 03:00 ET).
- ORB formation: 07:00-07:15 UTC (15 x 1m bars)
- Signal window: 07:15-12:00 UTC only (zero-out outside window)
- Long: close > ORB high AND 2+ consecutive bars above range
- Short: close < ORB low AND 2+ consecutive bars below range
- VWAP filter: reset at 07:00 UTC; signal aligns with VWAP side
- Confidence scales with breakout magnitude / ATR

No AI Scientist walkforward — HEURISTIC_UNVERIFIED.
promoted_for_execution=False, tradable_signal=False always.
Add to PROMOTION_REQUIRED only after AI Scientist OOS validation.
"""
import json, os, sys
from datetime import datetime, timezone, time, date
from pathlib import Path

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
BAR_ARCHIVE = ROOT / ".rumbling-hedge/research/topstep-readonly-bars"
SIGNAL_PATH = STATE / "london-orb-signal.latest.json"
NQ_CSV = BAR_ARCHIVE / "NQ-1m-topstep-readonly.csv"

LONDON_OPEN_UTC = time(7, 0)
LONDON_SIGNAL_START_UTC = time(7, 15)  # after ORB forms
LONDON_CLOSE_UTC = time(12, 0)
ORB_BARS = 15  # 07:00-07:15 UTC
CONFIRM_BARS = 2


def in_london_signal_window(now_utc=None):
    t = (now_utc or datetime.now(timezone.utc)).time()
    return LONDON_SIGNAL_START_UTC <= t < LONDON_CLOSE_UTC


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


def session_vwap(bars_df, session_start):
    """Cumulative VWAP from session_start forward."""
    import numpy as np
    session = bars_df[bars_df["ts"] >= session_start].copy()
    if len(session) == 0:
        return None
    typical = (session["high"] + session["low"] + session["close"]) / 3.0
    vol = session["volume"].replace(0, 1)
    cum_pv = (typical * vol).cumsum()
    cum_v = vol.cumsum()
    session = session.copy()
    session["vwap"] = cum_pv.values / cum_v.values
    return session


def compute_atr(bars_df, n=14):
    import numpy as np
    if len(bars_df) < n + 1:
        return bars_df["high"].iloc[-1] - bars_df["low"].iloc[-1]
    h = bars_df["high"].values
    l = bars_df["low"].values
    c = bars_df["close"].values
    tr = np.maximum(h[1:] - l[1:],
         np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-n:]))


def compute_signal(df, now_utc):
    import pandas as pd
    today = now_utc.date()

    # Find today's London open bars (07:00-07:15 UTC)
    today_bars = df[df["ts"].dt.date == today]
    orb_bars = today_bars[
        (today_bars["ts"].dt.hour == 7) & (today_bars["ts"].dt.minute < ORB_BARS)
    ]

    if len(orb_bars) < ORB_BARS:
        # Try prior trading day
        trading_days = sorted(df["ts"].dt.date.unique())
        idx = trading_days.index(today) if today in trading_days else -1
        if idx > 0:
            prev_day = trading_days[idx - 1]
            prev_bars = df[df["ts"].dt.date == prev_day]
            orb_bars = prev_bars[
                (prev_bars["ts"].dt.hour == 7) & (prev_bars["ts"].dt.minute < ORB_BARS)
            ]
        if len(orb_bars) < 5:
            return "neutral", 0.0, None, None, None

    orb_high = float(orb_bars["high"].max())
    orb_low = float(orb_bars["low"].min())
    orb_range = orb_high - orb_low

    # Post-ORB bars for confirmation (today only)
    post_orb = today_bars[today_bars["ts"].dt.hour >= 7][len(orb_bars):]
    if len(post_orb) < CONFIRM_BARS:
        return "neutral", 0.0, orb_high, orb_low, None

    recent = post_orb.tail(CONFIRM_BARS)
    last_close = float(post_orb["close"].iloc[-1])

    # VWAP from London open
    london_open_ts = pd.Timestamp(year=today.year, month=today.month,
                                   day=today.day, hour=7, minute=0,
                                   tzinfo=timezone.utc)
    vsdf = session_vwap(df, london_open_ts)
    vwap_now = float(vsdf["vwap"].iloc[-1]) if vsdf is not None and len(vsdf) > 0 else None

    # ATR from recent bars
    atr = compute_atr(df.tail(60))
    if atr <= 0:
        atr = orb_range or 20.0

    # Direction logic
    above_count = int((recent["close"] > orb_high).sum())
    below_count = int((recent["close"] < orb_low).sum())

    direction = "neutral"
    confidence = 0.0

    if above_count >= CONFIRM_BARS:
        breakout_mag = (last_close - orb_high) / atr
        conf = min(0.35 + breakout_mag * 0.3, 0.75)
        # VWAP filter: prefer long when price > VWAP
        if vwap_now is None or last_close >= vwap_now:
            direction = "bullish"
            confidence = round(conf, 3)
        else:
            # VWAP against us — reduced confidence
            direction = "bullish"
            confidence = round(conf * 0.5, 3)

    elif below_count >= CONFIRM_BARS:
        breakout_mag = (orb_low - last_close) / atr
        conf = min(0.35 + breakout_mag * 0.3, 0.75)
        if vwap_now is None or last_close <= vwap_now:
            direction = "bearish"
            confidence = round(conf, 3)
        else:
            direction = "bearish"
            confidence = round(conf * 0.5, 3)

    return direction, confidence, orb_high, orb_low, vwap_now


def main():
    now_utc = datetime.now(timezone.utc)
    ts = now_utc.isoformat()

    if not in_london_signal_window(now_utc):
        result = {
            "ts": ts, "symbol": "NQ", "session": "london",
            "direction": "neutral", "confidence": 0.0,
            "active_window": False,
            "window": "07:15-12:00 UTC",
            "note": "outside London session window — signal zeroed",
            "promoted_for_execution": False, "tradable_signal": False,
            "implementation_status": "HEURISTIC_UNVERIFIED",
            "researchOnly": True, "writesOrders": False,
        }
        SIGNAL_PATH.write_text(json.dumps(result, indent=2))
        print(f"NQ london-orb: outside window ({now_utc.strftime('%H:%M')} UTC) — neutral")
        return

    df = load_bars()
    if df is None or len(df) < 30:
        print("NQ london-orb: no bar data — exiting without writing signal", file=sys.stderr)
        sys.exit(1)

    direction, confidence, orb_high, orb_low, vwap = compute_signal(df, now_utc)

    result = {
        "ts": ts, "symbol": "NQ", "session": "london",
        "direction": direction, "confidence": confidence,
        "orb_high": round(orb_high, 2) if orb_high else None,
        "orb_low": round(orb_low, 2) if orb_low else None,
        "vwap": round(vwap, 2) if vwap else None,
        "active_window": True,
        "window": "07:15-12:00 UTC",
        "orb_formation_bars": ORB_BARS,
        "confirm_bars": CONFIRM_BARS,
        "implementation_status": "HEURISTIC_UNVERIFIED",
        "promoted_for_execution": False,
        "tradable_signal": False,
        "researchOnly": True,
        "writesOrders": False,
        "note": "London ORB — no AI Scientist OOS validation yet. Not in PROMOTION_REQUIRED.",
    }
    SIGNAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"NQ london-orb: {direction} conf={confidence:.3f} ORB=[{orb_high},{orb_low}] vwap={vwap}")


if __name__ == "__main__":
    main()
