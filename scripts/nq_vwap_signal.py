#!/usr/bin/env python3
"""nq_vwap_signal.py — NQ VWAP 15m live signal generator (HEURISTIC_UNVERIFIED).

Strategy: Cumulative VWAP mean reversion on 15m NQ futures.
- Entry: price deviates > vwap_threshold x ATR from cumulative session VWAP
- Direction: LONG when deviation is positive (price above VWAP), SHORT when negative
- Exit: after hold_bars or when price crosses VWAP

AI Scientist verified runs:
  run_vwap_postfix:
    - Strategy: vwap, Symbol: NQ, Timeframe: 15m
    - OOS PF: 2.488, Trades: 77, WR: 57.1%, Net: +1,460 pts
    - Walkforward: 60% positive folds (3/5)
  run_it_vwap_hb16:
    - OOS PF: 1.904, Trades: 94, WR: 55.3%, WF: 80% positive folds (4/5)

HEURISTIC_UNVERIFIED — promoted_for_execution=False.
Contributes to arbitration consensus but cannot trigger trades alone.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, time, date
from pathlib import Path
from typing import Any

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge" / "state"
SIGNAL_PATH = STATE / "nq-vwaptrend-signal.latest.json"

# Data sources (tried in order: most recent first)
DATA_GLOBS = [
    ROOT / "data" / "free" / "NQ-15m-5d.csv",
    ROOT / "data" / "free" / "NQ-15m-60d.csv",
    ROOT / "data" / "free" / "NQ-2022-2025-15m.csv",
]

# Strategy parameters (from AI Scientist run_vwap_postfix optimal config)
VWAP_THRESHOLD = 2.0        # entry threshold in ATR units
HOLD_BARS = 16              # max hold period (bars)
OPENING_MINUTES = 30        # skip first N minutes of RTH (= 2 bars at 15m)
COST_POINTS = 1.5           # estimated round-turn cost
ATR_PERIOD = 14             # ATR computation period
TICK_SIZE = 0.25            # NQ tick size

# AI Scientist verified metrics (primary run: run_vwap_postfix, PF 2.488)
SOURCE_RUN_PRIMARY = "run_vwap_postfix"
SOURCE_RUN_SECONDARY = "run_it_vwap_hb16"

# Primary run metrics
OOS_PF = 2.488
OOS_TRADES = 77
OOS_WIN_RATE = 57.1
OOS_NET_POINTS = 1460.0
WALKFORWARD_POSITIVE = 3
WALKFORWARD_FOLDS = 5
WALKFORWARD_PCT = 60.0

# Secondary run metrics
OOS_PF2 = 1.904
OOS_TRADES2 = 94
OOS_WIN_RATE2 = 55.3
OOS_NET_POINTS2 = 1236.0
WALKFORWARD_POSITIVE2 = 4
WALKFORWARD_PCT2 = 80.0

# NQ RTH window: 9:30-16:00 ET
# During EDT (summer): 13:30-20:00 UTC
# During EST (winter): 14:30-21:00 UTC
# Task specifies 14:30-21:00 BST (BST = UTC+1 → 13:30-20:00 UTC)
NQ_RTH_START_UTC = time(13, 30)
NQ_RTH_END_UTC = time(20, 0)


def in_nq_rth_window(now_utc: datetime | None = None) -> bool:
    """Check if current time falls within NQ RTH hours (13:30-20:00 UTC)."""
    t = (now_utc or datetime.now(timezone.utc)).time()
    return NQ_RTH_START_UTC <= t < NQ_RTH_END_UTC


def find_data_file() -> Path | None:
    """Find the most recent NQ 15m CSV data file."""
    for path in DATA_GLOBS:
        if path.exists():
            return path
    # Fallback: glob for any NQ-15m-*.csv
    for p in sorted((ROOT / "data" / "free").glob("NQ-15m-*.csv"), reverse=True):
        return p
    return None


def load_nq_15m_bars() -> Any:
    """Load NQ 15m bars from the best available data source."""
    import pandas as pd

    data_file = find_data_file()
    if data_file is None:
        print(f"NQ VWAP: no NQ 15m data file found", file=sys.stderr)
        return None

    try:
        df = pd.read_csv(data_file, parse_dates=["ts"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        if "symbol" in df.columns:
            df = df[df["symbol"] == "NQ"].copy()
        df = df.sort_values("ts").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"NQ VWAP: error loading bars: {e}", file=sys.stderr)
        return None


def compute_atr(df: Any, period: int = 14) -> Any:
    """Compute ATR on a price DataFrame with high/low/close columns."""
    import pandas as pd
    tr = pd.concat([
        abs(df["high"] - df["low"]),
        abs(df["high"] - df["close"].shift(1)),
        abs(df["low"] - df["close"].shift(1)),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def generate_signal() -> dict[str, Any] | None:
    """Generate a VWAP mean-reversion signal from today's NQ 15m bars.

    Returns:
        Signal dict with side, entry, target (VWAP), etc., or None if no signal.
    """
    import pandas as pd
    import numpy as np

    df = load_nq_15m_bars()
    if df is None or len(df) < 100:
        print(f"NQ VWAP: insufficient historical bars ({len(df) if df is not None else 0})", file=sys.stderr)
        return None

    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()

    # Determine session date in ET
    # NQ RTH starts at 9:30 ET = 13:30 UTC (EDT) / 14:30 UTC (EST)
    # If current time is before RTH open in UTC, session belongs to yesterday
    et_now = now_utc
    # Simple heuristic: session day = today if after RTH open UTC, else yesterday
    if now_utc.time() < NQ_RTH_START_UTC:
        session_date = (now_utc - pd.Timedelta(days=1)).date()
    else:
        session_date = now_utc.date()

    # Filter to today's RTH session bars
    # RTH bars: timestamps between session open (13:30 UTC / 14:30 UTC) and RTH close (20:00 / 21:00 UTC)
    session_open_utc = pd.Timestamp(session_date, tz="UTC") + pd.Timedelta(
        hours=NQ_RTH_START_UTC.hour, minutes=NQ_RTH_START_UTC.minute
    )
    session_close_utc = pd.Timestamp(session_date, tz="UTC") + pd.Timedelta(
        hours=NQ_RTH_END_UTC.hour, minutes=NQ_RTH_END_UTC.minute
    )

    # Get all bars for this session (includes bars starting within window)
    session_bars = df[
        (df["ts"] >= session_open_utc) & (df["ts"] < session_close_utc)
    ].copy()

    if session_bars.empty:
        print(f"NQ VWAP: no RTH bars for session date {session_date}")
        return None

    # Compute cumulative VWAP from session open
    # VWAP = Σ(price * volume) / Σ(volume)
    # Using typical price = (high + low + close) / 3
    session_bars["typical"] = (session_bars["high"] + session_bars["low"] + session_bars["close"]) / 3.0
    session_bars["cum_pv"] = (session_bars["typical"] * session_bars["volume"]).cumsum()
    session_bars["cum_vol"] = session_bars["volume"].cumsum()
    session_bars["vwap"] = session_bars["cum_pv"] / session_bars["cum_vol"]

    # Compute ATR on the full dataset (for stability, use trailing 14 bars)
    full_atr = compute_atr(df, ATR_PERIOD)

    # Map ATR to session bars (use last known ATR value before each session bar)
    last_atr = None
    session_bars["atr"] = np.nan
    for idx in session_bars.index:
        bar_ts = session_bars.loc[idx, "ts"]
        # ATR at this timestamp from the full dataset
        prior = full_atr[full_atr.index <= idx]
        if not prior.empty and not pd.isna(prior.iloc[-1]):
            last_atr = float(prior.iloc[-1])
        if last_atr is not None:
            session_bars.at[idx, "atr"] = last_atr

    # Compute deviation = (close - vwap) / atr
    session_bars["deviation"] = (session_bars["close"] - session_bars["vwap"]) / session_bars["atr"]

    # Skip opening range (first 30 min = 2 bars of 15m)
    opening_bars_count = max(1, OPENING_MINUTES // 15)
    if len(session_bars) <= opening_bars_count:
        print(f"NQ VWAP: session has {len(session_bars)} bars, need > {opening_bars_count} to skip opening range")
        return None

    tradable_bars = session_bars.iloc[opening_bars_count:].copy()
    if tradable_bars.empty:
        return None

    # Latest completed bar
    latest = tradable_bars.iloc[-1]
    curr_dev = float(latest["deviation"]) if not pd.isna(latest["deviation"]) else 0.0
    curr_vwap = float(latest["vwap"])
    curr_atr = float(latest["atr"]) if not pd.isna(latest["atr"]) else 0.0
    curr_close = float(latest["close"])
    curr_ts = latest["ts"]

    print(f"NQ VWAP: latest bar @ {curr_ts} close={curr_close:.2f} vwap={curr_vwap:.2f} "
          f"dev={curr_dev:.3f} atr={curr_atr:.2f}")

    # Skip if deviation is NaN or ATR is 0
    if pd.isna(latest["deviation"]) or curr_atr <= 0:
        print(f"NQ VWAP: deviation NaN or ATR=0 — no signal")
        return None

    # Check for entry signal
    direction = "neutral"
    entry_price = None
    reason = ""

    if curr_dev > VWAP_THRESHOLD:
        # Price extended above VWAP — LONG momentum signal
        # (Strategy follows the break from VWAP, exits on reversion to VWAP)
        direction = "long"
        entry_price = curr_close
        deviation_atr = curr_dev
        reason = f"vwap_long_deviation_{curr_dev:.2f}xATR"
    elif curr_dev < -VWAP_THRESHOLD:
        # Price extended below VWAP — SHORT momentum signal
        direction = "short"
        entry_price = curr_close
        deviation_atr = abs(curr_dev)
        reason = f"vwap_short_deviation_{curr_dev:.2f}xATR"
    else:
        print(f"NQ VWAP: deviation {curr_dev:.3f} within threshold ±{VWAP_THRESHOLD} — no signal")
        return None

    # Build signal
    signal = {
        "side": direction,
        "entry": entry_price,
        "target": curr_vwap,  # VWAP is the reversion target
        "stop": None,          # No hard stop (stop_loss_atr = 0.0 in optimal config)
        "vwap": curr_vwap,
        "atr": round(curr_atr, 2),
        "deviation": round(curr_dev, 4),
        "threshold": VWAP_THRESHOLD,
        "hold_bars": HOLD_BARS,
        "cost_points": COST_POINTS,
        "reason": reason,
        "price_now": curr_close,
    }

    return signal


def write_result(result: dict[str, Any]) -> None:
    """Atomically write signal payload to .rumbling-hedge/state."""
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = SIGNAL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2, default=str))
    tmp.rename(SIGNAL_PATH)


def main() -> None:
    import pandas as pd
    import numpy as np  # ensure available

    now_utc = datetime.now(timezone.utc)
    ts = now_utc.isoformat()

    # ── Outside RTH: self-zero ──────────────────────────────────────────
    if not in_nq_rth_window(now_utc):
        result = {
            "ts": ts,
            "signal": "nq-vwaptrend",
            "strategy": "vwap",
            "direction": "neutral",
            "confidence": 0.0,
            "promoted_for_execution": False,
            "active_window": False,
            "symbol": "NQ",
            "timeframe": "15m",
            "window": "13:30-20:00 UTC (NQ RTH 9:30-16:00 ET / 14:30-21:00 BST)",
            "implementation_status": "HEURISTIC_UNVERIFIED",
            "tradable_signal": False,
            "researchOnly": True,
            "writesOrders": False,
            "note": "Outside NQ RTH window — signal zeroed",
            "metadata": {
                "source_run": f"{SOURCE_RUN_PRIMARY} (PF {OOS_PF}) + {SOURCE_RUN_SECONDARY} (PF {OOS_PF2})",
                "primary_run": {
                    "run": SOURCE_RUN_PRIMARY,
                    "oos_pf": OOS_PF,
                    "oos_trades": OOS_TRADES,
                    "oos_win_rate_pct": OOS_WIN_RATE,
                    "oos_net_points": OOS_NET_POINTS,
                    "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE}/{WALKFORWARD_FOLDS}",
                    "walkforward_pct": f"{WALKFORWARD_PCT}%",
                },
                "secondary_run": {
                    "run": SOURCE_RUN_SECONDARY,
                    "oos_pf": OOS_PF2,
                    "oos_trades": OOS_TRADES2,
                    "oos_win_rate_pct": OOS_WIN_RATE2,
                    "oos_net_points": OOS_NET_POINTS2,
                    "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE2}/{WALKFORWARD_FOLDS}",
                    "walkforward_pct": f"{WALKFORWARD_PCT2}%",
                },
                "params": {
                    "vwap_threshold": VWAP_THRESHOLD,
                    "hold_bars": HOLD_BARS,
                    "opening_minutes": OPENING_MINUTES,
                    "atr_period": ATR_PERIOD,
                    "cost_points": COST_POINTS,
                },
                "note": "AI Scientist verified runs — HEURISTIC_UNVERIFIED signal generator",
            },
        }
        write_result(result)
        print(f"NQ VWAP: outside RTH window ({now_utc.strftime('%H:%M')} UTC) — neutral, zeroed")
        return

    # ── Generate signal from bars ───────────────────────────────────────
    signal = generate_signal()
    if signal is None:
        # Write neutral signal rather than exiting non-zero
        result = {
            "ts": ts,
            "signal": "nq-vwaptrend",
            "strategy": "vwap",
            "direction": "neutral",
            "confidence": 0.0,
            "promoted_for_execution": False,
            "active_window": True,
            "symbol": "NQ",
            "timeframe": "15m",
            "implementation_status": "HEURISTIC_UNVERIFIED",
            "tradable_signal": False,
            "researchOnly": True,
            "writesOrders": False,
            "note": "No VWAP signal generated (deviation within threshold or insufficient data)",
            "metadata": {
                "source_run": f"{SOURCE_RUN_PRIMARY} (PF {OOS_PF}) + {SOURCE_RUN_SECONDARY} (PF {OOS_PF2})",
                "primary_run": {
                    "run": SOURCE_RUN_PRIMARY,
                    "oos_pf": OOS_PF,
                    "oos_trades": OOS_TRADES,
                    "oos_win_rate_pct": OOS_WIN_RATE,
                    "oos_net_points": OOS_NET_POINTS,
                    "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE}/{WALKFORWARD_FOLDS}",
                    "walkforward_pct": f"{WALKFORWARD_PCT}%",
                },
                "secondary_run": {
                    "run": SOURCE_RUN_SECONDARY,
                    "oos_pf": OOS_PF2,
                    "oos_trades": OOS_TRADES2,
                    "oos_win_rate_pct": OOS_WIN_RATE2,
                    "oos_net_points": OOS_NET_POINTS2,
                    "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE2}/{WALKFORWARD_FOLDS}",
                    "walkforward_pct": f"{WALKFORWARD_PCT2}%",
                },
                "params": {
                    "vwap_threshold": VWAP_THRESHOLD,
                    "hold_bars": HOLD_BARS,
                    "opening_minutes": OPENING_MINUTES,
                    "atr_period": ATR_PERIOD,
                    "cost_points": COST_POINTS,
                },
                "note": "AI Scientist verified runs — HEURISTIC_UNVERIFIED signal generator",
            },
        }
        write_result(result)
        print(f"NQ VWAP: no signal during RTH — neutral")
        return

    # ── Build active signal payload ──────────────────────────────────────
    direction = signal["side"]
    confidence = round(min(0.35 + abs(signal["deviation"]) / VWAP_THRESHOLD * 0.15, 0.65), 3)

    result = {
        "ts": ts,
        "signal": f"{direction}@nq-vwaptrend",
        "strategy": "vwap",
        "side": direction,
        "direction": direction,
        "confidence": confidence,
        "promoted_for_execution": False,
        "active_window": True,
        "symbol": "NQ",
        "timeframe": "15m",
        "implementation_status": "HEURISTIC_UNVERIFIED",
        "tradable_signal": False,
        "researchOnly": True,
        "writesOrders": False,
        "entry": signal["entry"],
        "target": signal["target"],
        "stop": signal["stop"],
        "vwap": signal["vwap"],
        "atr": signal["atr"],
        "deviation": signal["deviation"],
        "threshold": signal["threshold"],
        "hold_bars": signal["hold_bars"],
        "cost_points": signal["cost_points"],
        "price_now": signal["price_now"],
        "reason": signal["reason"],
        "metadata": {
            "source_run": f"{SOURCE_RUN_PRIMARY} (PF {OOS_PF}) + {SOURCE_RUN_SECONDARY} (PF {OOS_PF2})",
            "primary_run": {
                "run": SOURCE_RUN_PRIMARY,
                "oos_pf": OOS_PF,
                "oos_trades": OOS_TRADES,
                "oos_win_rate_pct": OOS_WIN_RATE,
                "oos_net_points": OOS_NET_POINTS,
                "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE}/{WALKFORWARD_FOLDS}",
                "walkforward_pct": f"{WALKFORWARD_PCT}%",
            },
            "secondary_run": {
                "run": SOURCE_RUN_SECONDARY,
                "oos_pf": OOS_PF2,
                "oos_trades": OOS_TRADES2,
                "oos_win_rate_pct": OOS_WIN_RATE2,
                "oos_net_points": OOS_NET_POINTS2,
                "walkforward_positive_folds": f"{WALKFORWARD_POSITIVE2}/{WALKFORWARD_FOLDS}",
                "walkforward_pct": f"{WALKFORWARD_PCT2}%",
            },
            "params": {
                "vwap_threshold": VWAP_THRESHOLD,
                "hold_bars": HOLD_BARS,
                "opening_minutes": OPENING_MINUTES,
                "atr_period": ATR_PERIOD,
                "cost_points": COST_POINTS,
            },
            "note": "AI Scientist verified runs — HEURISTIC_UNVERIFIED signal generator",
        },
    }

    # Atomic write
    write_result(result)

    print(f"NQ VWAP: {direction} conf={confidence:.3f} "
          f"dev={signal['deviation']:.3f}xATR entry={signal['entry']:.2f} "
          f"target(VWAP)={signal['target']:.2f} price={signal['price_now']:.2f} "
          f"[HEURISTIC_UNVERIFIED]")


if __name__ == "__main__":
    main()
