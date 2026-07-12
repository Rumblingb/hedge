import unittest
from datetime import datetime, timezone

from scripts import macro_context


class MacroContextDateTest(unittest.TestCase):
    def test_macro_calendar_uses_bill_trading_timezone(self):
        # 23:30 UTC on May 5 is already May 6 in Europe/London (FOMC Decision day).
        now = datetime(2026, 5, 5, 23, 30, tzinfo=timezone.utc)

        self.assertEqual(macro_context.current_trading_date(now).isoformat(), "2026-05-06")
        self.assertEqual(macro_context.today_events(now), "FOMC Decision")

    def test_next_events_start_from_trading_day(self):
        now = datetime(2026, 6, 9, 23, 30, tzinfo=timezone.utc)

        events = macro_context.next_3_days_events(now)

        self.assertEqual(events[0], {"date": "2026-06-10", "event": "CPI Release"})

    def test_macro_session_hour_handles_est_and_edt(self):
        self.assertEqual(macro_context.ny_hour(datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)), 9)
        self.assertEqual(macro_context.ny_hour(datetime(2026, 7, 6, 13, 30, tzinfo=timezone.utc)), 9)


if __name__ == "__main__":
    unittest.main()
