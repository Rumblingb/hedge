import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import scripts.noise_area_scalp as noise_area


class NoiseAreaScalpSafetyTest(unittest.TestCase):
    def test_stale_breakout_is_written_as_research_only_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "noise-area-signal.latest.json"
            raw_signal = {
                "entry_signal": "LONG_ENTRY",
                "direction": "long",
                "entry_price": 30348.25,
                "stop_loss": 30229.5,
                "tp1": 30363.25,
                "tp2": 30378.25,
                "trail_trigger_pts": noise_area.TRAIL_TRIGGER_PTS,
                "exit_signal": "HOLD",
                "max_contracts": noise_area.MAX_CONTRACTS,
                "scale_out": {
                    "tp1_pts": noise_area.TP1_PTS,
                    "tp1_contracts": 1,
                    "tp2_pts": noise_area.TP2_PTS,
                    "tp2_contracts": 1,
                    "trail_contracts": 1,
                },
            }
            fake_noise = {
                "bar_time": "2026-05-29T18:41:59+00:00",
                "session_open": 30269.0,
                "upper_boundary": 30333.0,
                "lower_boundary": 30229.5,
                "current_close": 30348.25,
                "current_high": 30350.0,
                "current_low": 30330.0,
                "avg_upper_dev": 54.0,
                "avg_lower_dev": 29.5,
                "buffer_pts": 10.0,
                "hist_days_used": 14,
                "vwap": 30311.6,
                "bar_index": 12,
            }

            with patch.object(noise_area, "STATE_FILE", state_file), patch.object(
                noise_area, "load_data", return_value=pd.DataFrame({"time": [datetime(2026, 5, 29, tzinfo=timezone.utc)]})
            ), patch.object(noise_area, "check_freshness", return_value=(False, datetime(2026, 5, 29, tzinfo=timezone.utc))), patch.object(
                noise_area, "get_session", return_value="asia"
            ), patch.object(
                noise_area, "compute_noise_area", return_value=fake_noise
            ), patch.object(
                noise_area, "generate_signal", return_value=raw_signal
            ):
                output = noise_area.run("NQ")

            self.assertIsNotNone(output)
            payload = json.loads(state_file.read_text())
            self.assertEqual(payload["entry_signal"], "HOLD")
            self.assertEqual(payload["direction"], "neutral")
            self.assertIsNone(payload["entry_price"])
            self.assertEqual(payload["raw_research_signal"]["entry_signal"], "LONG_ENTRY")
            self.assertEqual(payload["execution_block_reason"], "stale-data-research-only")
            self.assertTrue(payload["researchOnly"])
            self.assertFalse(payload["writesOrders"])
            self.assertFalse(payload["touchesBroker"])
            self.assertFalse(payload["tradable_signal"])
            self.assertFalse(payload["promoted_for_execution"])
            self.assertFalse(payload["readyForExecution"])

    def test_empty_state_is_never_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "noise-area-signal.latest.json"
            with patch.object(noise_area, "STATE_FILE", state_file):
                noise_area._write_empty_state("outside_session")

            payload = json.loads(state_file.read_text())
            self.assertEqual(payload["entry_signal"], "HOLD")
            self.assertTrue(payload["researchOnly"])
            self.assertFalse(payload["writesOrders"])
            self.assertFalse(payload["touchesBroker"])
            self.assertFalse(payload["readyForExecution"])


if __name__ == "__main__":
    unittest.main()
