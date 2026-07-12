#!/usr/bin/env python3
"""
FOMC Gate — Macro Risk Reducer
================================
Checks FRED calendar + system awareness for upcoming FOMC meetings.
Outputs a risk multiplier consumed by brain_cortex.py association cortex.

RULES:
- FOMC decision day (Wed, meeting week): return CAUTION, multiplier 0.3
- Day before FOMC (Tue): return reduced sizing, multiplier 0.5
- Day after FOMC (Thu morning): return CAUTION until 11am ET, then normal
- Normal days: PASS, multiplier 1.0

State file: ~/.rumbling-hedge/state/fomc-gate.latest.json
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

STATE_DIR = Path.home() / ".rumbling-hedge" / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "fomc-gate.latest.json"

# 2026 FOMC meetings (from federalreserve.gov)
FOMC_MEETINGS_2026: list[Tuple[datetime, datetime]] = [
    (datetime(2026, 1, 27, tzinfo=timezone.utc), datetime(2026, 1, 28, tzinfo=timezone.utc)),
    (datetime(2026, 3, 17, tzinfo=timezone.utc), datetime(2026, 3, 18, tzinfo=timezone.utc)),
    (datetime(2026, 5, 5, tzinfo=timezone.utc), datetime(2026, 5, 6, tzinfo=timezone.utc)),
    (datetime(2026, 6, 16, tzinfo=timezone.utc), datetime(2026, 6, 17, tzinfo=timezone.utc)),  # ← THIS WEEK
    (datetime(2026, 7, 28, tzinfo=timezone.utc), datetime(2026, 7, 29, tzinfo=timezone.utc)),
    (datetime(2026, 9, 15, tzinfo=timezone.utc), datetime(2026, 9, 16, tzinfo=timezone.utc)),
    (datetime(2026, 10, 27, tzinfo=timezone.utc), datetime(2026, 10, 28, tzinfo=timezone.utc)),
    (datetime(2026, 12, 8, tzinfo=timezone.utc), datetime(2026, 12, 9, tzinfo=timezone.utc)),
]


def find_next_fomc(now: datetime) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Find the next FOMC meeting relative to now."""
    for day1, day2 in FOMC_MEETINGS_2026:
        # Buffer to end of day in UTC (day2 11:59pm ET = day2+1 03:59 UTC)
        deadline = day2.replace(hour=23, minute=59, second=0, tzinfo=timezone.utc) + timedelta(hours=4)
        if now <= deadline:
            return day1, day2
    return None, None


def get_fomc_verdict() -> dict:
    now = datetime.now(timezone.utc)
    day1, day2 = find_next_fomc(now)

    if day1 is None or day2 is None:
        return {"verdict": "PASS", "multiplier": 1.0, "reason": "no_more_fomc_2026"}

    # EDT offset
    ET_OFFSET = timedelta(hours=-4)  # EDT (summer)

    details = {
        "next_meeting_day1": day1.strftime("%Y-%m-%d"),
        "next_meeting_day2": day2.strftime("%Y-%m-%d"),
        "now_utc": now.isoformat(),
    }

    # Build comparison boundaries
    pre_fomc_start = day1.replace(hour=9, minute=30)  # Tue 9:30am ET
    day2_decision = day2.replace(hour=14, minute=0)    # Wed 2pm ET
    day2_post = day2.replace(hour=14, minute=30)       # Wed 2:30pm ET
    day2_stabilize = day2.replace(hour=17, minute=30)  # Wed 5:30pm ET

    # Convert to UTC for comparison
    bounds = {
        "pre_fomc_start": pre_fomc_start - ET_OFFSET,
        "day2_decision": day2_decision - ET_OFFSET,
        "day2_post": day2_post - ET_OFFSET,
        "day2_stabilize": day2_stabilize - ET_OFFSET,
    }

    # FOMC week: Mon 0:00 ET → Thu 0:00 ET
    fomc_monday = day1 - timedelta(days=1)  # Monday of the meeting week
    fomc_monday_start = fomc_monday.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc) - ET_OFFSET  # Mon 0:00 ET in UTC
    fomc_thursday = day2 + timedelta(days=1)  # Thursday after meeting
    fomc_thursday_start = fomc_thursday.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc) - ET_OFFSET  # Thu 0:00 ET in UTC

    if now < fomc_monday_start:
        return {"verdict": "PASS", "multiplier": 1.0, "reason": "outside_fomc_window", "details": details}

    if now < bounds["pre_fomc_start"]:
        # Pre-FOMC (Mon 0:00 ET → Tue 9:30am ET)
        return {"verdict": "CAUTION", "multiplier": 0.5, "reason": "pre_fomc_window", "details": details}

    if now < bounds["day2_decision"]:
        # FOMC in progress (Tue 9:30am ET → Wed 2pm ET)
        return {"verdict": "CAUTION", "multiplier": 0.3, "reason": "fomc_in_progress", "details": details}

    if now < bounds["day2_post"]:
        # Decision window (Wed 2pm-2:30pm ET)
        return {"verdict": "BLOCK_ALL", "multiplier": 0.0, "reason": "fomc_decision_window", "details": details}

    if now < bounds["day2_stabilize"]:
        # Post-FOMC vol (Wed 2:30-5:30pm ET)
        return {"verdict": "CAUTION", "multiplier": 0.5, "reason": "post_fomc_volatility", "details": details}

    # Thu onwards → normal
    return {"verdict": "PASS", "multiplier": 1.0, "reason": "post_fomc_normal", "details": details}


def run() -> dict:
    result = get_fomc_verdict()
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gate_name": "fomc_gate",
        **result,
        "signal_name": "fomc_gate",
        "confidence": 0.95,
        "direction": 0.0,  # FOMC gate doesn't produce a direction, only a risk qualifier
    }
    STATE_FILE.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    run()
