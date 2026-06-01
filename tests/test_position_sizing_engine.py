import json
import tempfile
import unittest
from pathlib import Path

from scripts.position_sizing_engine import DEFAULT_STATE_DIR, REPO_ROOT, compute_sizing


class PositionSizingEngineTests(unittest.TestCase):
    def test_default_state_dir_is_repo_local(self):
        self.assertEqual(DEFAULT_STATE_DIR, REPO_ROOT / ".rumbling-hedge/state")

    def test_missing_signal_fails_closed_to_zero_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = compute_sizing(Path(tmp), balance_override=100000)

        self.assertEqual(result["recommended_contracts"], 0)
        self.assertEqual(result["direction"], 0)
        self.assertIn("confidence", result["gates"]["confidence_gate"])

    def test_valid_signal_can_recommend_size_inside_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "risk-aware-sizing.latest.json").write_text(json.dumps({
                "confidence": 0.8,
                "details": {
                    "signal_strength": 0.5,
                    "regime": "normal"
                }
            }))
            result = compute_sizing(state_dir, balance_override=100000)

        self.assertGreaterEqual(result["recommended_contracts"], 1)
        self.assertLessEqual(result["recommended_contracts"], result["limits"]["max_contracts_mnq"])


if __name__ == "__main__":
    unittest.main()
