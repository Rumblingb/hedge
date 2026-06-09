#!/usr/bin/env python3
"""cron_health_check.py — Monitor all Hermes cron jobs for errors.
Runs every 15m, writes .rumbling-hedge/state/cron-health.latest.json.
Hermes reads this to detect and act on cron failures immediately."""

import json, os
from pathlib import Path
from datetime import datetime, timezone

STATE = Path(os.environ["HOME"]) / "hedge" / ".rumbling-hedge" / "state"
JOBS_FILE = Path(os.environ["HOME"]) / ".hermes" / "cron" / "jobs.json"


def estimate_interval(schedule: str) -> int:
    """Estimate expected interval in minutes from cron schedule or 'every' format."""
    s = schedule.strip()
    # 'every N unit' format
    if s.startswith("every "):
        parts = s.split()
        for i, p in enumerate(parts):
            if p.lstrip("-").isdigit() and i + 1 < len(parts):
                unit = parts[i + 1]
                mult = {"m": 1, "min": 1, "h": 60, "hour": 60, "hours": 60}.get(unit, 1)
                return int(p) * mult
            # Handle '720m' as combined number+unit
            if p[:-1].lstrip("-").isdigit() and p[-1] in "mh":
                num = int(p[:-1])
                mult = 60 if p[-1] == "h" else 1
                return num * mult
        return 60
    # Standard cron: 'min hour day month weekday'
    fields = s.split()
    if len(fields) >= 5:
        minute, hour = fields[0], fields[1]
        # '0 6 * * 1' → weekly (Monday at 6)
        if fields[4] in ("0", "1", "2", "3", "4", "5", "6", "7", "sun", "mon", "tue", "wed", "thu", "fri", "sat"):
            return 10080  # weekly
        # '0 6 * * *' → daily
        if minute == "0" and hour not in ("*",):
            return 1440
        # '* /15' → every 15 min
        if minute.startswith("*/"):
            try: return int(minute.lstrip("*/"))
            except: return 60
        # '*/5 14-21 * * 1-5' → every 5 min during market hours
        if hour.startswith("*/"):
            try: return int(hour.lstrip("*/"))
            except: return 60
        # Specific minute, specific hour range → intraday
        if minute.isdigit() and ":" not in hour and "-" in hour:
            return 1440  # daily pattern like '30 14,21'
        if minute.isdigit() and hour.isdigit():
            return 1440  # daily at specific time
        return 60
    return 60


def check_jobs():
    if not JOBS_FILE.exists():
        return {"error": f"Jobs file not found: {JOBS_FILE}"}

    jobs_data = json.loads(JOBS_FILE.read_text())
    jobs = jobs_data.get("jobs", []) if isinstance(jobs_data, dict) else jobs_data
    now = datetime.now(timezone.utc)
    failed = []
    all_ok = True

    for job in jobs:
        if not isinstance(job, dict):
            continue
        jid = job.get("id", "?")
        name = job.get("name", jid)
        status = job.get("last_status", "never_run")
        last_run_str = job.get("last_run_at")
        enabled = job.get("enabled", False)
        paused = job.get("state") == "paused"

        last_run = None
        if last_run_str:
            try:
                last_run = datetime.fromisoformat(last_run_str)
            except Exception:
                pass

        if status == "error" and enabled and not paused:
            failed.append({
                "id": jid, "name": name,
                "schedule": job.get("schedule", "?"),
                "last_run": last_run_str,
                "last_status": status,
                "last_error": job.get("last_delivery_error", "unknown"),
            })
            all_ok = False

        if last_run and enabled and not paused:
            age_mins = (now - last_run).total_seconds() / 60
            raw_schedule = job.get("schedule", "")
            schedule = raw_schedule
            if isinstance(raw_schedule, dict):
                schedule = raw_schedule.get("display", raw_schedule.get("expr", ""))
            elif not isinstance(raw_schedule, str):
                schedule = str(raw_schedule)
            expected_mins = estimate_interval(schedule)
            if expected_mins > 0 and age_mins > expected_mins * 3:
                failed.append({
                    "id": jid, "name": name,
                    "schedule": schedule,
                    "last_run": last_run_str,
                    "last_status": "stale",
                    "last_error": f"Not run in {age_mins:.0f}m (expected ~{expected_mins}m)",
                })
                all_ok = False

    result = {
        "ts": now.isoformat(),
        "total_jobs": len(jobs),
        "healthy": all_ok,
        "failed_count": len(failed),
        "failed": failed,
        "action_required": len(failed) > 0,
    }

    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "cron-health.latest.json").write_text(json.dumps(result, indent=2))

    if failed:
        for f in failed:
            print(f"❌ CRON FAILURE: {f['name']} — {f['last_error']}")
    else:
        print(f"✅ All {len(jobs)} crons healthy")

    return result


if __name__ == "__main__":
    check_jobs()
