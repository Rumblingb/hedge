#!/usr/bin/env python3
"""session_gate.py - Session filter, trade cap, day-of-week sizing."""
import os, sys
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo
from pathlib import Path

# Local import for atomic writes
sys.path.insert(0, str(Path(__file__).parent))
from common import atomic_write_json

NY = ZoneInfo("America/New_York")
STATE_DIR = Path(os.environ["HOME"]) / "hedge" / ".rumbling-hedge" / "state"

MAX_TRADES_PER_SESSION = 3
MAX_TRADES_LONDON_SESSION = 2  # conservative cap for London
MAX_TRADES_ASIA_SESSION = 1    # one overnight trade max
# Default: block London/Asia. Set env vars to enable for demo.
# BILL_LONDON_TRADING_ENABLED=true → allow London session trades
# BILL_ASIA_TRADING_ENABLED=true → allow Asia session trades
def _session_config():
    """Re-evaluate session trading config from env vars at runtime with cross-validation."""
    london_enabled = os.environ.get("BILL_LONDON_TRADING_ENABLED", "").lower() == "true"
    asia_enabled = os.environ.get("BILL_ASIA_TRADING_ENABLED", "").lower() == "true"
    # Cross-validate: only allow non-NY sessions if daily plan has BILL_ROUTE_APPROVAL
    # If the gate file doesn't exist or has no daily_plan data, trust the env vars.
    readiness_path = STATE_DIR / "live-readiness-gate.latest.json"
    if readiness_path.exists():
        try:
            import json
            rg = json.loads(readiness_path.read_text())
            plan = rg.get("daily_plan", {})
            if plan:  # Only block if daily_plan data exists and explicitly says not approved
                route_approved = plan.get("BILL_ROUTE_APPROVAL", False)
                if london_enabled and not route_approved:
                    london_enabled = False
                if asia_enabled and not route_approved:
                    asia_enabled = False
        except Exception:
            pass
    skipped = set()
    if not london_enabled:
        skipped.add("london")
    if not asia_enabled:
        skipped.add("asia")
    return london_enabled, asia_enabled, skipped
SKIP_FIRST_MINUTES_NY_OPEN = 5
NO_NEW_TRADES_AFTER_ET = time(14, 0)
FRIDAY_EARLY_CLOSE_ET = time(15, 30)
LONDON_NO_NEW_TRADES_AFTER_UTC = time(11, 30)   # 30 min before London close
ASIA_NO_NEW_TRADES_AFTER_UTC = time(6, 0)       # 30 min before Asia end


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
    _, _, skipped = _session_config()
    if s in skipped:
        return False
    if s == "premarket":
        return False
    if s in ("closed", "postmarket"):
        return False
    # ny always tradable; london/asia tradable when not in SKIP_SESSIONS (env-var controlled)
    return s in ("ny", "london", "asia")


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

    # Session-specific timing and cap checks
    if s == "london":
        utc_now = datetime.now(timezone.utc)
        if utc_now.time() >= LONDON_NO_NEW_TRADES_AFTER_UTC:
            return False, "past 11:30 UTC - London session winding down", 0.0, 0
        if trade_count >= MAX_TRADES_LONDON_SESSION:
            return False, f"max {MAX_TRADES_LONDON_SESSION} London trades reached", 0.0, MAX_TRADES_LONDON_SESSION
        return True, f"london gate PASS ({MAX_TRADES_LONDON_SESSION - trade_count} trades left)", 0.75, MAX_TRADES_LONDON_SESSION - trade_count

    if s == "asia":
        utc_now = datetime.now(timezone.utc)
        if utc_now.time() >= ASIA_NO_NEW_TRADES_AFTER_UTC:
            return False, "past 06:00 UTC - Asia session closing", 0.0, 0
        if trade_count >= MAX_TRADES_ASIA_SESSION:
            return False, f"max {MAX_TRADES_ASIA_SESSION} Asia trades reached", 0.0, MAX_TRADES_ASIA_SESSION
        return True, f"asia gate PASS ({MAX_TRADES_ASIA_SESSION - trade_count} trades left)", 0.5, MAX_TRADES_ASIA_SESSION - trade_count

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
    atomic_write_json(jf, {
        "count": count,
        "max": MAX_TRADES_PER_SESSION,
        "updated": datetime.now(timezone.utc).isoformat()
    })
    return count


# Exports for master_bridge
__all__ = [
    "detect_session", "session_allows_trading", "gate_decision",
    "read_trade_count", "increment_trade_count",
    "MAX_TRADES_PER_SESSION", "_session_config"
]
