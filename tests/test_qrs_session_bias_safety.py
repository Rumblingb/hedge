import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.qrs_session_bias as qrs


class QrsSessionBiasSafetyTest(unittest.TestCase):
    def test_stale_bias_is_written_as_research_only_neutral(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "qrs-bias-signal.latest.json"
            computed = {
                "signal": "bullish",
                "z_score": 2.3,
                "beta": 1.02,
                "r_squared": 0.88,
                "confidence": 1.4,
                "last_bar": "2026-05-29T20:00:00.000Z",
                "generated_at": "2026-05-31T00:00:00+00:00",
                "model": "RSRS_QRS_v1",
                **qrs.safety_metadata(),
            }

            with patch.object(qrs, "OUTPUT_FILE", output_file), patch.object(
                qrs, "load_data", return_value=[{"ts": "2026-05-29T20:00:00.000Z"}]
            ), patch.object(qrs, "compute_signal", return_value=computed):
                rc = qrs.main()

            self.assertEqual(rc, 0)
            payload = json.loads(output_file.read_text())
            self.assertEqual(payload["signal"], "neutral")
            self.assertFalse(payload["data_fresh"])
            self.assertEqual(payload["raw_research_signal"]["signal"], "bullish")
            self.assertEqual(payload["execution_block_reason"], "stale-data-research-only")
            self.assertTrue(payload["researchOnly"])
            self.assertFalse(payload["writesOrders"])
            self.assertFalse(payload["touchesBroker"])
            self.assertFalse(payload["tradable_signal"])
            self.assertFalse(payload["promoted_for_execution"])
            self.assertFalse(payload["readyForExecution"])

    def test_insufficient_data_result_is_never_actionable(self):
        result = qrs.compute_signal([{"low": 1, "high": 2, "ts": "2026-05-29T20:00:00.000Z"}])

        self.assertEqual(result["signal"], "neutral")
        self.assertTrue(result["researchOnly"])
        self.assertFalse(result["writesOrders"])
        self.assertFalse(result["touchesBroker"])
        self.assertFalse(result["readyForExecution"])


if __name__ == "__main__":
    unittest.main()
