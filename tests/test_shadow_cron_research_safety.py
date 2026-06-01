import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts import dom_proxy_ohlcv, kalman_pairs, rolling_window_optimizer


def sample_ohlcv(rows: int = 140) -> pd.DataFrame:
    base = np.linspace(100.0, 125.0, rows)
    return pd.DataFrame({
        "ts": pd.date_range("2026-05-01", periods=rows, freq="h", tz="UTC"),
        "open": base,
        "high": base + 2.0,
        "low": base - 2.0,
        "close": base + np.sin(np.linspace(0.0, 12.0, rows)),
        "volume": np.full(rows, 1000),
    })


def assert_shadow_only(testcase: unittest.TestCase, payload: dict) -> None:
    testcase.assertTrue(payload["researchOnly"])
    testcase.assertFalse(payload["writesOrders"])
    testcase.assertFalse(payload["touchesBroker"])
    testcase.assertFalse(payload["tradable_signal"])
    testcase.assertFalse(payload["promoted_for_execution"])
    testcase.assertFalse(payload["readyForExecution"])
    testcase.assertEqual(payload["execution_role"], "diagnostic_only")
    testcase.assertIn("Research-only", payload["operator_read"])


class ShadowCronResearchSafetyTests(unittest.TestCase):
    def test_dom_proxy_is_explicit_proxy_shadow_only(self):
        payload = dom_proxy_ohlcv.compute_dom_proxy(sample_ohlcv())

        self.assertEqual(payload["method"], "OHLCV_DOM_proxy")
        self.assertEqual(payload["evidence_level"], "proxy_shadow_only")
        assert_shadow_only(self, payload)
        self.assertIn("not true DOM", payload["limitations"][0])
        self.assertIn("not true DOM", payload["operator_read"])
        self.assertTrue(payload["source_data_stale"])
        self.assertEqual(payload["stale_threshold_seconds"], 7200)

    def test_kalman_pairs_error_state_is_not_trade_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "kalman-pairs-signal.latest.json"
            with patch.object(kalman_pairs, "STATE_FILE", state_file), \
                 patch.object(kalman_pairs, "load_pair_data", side_effect=ValueError("missing aligned data")):
                with self.assertRaises(SystemExit) as caught:
                    kalman_pairs.main()

            self.assertEqual(caught.exception.code, 1)
            payload = json.loads(state_file.read_text())
            self.assertEqual(payload["direction"], "neutral")
            self.assertEqual(payload["method"], "kalman_dynamic_hedge")
            self.assertEqual(payload["evidence_level"], "research_shadow_only")
            assert_shadow_only(self, payload)
            self.assertIn("missing aligned data", payload["error"])
            self.assertIn("neutral/no-evidence", payload["operator_read"])

    def test_kalman_pairs_normal_state_is_shadow_only(self):
        rows = 140
        es = np.linspace(7000.0, 7100.0, rows)
        nq = es * 4.0 + np.sin(np.linspace(0.0, 8.0, rows)) * 10.0
        timestamps = np.array([
            pd.Timestamp("2026-05-01", tz="UTC").timestamp() + i * 3600
            for i in range(rows)
        ])

        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "kalman-pairs-signal.latest.json"
            with patch.object(kalman_pairs, "STATE_FILE", state_file), \
                 patch.object(kalman_pairs, "load_pair_data", return_value=(nq, es, timestamps)):
                kalman_pairs.main()

            payload = json.loads(state_file.read_text())
            self.assertEqual(payload["method"], "kalman_dynamic_hedge")
            self.assertEqual(payload["evidence_level"], "research_shadow_only")
            assert_shadow_only(self, payload)
            self.assertIn("does not authorize", payload["operator_read"])
            self.assertTrue(payload["source_data_stale"])
            self.assertEqual(payload["stale_threshold_seconds"], 7200)

    def test_rolling_window_output_is_shadow_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "rolling-window-params.latest.json"
            with patch.object(rolling_window_optimizer, "STATE_FILE", state_file), \
                 patch.object(rolling_window_optimizer, "fetch_recent_bars", return_value=sample_ohlcv()):
                rolling_window_optimizer.main()

            payload = json.loads(state_file.read_text())
            self.assertEqual(payload["evidence_level"], "research_shadow_only")
            assert_shadow_only(self, payload)
            self.assertIn("must not mutate live bridge parameters", payload["operator_read"])
            self.assertIn(payload["selected"], rolling_window_optimizer.WINDOW_CANDIDATES)
            self.assertTrue(payload["source_data_stale"])
            self.assertEqual(payload["stale_threshold_seconds"], 7200)


if __name__ == "__main__":
    unittest.main()
