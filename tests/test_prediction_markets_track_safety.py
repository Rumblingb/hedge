import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import prediction_markets_track


class PredictionMarketsTrackSafetyTests(unittest.TestCase):
    def test_lowered_thresholds_emit_watch_candidates_only(self):
        signal = prediction_markets_track.analyze_opportunity(
            {"price": 0.45, "edge": 0.02, "eventTitle": "Test event", "displayedSize": 1000},
            "arbitrage",
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal["action"], "watch-buy-candidate")
        self.assertTrue(signal["watchCandidateOnly"])
        self.assertFalse(signal["paperCandidateOnly"])
        self.assertLessEqual(signal["stake"], 10)

    def test_execution_track_report_is_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            journal = Path(tmp) / "opportunities.jsonl"
            journal.write_text('{"price": 0.45, "edge": 0.02, "eventTitle": "Test", "displayedSize": 1000}\n')
            output = state_dir / "prediction-markets-research-track.latest.json"

            with patch.object(prediction_markets_track, "STATE_DIR", state_dir):
                with patch.object(prediction_markets_track, "JOURNAL_PATH", journal):
                    with patch.object(prediction_markets_track, "PM_STATE", output):
                        prediction_markets_track.execute_prediction_track()

            payload = output.read_text()

        self.assertIn('"researchOnly": true', payload)
        self.assertIn('"writesOrders": false', payload)
        self.assertIn('"touchesBroker": false', payload)
        self.assertIn('"readyForExecution": false', payload)
        self.assertIn("watch-buy-candidate", payload)
        self.assertIn('"thresholdMode": "exploratory-watch-only"', payload)
        self.assertIn('"per_trade_max": 10', payload)


if __name__ == "__main__":
    unittest.main()
