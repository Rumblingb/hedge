#!/usr/bin/env python3
"""Build deterministic USD red-folder calendar evidence for demo execution.

The public weekly XML response is archived, normalized events are written for
the TypeScript news gate, and a separate health artifact lets execution fail
closed when the feed is unavailable or stale. This script never touches a
broker or routes orders.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / ".rumbling-hedge" / "research" / "news"
STATE = ROOT / ".rumbling-hedge" / "state"
SOURCE_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
EVENTS_PATH = RESEARCH / "red-folder-events.json"
RAW_PATH = RESEARCH / "ff-calendar-thisweek.xml"
STATUS_PATH = STATE / "red-folder-calendar.latest.json"


def parse_event_time(date_text: str, time_text: str) -> datetime | None:
    try:
        stamp = datetime.strptime(
            f"{date_text.strip()} {time_text.strip().lower()}",
            "%m-%d-%Y %I:%M%p",
        )
        # The public weekly XML feed publishes event times in UTC.
        return stamp.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_calendar(raw: bytes, *, currency: str = "USD") -> tuple[list[dict[str, Any]], list[str]]:
    root = ET.fromstring(raw)
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    for node in root.findall("event"):
        country = (node.findtext("country") or "").strip().upper()
        if country != currency.upper():
            continue
        title = (node.findtext("title") or "").strip()
        impact_raw = (node.findtext("impact") or "").strip().lower()
        impact = impact_raw if impact_raw in {"high", "medium", "low"} else "low"
        event_time = parse_event_time(node.findtext("date") or "", node.findtext("time") or "")
        if not title or event_time is None:
            warnings.append(f"ignored un-timed {currency} calendar row: {title or 'missing-title'}")
            continue
        events.append({
            "symbol": "NQ",
            "ts": event_time.isoformat(),
            "headline": title,
            "impact": impact,
            "direction": "flat",
            "probability": 1.0,
            "currency": country,
            "forecast": (node.findtext("forecast") or "").strip(),
            "previous": (node.findtext("previous") or "").strip(),
            "source": "Forex Factory public weekly calendar",
            "sourceUrl": (node.findtext("url") or "").strip(),
        })
    events.sort(key=lambda item: str(item["ts"]))
    return events, warnings


def fetch_calendar(url: str = SOURCE_URL, timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Bill-Hedge-RedFolder/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run(*, fixture: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    generated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    source = str(fixture) if fixture else SOURCE_URL
    try:
        raw = fixture.read_bytes() if fixture else fetch_calendar()
        events, warnings = parse_calendar(raw)
        RESEARCH.mkdir(parents=True, exist_ok=True)
        RAW_PATH.write_bytes(raw)
        write_json(EVENTS_PATH, {"generatedAt": generated.isoformat(), "source": source, "events": events})
        today = generated.date().isoformat()
        today_events = [item for item in events if str(item.get("ts", "")).startswith(today)]
        payload = {
            "command": "red-folder-calendar",
            "generatedAt": generated.isoformat(),
            "status": "PASS",
            "source": source,
            "currency": "USD",
            "eventCount": len(events),
            "todayEventCount": len(today_events),
            "highImpactToday": [item for item in today_events if item.get("impact") == "high"],
            "mediumImpactToday": [item for item in today_events if item.get("impact") == "medium"],
            "todayEvents": today_events,
            "warnings": warnings,
            "eventsPath": str(EVENTS_PATH),
            "rawPath": str(RAW_PATH),
            "researchOnly": False,
            "writesOrders": False,
            "touchesBroker": False,
        }
    except Exception as exc:
        payload = {
            "command": "red-folder-calendar",
            "generatedAt": generated.isoformat(),
            "status": "BLOCKED",
            "source": source,
            "blockers": [f"red-folder calendar fetch/parse failed: {exc}"],
            "eventCount": 0,
            "todayEventCount": 0,
            "todayEvents": [],
            "researchOnly": False,
            "writesOrders": False,
            "touchesBroker": False,
        }
    write_json(STATUS_PATH, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh USD red-folder calendar evidence.")
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    payload = run(fixture=args.fixture)
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
