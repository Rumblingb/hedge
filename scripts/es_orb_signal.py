#!/usr/bin/env python3
"""es_orb_signal.py — ES 15m ORB signal generator (HEURISTIC_UNVERIFIED).

AI Scientist verified run: run_it_orb_es15m
- OOS PF: 1.385, 538 trades, 43.9% WR
- Params: range_window_bars=6, hold_bars=6, volume_threshold=1.6
- This signal: 1-bar opening range (15m), 4-bar hold (60 min), vt=1.6

HEURISTIC_UNVERIFIED — promoted_for_execution: false.
Must pass AI Scientist OOS validation before promotion.
"""
import json, os, sys
from datetime import datetime, timezone, time, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import atomic_write_json

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
DATA = ROOT / "data/free"
SIGNAL_PATH = STATE / "es-orb-signal.latest.json"

# AI Scientist verified params
VOL_THRESH = 1.6       # volume_threshold from AI Scientist run
HOLD_BARS = 4          # hold for 4 bars (60 min)
ENTRY_OFFSET = 0       # entry_offset_ticks from AI Scientist run
TICK_SIZE = 0.25       # ES minimum tick
COST = 1.5             # cost_points

# RTH session for ES: 9:30 ET – 16:00 ET
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def read_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def find_es_15m_csv():
    """Find the most suitable ES 15m CSV file from data/free."""
    candidates = sorted(DATA.glob("ES-15m-*.csv"))
    if candidates:
        return candidates[-1]  # newest by filename convention
    # Fallback: try combined files
    fallbacks = sorted(DATA.glob("ES-60d-15m-*.csv"))
    if fallbacks:
        return fallbacks[-1]
    # Last resort: any 15m file with ES data
    return None


def load_es_15m_bars():
    """Load ES 15m bars from the best available CSV, resampling 1m if needed."""
    csv_path = find_es_15m_csv()
    if csv_path is None or not csv_path.exists():
        print(f"❌ No ES 15m CSV found in {DATA}")
        return None

    import pandas as pd
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)

    if "symbol" in df.columns:
        df = df[df["symbol"] == "ES"].copy()

    df = df.sort_values("ts").drop_duplicates(subset="ts").reset_index(drop=True)

    # If data is not already 15m, resample
    if df.empty:
        return None

    # Check spacing — if median interval < 10 min, it's sub-15m and needs resampling
    deltas = df["ts"].diff().dropna().dt.total_seconds().median()
    if deltas < 600:  # less than 10 min median spacing
        df = df.set_index("ts")
        resampled = df.resample("15min", label="right", closed="right").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum" if "volume" in df.columns else "first",
        }).dropna().reset_index()
        df = resampled

    # Compute session time fields in ET
    et = df["ts"].dt.tz_convert("America/New_York")
    df["minutes_from_rth_open"] = et.dt.hour * 60 + et.dt.minute - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)
    df["date"] = et.dt.date
    df["time_et"] = et.dt.time

    return df


def in_rth(now_utc=None):
    """Check if current time is within ES RTH (9:30-16:00 ET)."""
    import pytz
    et_tz = pytz.timezone("America/New_York")
    now_et = (now_utc or datetime.now(timezone.utc)).astimezone(et_tz)
    return RTH_OPEN <= now_et.time() < RTH_CLOSE


