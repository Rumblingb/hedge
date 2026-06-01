import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.pipeline_monitor as monitor


class PipelineMonitorQuoteQualityTests(unittest.TestCase):
    def write_quote(self, tmp_path: Path, payload: dict):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "realtime-quote.latest.json").write_text(json.dumps(payload))
        return state_dir

    def test_tradingview_delayed_stream_is_flagged_not_execution_grade(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = self.write_quote(Path(tmp), {
                "source": "tradingview_pro",
                "price_nq": 30405.25,
                "price_es": 7595.75,
                "update_mode_nq": "delayed_streaming_600",
                "update_mode_es": "delayed_streaming_600",
            })
            with patch.object(monitor, "ALL_STATE_DIRS", [state_dir]):
                result = monitor.check_realtime_quote_quality()

        self.assertEqual(result["status"], "WARNING")
        self.assertEqual(result["issues"][0]["type"], "NON_EXECUTION_GRADE_QUOTE")
        self.assertIn("delayed_streaming_600", result["issues"][0]["description"])

    def test_realtime_allowlisted_source_has_no_quality_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = self.write_quote(Path(tmp), {
                "source": "tradingview_ws",
                "price_nq": 30405.25,
                "price_es": 7595.75,
                "update_mode_nq": "realtime",
                "update_mode_es": "realtime",
            })
            with patch.object(monitor, "ALL_STATE_DIRS", [state_dir]):
                result = monitor.check_realtime_quote_quality()

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["issues"], [])


if __name__ == "__main__":
    unittest.main()
