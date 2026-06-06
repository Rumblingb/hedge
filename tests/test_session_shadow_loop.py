import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import (
    session_shadow_postmarket as postmarket,
    session_shadow_premarket as premarket,
    session_shadow_trade_logger as logger,
)


class SessionShadowLoopTests(unittest.TestCase):
    def test_premarket_shadow_is_research_only_and_regular_monday(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            shadow_dir = state / "session-shadows"
            state.mkdir()
            (state / "realtime-quote.latest.json").write_text(json.dumps({
                "bid_nq": 30000.0,
                "ask_nq": 30000.5,
                "price_nq": 30000.25,
                "source": "topstep_realtime",
                "execution_grade": True,
                "timestamp": "2026-06-08T13:25:00+00:00",
            }))

            with patch.object(premarket, "STATE", state), patch.object(premarket, "SHADOW_DIR", shadow_dir):
                payload = premarket.build_premarket_shadow(
                    datetime(2026, 6, 8, 13, 25, tzinfo=timezone.utc)
                )

            self.assertEqual(payload["session_date"], "2026-06-08")
            self.assertEqual(payload["session_type"], "regular")
            self.assertTrue(payload["researchOnly"])
            self.assertFalse(payload["writesOrders"])
            self.assertFalse(payload["touchesBroker"])
            self.assertFalse(payload["readyForExecution"])
            self.assertEqual(0, payload["plan"]["max_algo_contracts"])
            self.assertEqual(1, payload["plan"]["max_manual_watch_contracts_if_daily_and_broker_cleared"])
            self.assertTrue((shadow_dir / "session-2026-06-08.json").exists())

    def test_trade_logger_closes_shadow_and_journal_consistently(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            shadow_dir = state / "session-shadows"
            shadow_dir.mkdir()
            shadow_path = shadow_dir / "session-2026-06-08.json"
            shadow_path.write_text(json.dumps({"session_date": "2026-06-08", "trades": []}))
            journal = state / "trade-journal.latest.json"

            class FixedEntryDateTime:
                @classmethod
                def now(cls, tz=None):
                    return datetime(2026, 6, 8, 14, 35, tzinfo=timezone.utc)

            class FixedExitDateTime:
                @classmethod
                def now(cls, tz=None):
                    return datetime(2026, 6, 8, 14, 45, tzinfo=timezone.utc)

            with patch.object(logger, "STATE", state), \
                    patch.object(logger, "SHADOW_DIR", shadow_dir), \
                    patch.object(logger, "JOURNAL_PATH", journal), \
                    patch.object(logger, "datetime", FixedEntryDateTime):
                self.assertTrue(logger.log_trade({"side": "long", "entry": 30000.0, "symbol": "MNQ"}))

            with patch.object(logger, "STATE", state), \
                    patch.object(logger, "SHADOW_DIR", shadow_dir), \
                    patch.object(logger, "JOURNAL_PATH", journal), \
                    patch.object(logger, "datetime", FixedExitDateTime):
                self.assertTrue(logger.close_trade(30012.5))

            shadow = json.loads(shadow_path.read_text())
            rows = json.loads(journal.read_text())
            self.assertEqual(12.5, shadow["trades"][0]["points"])
            self.assertEqual("win", shadow["trades"][0]["outcome"])
            self.assertEqual(12.5, rows[0]["points"])
            self.assertEqual("win", rows[0]["outcome"])
            self.assertTrue(rows[0]["researchOnly"])

    def test_postmarket_filters_to_current_session_and_writes_memory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            shadow_dir = state / "session-shadows"
            obsidian = root / "obsidian"
            (obsidian / "daily").mkdir(parents=True)
            shadow_dir.mkdir(parents=True)
            (shadow_dir / "session-2026-06-08.json").write_text(json.dumps({
                "session_date": "2026-06-08",
                "session_type": "regular",
                "plan": {"bias": "neutral"},
            }))
            (state / "trade-journal.latest.json").write_text(json.dumps([
                {"entry_time": "2026-06-07T14:35:00+00:00", "side": "long", "entry": 1, "points": 99},
                {"entry_time": "2026-06-08T14:35:00+00:00", "side": "short", "entry": 30000, "points": -5},
            ]))

            with patch.object(postmarket, "STATE", state), \
                    patch.object(postmarket, "SHADOW_DIR", shadow_dir), \
                    patch.object(postmarket, "OBSIDIAN_HERMES", obsidian):
                payload = postmarket.build_postmarket_shadow(
                    datetime(2026, 6, 8, 20, 0, tzinfo=timezone.utc)
                )

            self.assertTrue(payload["researchOnly"])
            self.assertFalse(payload["writesOrders"])
            self.assertFalse(payload["touchesBroker"])
            self.assertEqual(1, payload["post_mortem"]["total_trades"])
            self.assertEqual(-5, payload["post_mortem"]["session_stats"]["net_points"])
            self.assertIn("LOSS -5.0 pts", (obsidian / "daily" / "2026-06-08.md").read_text())


if __name__ == "__main__":
    unittest.main()
