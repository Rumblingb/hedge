#!/usr/bin/env python3
"""
Noise Area Intraday Scalp — NQ 5m
==================================
Adapted from QuantsPlayBook "Noise Area" intraday momentum system.

Strategy:
- Builds dynamic "noise boundaries" (river banks) around session open
  using 14-day rolling average of price deviation per 5m bar position
- LONG when price breaks ABOVE upper noise boundary
- SHORT when price breaks BELOW lower noise boundary
- Exit: price crosses VWAP or returns inside noise area

Position:
- Max 3 MNQ contracts
- Scale-out: TP1 +15pt (close 1/3), TP2 +30pt (close 1/3), trail from +30pt (last 1/3)
- Stop: opposite noise boundary at entry time

Session filters (ET = America/New_York):
- London:  03:00 - 09:30 ET
- Asia:    19:00 - 03:00 ET (overnight)

Data: ~/hedge/data/free/NQ-5m-*.csv (5m OHLCV)
Output: ~/.rumbling-hedge/state/noise-area-signal.latest.json
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path(
    os.environ.get("BILL_STATE_DIR")
    or os.environ.get("RH_STATE_DIR")
    or (ROOT / ".rumbling-hedge" / "state")
)
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "noise-area-signal.latest.json"

DATA_DIR = Path(os.environ.get("BILL_DATA_DIR") or (ROOT / "data" / "free"))

ET = ZoneInfo("America/New_York")
UTC = timezone.utc

LOOKBACK_DAYS = 14
SESSION_LONDON = ("03:00", "09:30")  # ET
SESSION_ASIA = ("19:00", "03:00")    # ET (spans midnight)
MAX_CONTRACTS = 3
TP1_PTS = 15
TP2_PTS = 30
TRAIL_TRIGGER_PTS = 30

# Stale data threshold — if newest bar older than 15 min, flag stale
STALE_MINUTES = 15


def safety_metadata(reason: str = "research-only") -> Dict:
    return {
        "researchOnly": True,
        "advisoryOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "execution_block_reason": reason,
    }


def log(msg: str):
    ts = datetime.now(UTC).isoformat()
    print(f"[{ts}] {msg}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_data(symbol: str = "NQ") -> Optional[pd.DataFrame]:
    """Load 5m OHLCV data, merging 60d depth with 5d freshness."""
    files_60d = DATA_DIR / f"{symbol}-5m-60d.csv"
    files_5d = DATA_DIR / f"{symbol}-5m-5d.csv"

    frames = []
    for p in [files_60d, files_5d]:
        if p.exists():
            try:
                df = pd.read_csv(p)
                if "ts" in df.columns:
                    df.rename(columns={"ts": "time"}, inplace=True)
                df["time"] = pd.to_datetime(df["time"], utc=True)
                df["time_et"] = df["time"].dt.tz_convert(ET)
                df["date_et"] = df["time_et"].dt.date
                df["tod_et"] = df["time_et"].dt.strftime("%H:%M")
                frames.append(df)
            except Exception as e:
                log(f"  ⚠️  Failed to load {p.name}: {e}")

    if not frames:
        return None

    if len(frames) == 2:
        # Merge: use 60d for depth, deduplicate keeping 5d's fresher rows
        merged = pd.concat(frames, ignore_index=True)
        merged.drop_duplicates(subset=["time"], keep="last", inplace=True)
        merged.sort_values("time", inplace=True)
        merged.reset_index(drop=True, inplace=True)
        return merged

    df = frames[0]
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def check_freshness(df: pd.DataFrame) -> Tuple[bool, Optional[datetime]]:
    """Return (is_fresh, last_bar_time_utc)."""
    if df is None or len(df) == 0:
        return False, None
    last_ts = df["time"].iloc[-1]
    now = datetime.now(UTC)
    age_min = (now - last_ts).total_seconds() / 60
    return age_min <= STALE_MINUTES, last_ts


# ---------------------------------------------------------------------------
# Session detection
# ---------------------------------------------------------------------------
def get_session(tod_et: str) -> Optional[str]:
    """Return 'london', 'asia', or None based on ET time-of-day."""
    h, m = int(tod_et[:2]), int(tod_et[3:5])
    t = h * 60 + m

    lon_start, lon_end = 180, 570   # 03:00, 09:30
    asia_start = 1140               # 19:00
    asia_end = 180                  # 03:00 (next day)

    if lon_start <= t < lon_end:
        return "london"
    if t >= asia_start or t < asia_end:
        return "asia"
    return None


# ---------------------------------------------------------------------------
# Noise Area calculation
# ---------------------------------------------------------------------------
def compute_noise_area(
    df: pd.DataFrame,
    session: str,
    lookback_days: int = LOOKBACK_DAYS,
) -> Optional[Dict]:
    """
    Compute noise boundaries for the current session.

    For each 5m bar position within the session, compute the average
    cumulative deviation from session open (high - open, open - low)
    over the last `lookback_days` trading days.

    Returns dict with upper/lower boundary arrays and current bar index.
    """
    session_dates = _get_session_dates(df, session, lookback_days + 1)
    if len(session_dates) < 5:
        log(f"  Not enough session days ({len(session_dates)} < 5)")
        return None

    # Historical session data (exclude today for boundary calc)
    today_date = session_dates[-1]
    hist_dates = session_dates[:-1]  # last N days excluding today

    # For each historical date, extract session bars and compute deviations
    # Use the current day's time slots as reference for alignment
    # Build a reference time-of-day list from the most complete day
    max_bars = 0
    ref_tods = None
    for d in hist_dates:
        mask = (df["date_et"] == d) & df["tod_et"].apply(lambda t: _in_session(t, session))
        bars = df.loc[mask]
        if len(bars) > max_bars:
            max_bars = len(bars)
            ref_tods = bars["tod_et"].tolist()

    if ref_tods is None:
        log(f"  No historical session bars found")
        return None

    tod_list = ref_tods
    dev_up_list = []   # list of arrays: max(high - open) at each bar position
    dev_dn_list = []   # list of arrays: max(open - low) at each bar position

    for d in hist_dates:
        mask = (df["date_et"] == d) & df["tod_et"].apply(lambda t: _in_session(t, session))
        bars = df.loc[mask].copy()
        if len(bars) < 10:
            continue

        # Align by time-of-day: match bars to ref_tods
        bar_tods = bars["tod_et"].tolist()
        highs = bars["high"].values
        lows = bars["low"].values

        # Compute deviations for matched positions
        cum_up = np.full(len(tod_list), np.nan)
        cum_dn = np.full(len(tod_list), np.nan)

        # Map each bar's tod to its position in tod_list
        bar_tod_set = {t: i for i, t in enumerate(bar_tods)}
        ref_tod_set = {t: i for i, t in enumerate(tod_list)}

        # Matched positions
        j = 0
        run_high = 0
        run_low = float('inf')
        for ref_i, ref_tod in enumerate(tod_list):
            if ref_tod in bar_tod_set:
                bi = bar_tod_set[ref_tod]
                run_high = max(run_high, highs[bi])
                run_low = min(run_low, lows[bi])
                session_open = float(bars["open"].iloc[0])
                cum_up[ref_i] = max(0, run_high - session_open)
                cum_dn[ref_i] = max(0, session_open - run_low)

        # Only use if we have at least 50% of reference positions
        matched = np.sum(~np.isnan(cum_up))
        if matched / len(tod_list) >= 0.5:
            # Fill NaN with last known value (forward fill)
            for i in range(1, len(cum_up)):
                if np.isnan(cum_up[i]):
                    cum_up[i] = cum_up[i-1]
                    cum_dn[i] = cum_dn[i-1]
            # Replace remaining leading NaNs with 0
            cum_up = np.nan_to_num(cum_up, nan=0.0)
            cum_dn = np.nan_to_num(cum_dn, nan=0.0)
            dev_up_list.append(cum_up)
            dev_dn_list.append(cum_dn)

    if tod_list is None or len(dev_up_list) < 3:
        log(f"  Not enough valid session history ({len(dev_up_list)} < 3)")
        return None

    # Average boundaries
    avg_up = np.mean(dev_up_list, axis=0)
    avg_dn = np.mean(dev_dn_list, axis=0)

    # Add a small buffer to avoid false triggers (minimum 5 pts)
    buffer = 10.0  # fixed buffer for NQ, reasonable for 5m noise

    # Current session bars
    curr_mask = (df["date_et"] == today_date) & df["tod_et"].apply(lambda t: _in_session(t, session))
    curr_bars = df.loc[curr_mask].copy()
    if len(curr_bars) == 0:
        return None

    session_open = float(curr_bars["open"].iloc[0])

    # Current bar index within session
    curr_idx = len(curr_bars) - 1
    if curr_idx >= len(avg_up):
        curr_idx = len(avg_up) - 1

    # Current noise boundaries
    upper_boundary = session_open + avg_up[curr_idx] + buffer
    lower_boundary = session_open - avg_dn[curr_idx] - buffer

    # Current price
    current_close = float(curr_bars["close"].iloc[-1])
    current_high = float(curr_bars["high"].iloc[-1])
    current_low = float(curr_bars["low"].iloc[-1])
    current_time = str(curr_bars["time"].iloc[-1])

    # VWAP (session VWAP)
    cum_vol = curr_bars["volume"].values.cumsum()
    cum_vp = (curr_bars["close"].values * curr_bars["volume"].values).cumsum()
    vwap = float(cum_vp[-1] / cum_vol[-1]) if cum_vol[-1] > 0 else current_close

    return {
        "session": session,
        "session_open": round(session_open, 2),
        "upper_boundary": round(upper_boundary, 2),
        "lower_boundary": round(lower_boundary, 2),
        "avg_upper_dev": round(float(avg_up[curr_idx]), 2),
        "avg_lower_dev": round(float(avg_dn[curr_idx]), 2),
        "buffer_pts": round(buffer, 2),
        "current_close": round(current_close, 2),
        "current_high": round(current_high, 2),
        "current_low": round(current_low, 2),
        "vwap": round(vwap, 2),
        "bar_index": curr_idx,
        "bar_time": current_time,
        "bars_in_session": len(curr_bars),
        "hist_days_used": len(dev_up_list),
    }


def _get_session_dates(df: pd.DataFrame, session: str, n_days: int) -> List:
    """Get the last n_days that have data for the given session."""
    all_dates = sorted(df["date_et"].unique())
    session_dates = []
    for d in reversed(all_dates):
        mask = (df["date_et"] == d) & df["tod_et"].apply(lambda t: _in_session(t, session))
        if mask.sum() > 0:
            session_dates.append(d)
        if len(session_dates) >= n_days:
            break
    return list(reversed(session_dates))


def _in_session(tod_et: str, session: str) -> bool:
    """Check if a time-of-day string falls within the session."""
    h, m = int(tod_et[:2]), int(tod_et[3:5])
    t = h * 60 + m
    if session == "london":
        return 180 <= t < 570  # 03:00-09:30
    elif session == "asia":
        return t >= 1140 or t < 180  # 19:00-03:00
    return False


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------
def generate_signal(
    noise: Dict,
    session: str,
) -> Dict:
    """Generate entry/exit signal from noise area data."""
    close = noise["current_close"]
    upper = noise["upper_boundary"]
    lower = noise["lower_boundary"]
    vwap = noise["vwap"]
    session_open = noise["session_open"]

    entry_signal = "HOLD"
    direction = "neutral"
    entry_price = None
    stop_loss = None
    tp1 = None
    tp2 = None
    exit_signal = "HOLD"

    # --- Entry logic ---
    # LONG: close breaks above upper noise boundary
    if close > upper:
        entry_signal = "LONG_ENTRY"
        direction = "long"
        entry_price = close
        stop_loss = lower  # opposite noise boundary
        tp1 = round(entry_price + TP1_PTS, 2)
        tp2 = round(entry_price + TP2_PTS, 2)

    # SHORT: close breaks below lower noise boundary
    elif close < lower:
        entry_signal = "SHORT_ENTRY"
        direction = "short"
        entry_price = close
        stop_loss = upper  # opposite noise boundary
        tp1 = round(entry_price - TP1_PTS, 2)
        tp2 = round(entry_price - TP2_PTS, 2)

    # --- Exit logic (for existing positions) ---
    # Exit if price returns inside noise area or crosses VWAP
    if lower <= close <= upper:
        # Inside noise = exit any position
        exit_signal = "EXIT_FLAT"

    return {
        "entry_signal": entry_signal,
        "direction": direction,
        "entry_price": round(entry_price, 2) if entry_price else None,
        "stop_loss": round(stop_loss, 2) if stop_loss else None,
        "tp1": tp1,
        "tp2": tp2,
        "trail_trigger_pts": TRAIL_TRIGGER_PTS,
        "exit_signal": exit_signal,
        "max_contracts": MAX_CONTRACTS,
        "scale_out": {
            "tp1_pts": TP1_PTS,
            "tp1_contracts": 1,
            "tp2_pts": TP2_PTS,
            "tp2_contracts": 1,
            "trail_contracts": 1,
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(symbol: str = "NQ") -> Optional[Dict]:
    log(f"Noise Area Intraday Scalp — {symbol} 5m")

    df = load_data(symbol)
    if df is None:
        log("❌ No data available")
        _write_empty_state("no_data")
        return None

    is_fresh, last_ts = check_freshness(df)
    if not is_fresh:
        age_str = last_ts.isoformat() if last_ts else "unknown"
        log(f"⚠️  Stale data (last bar: {age_str}), generating cautious signal")

    # Detect current session
    now_et = datetime.now(ET)
    tod_et = now_et.strftime("%H:%M")
    session = get_session(tod_et)

    if session is None:
        log(f"  Outside sessions (current ET: {tod_et}). No signal.")
        _write_empty_state("outside_session")
        return None

    log(f"  Session: {session} (ET: {tod_et})")

    # Compute noise area
    noise = compute_noise_area(df, session)
    if noise is None:
        log(f"  ⚠️  Could not compute noise area for {session}")
        _write_empty_state("noise_calc_failed")
        return None

    # Generate signal for research, then suppress actionable-looking fields
    # when freshness/session gates are not clean. Keep the raw read for
    # post-market analysis without letting consumers mistake it for a route.
    raw_sig = generate_signal(noise, session)
    sig = raw_sig
    execution_block_reason = "research-only"
    if not is_fresh:
        execution_block_reason = "stale-data-research-only"
        sig = {
            **raw_sig,
            "entry_signal": "HOLD",
            "direction": "neutral",
            "entry_price": None,
            "stop_loss": None,
            "tp1": None,
            "tp2": None,
            "exit_signal": "HOLD",
        }

    # Build output
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy": "Noise Area Intraday",
        "source": "quantsplaybook-noise-area-adapted",
        "symbol": symbol,
        "timeframe": "5m",
        "session": session,
        "data_fresh": is_fresh,
        "last_bar_utc": str(noise["bar_time"]),
        "price": {
            "close": noise["current_close"],
            "high": noise["current_high"],
            "low": noise["current_low"],
        },
        "noise_area": {
            "session_open": noise["session_open"],
            "upper_boundary": noise["upper_boundary"],
            "lower_boundary": noise["lower_boundary"],
            "width_pts": round(noise["upper_boundary"] - noise["lower_boundary"], 2),
            "avg_upper_dev_pts": noise["avg_upper_dev"],
            "avg_lower_dev_pts": noise["avg_lower_dev"],
            "buffer_pts": noise["buffer_pts"],
            "hist_days_used": noise["hist_days_used"],
        },
        "vwap": noise["vwap"],
        "bar_index": noise["bar_index"],
        "entry_signal": sig["entry_signal"],
        "direction": sig["direction"],
        "entry_price": sig["entry_price"],
        "stop_loss": sig["stop_loss"],
        "tp1": sig["tp1"],
        "tp2": sig["tp2"],
        "trail_trigger_pts": sig["trail_trigger_pts"],
        "exit_signal": sig["exit_signal"],
        "max_contracts": sig["max_contracts"],
        "scale_out": sig["scale_out"],
        "raw_research_signal": raw_sig,
        **safety_metadata(execution_block_reason),
    }

    # Risk/reward
    if sig["entry_price"] and sig["stop_loss"]:
        risk = abs(sig["entry_price"] - sig["stop_loss"])
        reward = TP2_PTS  # target is TP2 for R:R
        output["risk_reward"] = round(reward / risk, 2) if risk > 0 else None
    else:
        output["risk_reward"] = None

    # Write state file
    with open(STATE_FILE, "w") as f:
        json.dump(output, f, indent=2)

    log(f"✅ Written to {STATE_FILE}")
    log(f"  Session: {session} | Noise: {noise['lower_boundary']:.1f} — {noise['upper_boundary']:.1f}")
    log(f"  Open: {noise['session_open']:.1f} | VWAP: {noise['vwap']:.1f}")
    log(f"  Close: {noise['current_close']:.1f} | Signal: {sig['entry_signal']}")
    if sig["entry_price"]:
        log(f"  Entry: {sig['entry_price']:.1f} | SL: {sig['stop_loss']:.1f} | TP1: {sig['tp1']:.1f} | TP2: {sig['tp2']:.1f}")
    if not is_fresh:
        log(f"  ⚠️  DATA STALE — treat signal with caution")

    return output


def _write_empty_state(reason: str):
    """Write a no-signal state file for graceful degradation."""
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy": "Noise Area Intraday",
        "source": "quantsplaybook-noise-area-adapted",
        "symbol": "NQ",
        "timeframe": "5m",
        "entry_signal": "HOLD",
        "direction": "neutral",
        "entry_price": None,
        "stop_loss": None,
        "tp1": None,
        "tp2": None,
        "exit_signal": "HOLD",
        "max_contracts": MAX_CONTRACTS,
        "reason": reason,
        **safety_metadata(reason),
    }
    with open(STATE_FILE, "w") as f:
        json.dump(output, f, indent=2)
    log(f"  Written HOLD state ({reason}) to {STATE_FILE}")


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    result = run(symbol)
    # Exit 0 for graceful no-signal (outside session, stale data, etc.)
    # Exit 1 only for actual failures (no data files at all)
    if result is None and not STATE_FILE.exists():
        sys.exit(1)
    sys.exit(0)
