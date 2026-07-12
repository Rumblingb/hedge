from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import red_folder_calendar


FIXTURE = b"""<?xml version='1.0'?>
<weeklyevents>
  <event><title>CPI m/m</title><country>USD</country><date>06-24-2026</date><time>12:30pm</time><impact>High</impact><forecast>0.2%</forecast><previous>0.3%</previous><url>https://example.test/cpi</url></event>
  <event><title>New Home Sales</title><country>USD</country><date>06-24-2026</date><time>2:00pm</time><impact>Low</impact><url>https://example.test/homes</url></event>
  <event><title>Other currency</title><country>EUR</country><date>06-24-2026</date><time>1:00pm</time><impact>High</impact></event>
</weeklyevents>"""


def test_parse_calendar_normalizes_usd_events_to_utc():
    events, warnings = red_folder_calendar.parse_calendar(FIXTURE)
    assert warnings == []
    assert len(events) == 2
    assert events[0]["headline"] == "CPI m/m"
    assert events[0]["ts"] == "2026-06-24T12:30:00+00:00"
    assert events[0]["impact"] == "high"


def test_fixture_run_writes_fresh_status_and_execution_feed():
    with TemporaryDirectory() as raw:
        root = Path(raw)
        fixture = root / "calendar.xml"
        fixture.write_bytes(FIXTURE)
        old_research, old_state = red_folder_calendar.RESEARCH, red_folder_calendar.STATE
        old_events, old_raw, old_status = red_folder_calendar.EVENTS_PATH, red_folder_calendar.RAW_PATH, red_folder_calendar.STATUS_PATH
        try:
            red_folder_calendar.RESEARCH = root / "research"
            red_folder_calendar.STATE = root / "state"
            red_folder_calendar.EVENTS_PATH = red_folder_calendar.RESEARCH / "red-folder-events.json"
            red_folder_calendar.RAW_PATH = red_folder_calendar.RESEARCH / "calendar.xml"
            red_folder_calendar.STATUS_PATH = red_folder_calendar.STATE / "red-folder-calendar.latest.json"
            payload = red_folder_calendar.run(
                fixture=fixture,
                now=datetime(2026, 6, 24, 11, 0, tzinfo=timezone.utc),
            )
            assert payload["status"] == "PASS"
            assert payload["todayEventCount"] == 2
            assert len(payload["highImpactToday"]) == 1
            assert red_folder_calendar.EVENTS_PATH.exists()
            assert red_folder_calendar.STATUS_PATH.exists()
        finally:
            red_folder_calendar.RESEARCH, red_folder_calendar.STATE = old_research, old_state
            red_folder_calendar.EVENTS_PATH, red_folder_calendar.RAW_PATH, red_folder_calendar.STATUS_PATH = old_events, old_raw, old_status
