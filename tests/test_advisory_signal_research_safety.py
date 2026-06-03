import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts import microstructure_filter, multitf_confirmation, vol_regime_gate


def assert_advisory_only(testcase: unittest.TestCase, payload: dict) -> None:
    testcase.assertTrue(payload["researchOnly"])
    testcase.assertFalse(payload["writesOrders"])
    testcase.assertFalse(payload["touchesBroker"])
    testcase.assertFalse(payload["tradable_signal"])
    testcase.assertFalse(payload["promoted_for_execution"])
    testcase.assertFalse(payload["readyForExecution"])
    testcase.assertEqual(payload["execution_role"], "diagnostic_only")


class AdvisorySignalResearchSafetyTests(unittest.TestCase):
    def test_vol_regime_success_is_advisory_only(self):
        rows = 60
        base = np.linspace(100.0, 120.0, rows)
        frame = pd.DataFrame({
            "High": base + 2.0,
            "Low": base - 2.0,
            "Close": base + 0.25,
        })

        class FakeTicker:
            def history(self, period, interval):
                return frame

        with patch.object(vol_regime_gate.yf, "Ticker", return_value=FakeTicker()):
            payload = vol_regime_gate.generate_signal(vol_regime_gate.DEFAULT_STATE_DIR)

        self.assertEqual(payload["signal_name"], "vol_regime_gate")
        self.assertIsNone(payload["error"])
        assert_advisory_only(self, payload)

    def test_vol_regime_empty_data_fails_advisory_only(self):
        class FakeTicker:
            def history(self, period, interval):
                return pd.DataFrame()

        with patch.object(vol_regime_gate.yf, "Ticker", return_value=FakeTicker()):
            payload = vol_regime_gate.generate_signal(vol_regime_gate.DEFAULT_STATE_DIR)

        self.assertEqual(payload["confidence"], 0.0)
        self.assertIsNotNone(payload["error"])
        assert_advisory_only(self, payload)

    def test_multitf_directional_output_is_not_tradable(self):
        closes_5m = np.linspace(100.0, 130.0, 60)
        closes_1m = np.linspace(129.0, 131.0, 20)

        with patch.object(multitf_confirmation, "fetch_bars", side_effect=[closes_5m, closes_1m]):
            payload = multitf_confirmation.compute_signal()

        self.assertEqual(payload["signal_name"], "multitf_confirmation")
        self.assertEqual(payload["direction"], 1)
        assert_advisory_only(self, payload)

    def test_multitf_fetch_error_is_advisory_only(self):
        with patch.object(multitf_confirmation, "fetch_bars", return_value=None):
            payload = multitf_confirmation.compute_signal()

        self.assertEqual(payload["direction"], 0)
        self.assertIsNotNone(payload["error"])
        assert_advisory_only(self, payload)

    def test_microstructure_proxy_success_is_advisory_only(self):
        index = pd.date_range("2026-06-01T13:30:00Z", periods=30, freq="min")
        frame = pd.DataFrame({
            "Open": np.linspace(100.0, 101.0, 30),
            "High": np.linspace(100.2, 101.2, 30),
            "Low": np.linspace(99.8, 100.8, 30),
            "Close": np.linspace(100.0, 101.5, 30),
            "Volume": np.full(30, 1000),
        }, index=index)

        payload = microstructure_filter.latest_signal(frame)

        self.assertEqual(payload["signal_name"], "microstructure_filter")
        self.assertIsNone(payload["error"])
        assert_advisory_only(self, payload)

    def test_microstructure_proxy_error_is_advisory_only(self):
        payload = microstructure_filter.with_advisory_contract({
            "timestamp": "2026-06-01T13:30:00+00:00",
            "direction": 0,
            "confidence": 0.0,
            "signal_name": "microstructure_filter",
            "details": {"filter_verdict": "NORMAL"},
            "error": "fixture",
        })

        self.assertEqual(payload["confidence"], 0.0)
        self.assertIsNotNone(payload["error"])
        assert_advisory_only(self, payload)


if __name__ == "__main__":
    unittest.main()
