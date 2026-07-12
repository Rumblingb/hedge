#!/usr/bin/env python3
"""Freshness sentinel — alerts when critical artifacts go stale.

Reads config/artifact-slas.json, checks file mtimes (and embedded ts when
present) against per-artifact SLAs within their active windows, and writes
.rumbling-hedge/state/freshness-sentinel.latest.json. Prints breaches to
stdout (Hermes no-agent cron delivers it), stays silent-ish when green.

Design rule this enforces: "process ran" is not health — "output is fresh" is.
The 2026-06-11/12 quote outage (13h, all trades blocked) and the 29h DOM-capture
death both had healthy-looking process stamps.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "hedge"
CONFIG = ROOT / "config/artifact-slas.json"
OUT = ROOT / ".rumbling-hedge/state/freshness-sentinel.latest.json"


def artifact_age_minutes(path: Path) -> float:
    """Age from embedded ts field when parseable, else file mtime."""
    mtime_age = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 60
    if path.suffix == ".json":
        try:
            doc = json.loads(path.read_text())
            ts = doc.get("ts") if isinstance(doc, dict) else None
            if ts:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return (datetime.now(timezone.utc) - dt).total_seconds() / 60
        except (json.JSONDecodeError, ValueError, OSError):
            pass
    return mtime_age


def main():
    cfg = json.loads(CONFIG.read_text())
    now = datetime.now(timezone.utc)
    breaches, checked = [], []
    for art in cfg.get("artifacts", []):
        path = ROOT / art["path"]
        rec = {"path": art["path"], "max_age_minutes": art["max_age_minutes"]}
        if art.get("weekdays_only") and now.weekday() >= 5:
            rec["status"] = "out-of-window"
            checked.append(rec)
            continue
        hours = art.get("active_hours_utc")
        if hours and now.hour not in hours:
            rec["status"] = "out-of-window"
            checked.append(rec)
            continue
        if not path.exists():
            rec.update({"status": "MISSING", "why": art.get("why", "")})
            breaches.append(rec)
            checked.append(rec)
            continue
        age = round(artifact_age_minutes(path), 1)
        rec["age_minutes"] = age
        if age > float(art["max_age_minutes"]):
            rec.update({"status": "STALE", "why": art.get("why", "")})
            breaches.append(rec)
        else:
            rec["status"] = "fresh"
        checked.append(rec)

    OUT.write_text(json.dumps({
        "ts": now.isoformat(),
        "breaches": breaches,
        "breach_count": len(breaches),
        "checked": checked,
    }, indent=2) + "\n")

    if breaches:
        print(f"FRESHNESS BREACH x{len(breaches)} — trading may be degraded/blocked:")
        for b in breaches:
            age = b.get("age_minutes", "n/a")
            print(f"  {b['status']}: {b['path']} (age {age}m, SLA {b['max_age_minutes']}m) — {b['why']}")
    else:
        active = sum(1 for c in checked if c["status"] == "fresh")
        print(f"all fresh ({active} active artifacts in SLA)")


if __name__ == "__main__":
    main()