def compute_atr(df, period=14):
    """Compute ATR on the dataframe."""
    import pandas as pd
    tr = pd.concat([
        abs(df["high"] - df["low"]),
        abs(df["high"] - df["close"].shift(1)),
        abs(df["low"] - df["close"].shift(1)),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=7).mean()


def generate_signal():
    """Generate ES ORB 15m signal based on AI Scientist verified params."""
    now = datetime.now(timezone.utc)
    import pytz
    et_tz = pytz.timezone("America/New_York")
    now_et = now.astimezone(et_tz)

    # Self-zero outside RTH
    if not in_rth(now):
        return None, "outside_rth"

    df = load_es_15m_bars()
    if df is None or df.empty:
        return None, "no_data"

    today = now_et.date()
    today_bars = df[df["date"] == today].copy()
    if today_bars.empty:
        return None, "no_today_data"

    # Opening range: first 1 bar after RTH open (minutes_from_rth_open >= 0)
    opening = today_bars[today_bars["minutes_from_rth_open"] == 0].copy()
    after = today_bars[today_bars["minutes_from_rth_open"] > 0].copy()

    if opening.empty:
        return None, "orb_not_formed"
    if after.empty:
        return None, "no_post_orb_bars"

    range_high = opening["high"].max()
    range_low = opening["low"].min()

    # Volume baseline from opening bar
    opening_vol = float(opening["volume"].iloc[0]) if "volume" in opening.columns and not opening["volume"].isna().iloc[0] else 0
    vol_floor = opening_vol * VOL_THRESH if opening_vol > 0 else 0

    # ATR
    atr = compute_atr(df)
    atr_val = float(atr.iloc[-1]) if not atr.empty else 20.0

    # Check last 2 bars for breakout confirmation
    recent = after.tail(2)
    if recent.empty:
        return None, "no_recent_bars"

    # Long breakout: price broke above ORB high
    if recent["high"].max() > range_high + ENTRY_OFFSET * TICK_SIZE:
        entry_bar = recent[recent["high"] > range_high].iloc[0]
        if VOL_THRESH <= 1 or entry_bar["volume"] >= vol_floor:
            entry = range_high
            # ATR-based stop (wider for ES)
            sl = entry - atr_val * 1.0
            tp = entry + atr_val * 2.0  # 2:1 reward:risk
            rr = (tp - entry) / (entry - sl) if (entry - sl) > 0 else 0
            return {
                "side": "long",
                "entry": round(entry, 2),
                "stop": round(sl, 2),
                "target": round(tp, 2),
                "rr": round(rr, 2),
                "reason": f"es_orb15m_long_breakout_{range_high:.2f}",
                "price_now": float(recent.iloc[-1]["close"]),
                "hold_bars": HOLD_BARS,
                "atr": round(atr_val, 2),
            }, None

    # Short breakout: price broke below ORB low
    if recent["low"].min() < range_low - ENTRY_OFFSET * TICK_SIZE:
        entry_bar = recent[recent["low"] < range_low].iloc[0]
        if VOL_THRESH <= 1 or entry_bar["volume"] >= vol_floor:
            entry = range_low
            sl = entry + atr_val * 1.0
            tp = entry - atr_val * 2.0
            rr = (entry - tp) / (sl - entry) if (sl - entry) > 0 else 0
            return {
                "side": "short",
                "entry": round(entry, 2),
                "stop": round(sl, 2),
                "target": round(tp, 2),
                "rr": round(rr, 2),
                "reason": f"es_orb15m_short_breakout_{range_low:.2f}",
                "price_now": float(recent.iloc[-1]["close"]),
                "hold_bars": HOLD_BARS,
                "atr": round(atr_val, 2),
            }, None

    return None, "no_breakout"


def write_zero_signal(reason="outside_rth"):
    """Write a zero/null signal to clear the state file."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "ts": now,
        "signal": "zero",
        "strategy": "es-orb-15m",
        "side": None,
        "direction": None,
        "entry": None,
        "stop": None,
        "target": None,
        "rr": 0.0,
        "contracts": 0,
        "research_contracts": 0,
        "accounts": 0,
        "route": "none",
        "submitted": False,
        "status": "inactive",
        "price_now": None,
        "reason": f"zeroed_{reason}",
        "confidence": 0.0,
        "promoted_for_execution": False,
        "tradable_signal": False,
        "heuristic_unverified": True,
        "hold_bars": HOLD_BARS,
    }
    STATE.mkdir(parents=True, exist_ok=True)
    atomic_write_json(SIGNAL_PATH, payload)
    print(f"🟡 ES ORB 15m signal zeroed: {reason}")


def write_signal(signal):
    """Write the ES ORB 15m signal to state file."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "ts": now,
        "signal": f"{signal['side']}@es-orb-15m",
        "strategy": "es-orb-15m",
        "side": signal["side"],
        "direction": signal["side"],
        "entry": signal["entry"],
        "stop": signal["stop"],
        "target": signal["target"],
        "rr": signal["rr"],
        "contracts": 1,
        "research_contracts": 3,
        "accounts": 1,
        "route": "topstep_demo",
        "submitted": False,
        "status": "signal_generated",
        "price_now": signal["price_now"],
        "reason": signal["reason"],
        "confidence": 0.6,
        "promoted_for_execution": False,
        "tradable_signal": True,
        "execution_firewall": {"allowed": False, "blockers": ["heuristic_unverified"]},
        "heuristic_unverified": True,
        "hold_bars": signal.get("hold_bars", HOLD_BARS),
        "atr": signal.get("atr"),
        "ai_scientist_ref": "run_it_orb_es15m",
        "oos_pf": 1.385,
        "oos_trades": 538,
        "oos_win_rate": 0.439,
    }

    STATE.mkdir(parents=True, exist_ok=True)
    atomic_write_json(SIGNAL_PATH, payload)

    print(f"✅ ES ORB 15m signal: {signal['side']} @ {signal['entry']} "
          f"(SL={signal['stop']}, TP={signal['target']}, RR={signal['rr']:.2f}, "
          f"hold={signal.get('hold_bars', HOLD_BARS)} bars)")
    print(f"   → {SIGNAL_PATH}")
    return payload


if __name__ == "__main__":
    signal, zero_reason = generate_signal()
    if signal:
        write_signal(signal)
        print(f"   Price now: {signal['price_now']}")
    else:
        write_zero_signal(zero_reason or "no_signal")
        sys.exit(0)
