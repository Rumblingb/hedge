import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json

from scripts import new_arsenal_gate, pre_trade_check, session_trader


class NySessionTimezoneTest(unittest.TestCase):
    def test_pre_trade_ny_minutes_handles_est_and_edt(self):
        self.assertEqual(pre_trade_check.ny_minutes(datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)), 570)
        self.assertEqual(pre_trade_check.ny_minutes(datetime(2026, 7, 6, 13, 30, tzinfo=timezone.utc)), 570)

    def test_session_trader_ny_minutes_handles_est_and_edt(self):
        self.assertEqual(session_trader.ny_minutes(datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)), 570)
        self.assertEqual(session_trader.ny_minutes(datetime(2026, 7, 6, 13, 30, tzinfo=timezone.utc)), 570)

    def test_session_trader_fails_closed_without_recent_data(self):
        with patch.object(session_trader, "fetch_nq_bars", return_value={}), patch("sys.stdout", new_callable=StringIO) as out:
            result = session_trader.run()
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertIn("hardcoded fallback disabled", out.getvalue())

    def test_new_arsenal_gate_ignores_unpromoted_research_overlays(self):
        with TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "ichimoku-signal.latest.json").write_text(json.dumps({"trend": "bullish"}))
            (state_dir / "donchian-signal.latest.json").write_text(json.dumps({"direction": "long"}))
            (state_dir / "pead-signal.latest.json").write_text(json.dumps({"nq_bias": "bullish", "confidence": 1.0}))
            (state_dir / "sr-proximity-signal.latest.json").write_text(json.dumps({"direction": "long", "confidence": 1.0}))
            (state_dir / "insider-signal.latest.json").write_text(json.dumps({"nq_bias": "bearish", "confidence": 1.0}))
            with patch.object(new_arsenal_gate, "STATE_DIR", state_dir):
                result = new_arsenal_gate.new_arsenal_gate({"side": "long"})
        self.assertEqual(result["confidence_modifier"], 1.0)
        self.assertIn("Ichimoku is research-only; ignored for execution sizing", result["reasons"])
        self.assertIn("Donchian breakout is research-only; ignored for execution sizing", result["reasons"])
        self.assertIn("PEAD is research-only; ignored for execution sizing", result["reasons"])
        self.assertIn("S/R proximity is research-only; ignored for execution sizing", result["reasons"])
        self.assertIn("Insider flow is research-only; ignored for execution sizing", result["reasons"])


if __name__ == "__main__":
    unittest.main()
