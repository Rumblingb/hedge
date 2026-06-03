import json
import tempfile
import unittest
from pathlib import Path

from scripts.position_sizing_engine import (
    DEFAULT_STATE_DIR,
    POINT_VALUE_MNQ,
    POINT_VALUE_NQ,
    REPO_ROOT,
    compute_sizing,
    point_value_for_instrument,
)


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

    def test_mnq_point_value_is_two_dollars_per_point(self):
        self.assertEqual(POINT_VALUE_MNQ, 2.0)
        self.assertEqual(POINT_VALUE_NQ, 20.0)
        self.assertEqual(point_value_for_instrument("MNQ"), 2.0)
        self.assertEqual(point_value_for_instrument("NQ"), 20.0)

    def test_result_surfaces_point_value_used_for_risk(self):
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

        self.assertEqual(result["limits"]["instrument"], "MNQ")
        self.assertEqual(result["limits"]["point_value"], 2.0)


if __name__ == "__main__":
    unittest.main()
