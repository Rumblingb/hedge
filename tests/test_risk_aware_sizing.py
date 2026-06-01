import json
import tempfile
import unittest
from pathlib import Path

from scripts.risk_aware_sizing import compute_sizing


class RiskAwareSizingTests(unittest.TestCase):
    def test_missing_noise_fails_closed_to_zero_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "arbitration.latest.json").write_text(json.dumps({
                "symbol": "NQ",
                "weighted_dir": -0.8,
            }))

            signal = compute_sizing(state_dir)

        self.assertEqual(signal["details"]["recommended_contracts"], 0.0)
        self.assertEqual(signal["confidence"], 0.0)
        self.assertTrue(signal["details"]["fail_closed"])
        self.assertTrue(signal["researchOnly"])
        self.assertFalse(signal["writesOrders"])
        self.assertFalse(signal["touchesBroker"])
        self.assertFalse(signal["tradable_signal"])
        self.assertFalse(signal["promoted_for_execution"])
        self.assertFalse(signal["readyForExecution"])
        self.assertIn("noise-analysis.latest.json not found or unreadable", signal["details"]["errors"])

    def test_valid_inputs_can_recommend_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "arbitration.latest.json").write_text(json.dumps({
                "symbol": "NQ",
                "weighted_dir": 0.03,
            }))
            (state_dir / "noise-analysis.latest.json").write_text(json.dumps({
                "details": {
                    "nq_noise": {
                        "current_nsr": 10.0,
                        "regime": "normal",
                    }
                }
            }))

            signal = compute_sizing(state_dir)

        self.assertFalse(signal["details"]["fail_closed"])
        self.assertGreater(signal["details"]["recommended_contracts"], 0)
        self.assertFalse(signal["readyForExecution"])


if __name__ == "__main__":
    unittest.main()
