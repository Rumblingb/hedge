#!/usr/bin/env python3
"""session_gate.py - Session filter, trade cap, day-of-week sizing."""
import os
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo
from pathlib import Path

NY = ZoneInfo("America/New_York")
STATE_DIR = Path(os.environ["HOME"]) / "hedge" / ".rumbling-hedge" / "state"

MAX_TRADES_PER_SESSION = 3
SKIP_SESSIONS = {"asia", "london"}
SKIP_FIRST_MINUTES_NY_OPEN = 5
NO_NEW_TRADES_AFTER_ET = time(14, 0)
FRIDAY_EARLY_CLOSE_ET = time(15, 30)


def _now_et():
    return datetime.now(timezone.utc).astimezone(NY)


def detect_session(now=None):
    """Classify current session: asia, london, ny, postmarket, closed."""
    et = (now or _now_et())
    t = et.time()
    w = et.weekday()  # 0=Mon, 6=Sun

    if w == 5:
        return "closed"  # Saturday
    if w == 6 and t < time(18, 0):
        return "closed"  # Sunday before Globex

    if time(18, 0) <= t or t < time(3, 0):
        return "asia"
    if time(3, 0) <= t < time(6, 30):
        return "london"
    if time(6, 30) <= t < time(9, 30):
        return "premarket"
    if time(9, 30) <= t < time(16, 0):
        return "ny"
    return "postmarket"


def session_allows_trading(session=None):
    """True if this session should trade."""
    s = session or detect_session()
    if s in SKIP_SESSIONS:
        return False
    if s == "premarket":
        return False
    if s in ("closed", "postmarket"):
        return False
    return s == "ny"


def ny_open_minutes(now=None):
    """Minutes since 09:30 ET. Negative before open."""
    et = (now or _now_et())
    return (et.hour - 9) * 60 + et.minute - 30


def gate_decision(session=None, trade_count=0, now=None):
    """
    Return (allowed: bool, reason: str, size_multiplier: float, max_trades: int).
    """
    s = session or detect_session()
    et = (now or _now_et())
    w = et.weekday()

    if not session_allows_trading(s):
        return False, f"session {s} blocked", 0.0, 0

    m = ny_open_minutes(et)
    if m < SKIP_FIRST_MINUTES_NY_OPEN:
        return False, f"first {SKIP_FIRST_MINUTES_NY_OPEN}min of NY open", 0.0, 0

    if et.time() >= NO_NEW_TRADES_AFTER_ET:
        return False, "past 14:00 ET - no new trades", 0.0, 0

    if w == 4 and et.time() >= FRIDAY_EARLY_CLOSE_ET:
        return False, "Friday after 15:30 ET", 0.0, 0

    if trade_count >= MAX_TRADES_PER_SESSION:
        return False, f"max {MAX_TRADES_PER_SESSION} trades reached", 0.0, MAX_TRADES_PER_SESSION

    # Day-of-week sizing
    if w == 1:  # Tuesday
        mult = 1.0
        label = "Tue=full"
    elif w in (2, 4):  # Wednesday, Friday
        mult = 0.5
        label = "Wed/Fri=half"
    else:  # Monday, Thursday
        mult = 1.0
        label = "standard"

    remaining = MAX_TRADES_PER_SESSION - trade_count
    return True, f"{s} gate PASS ({label}, {remaining} trades left)", mult, remaining


def read_trade_count(state_dir=None):
    """Count today's trades from journal."""
    sd = state_dir or STATE_DIR
    jf = sd / "trade-count-today.json"
    if jf.exists():
        try:
            import json
            d = json.loads(jf.read_text())
            return d.get("count", 0)
        except Exception:
            pass
    return 0


def increment_trade_count(state_dir=None):
    """Bump today's trade counter."""
    sd = state_dir or STATE_DIR
    jf = sd / "trade-count-today.json"
    count = read_trade_count(sd) + 1
    import json
    jf.parent.mkdir(parents=True, exist_ok=True)
    jf.write_text(json.dumps({
        "count": count,
        "max": MAX_TRADES_PER_SESSION,
        "updated": datetime.now(timezone.utc).isoformat()
    }, indent=2))
    return count


# Exports for master_bridge
__all__ = [
    "detect_session", "session_allows_trading", "gate_decision",
    "read_trade_count", "increment_trade_count",
    "MAX_TRADES_PER_SESSION", "SKIP_SESSIONS"
]
