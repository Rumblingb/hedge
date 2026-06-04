import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts import dom_edge_bridge, dom_proxy_ohlcv, kalman_pairs, rolling_window_optimizer


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

    def test_dom_proxy_prefers_topstep_archive_for_current_nq_bars(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "NQ-1m-topstep-readonly.csv"
            rows = sample_ohlcv(500).copy()
            rows["symbol"] = "NQ"
            rows["source"] = "topstep-readonly-market-data"
            rows["contractId"] = "CON.F.US.ENQ.M26"
            rows.to_csv(archive, index=False)

            with patch.object(dom_proxy_ohlcv, "TOPSTEP_NQ_ARCHIVE", archive):
                bars = dom_proxy_ohlcv.load_bars()

        self.assertEqual(bars.attrs["source_data_provider"], "topstep-readonly-market-data")
        self.assertEqual(bars.attrs["bar_timeframe"], "15min")
        self.assertGreaterEqual(len(bars), 30)

    def test_dom_proxy_thin_archive_emits_finite_neutral_scores(self):
        payload = dom_proxy_ohlcv.compute_dom_proxy(sample_ohlcv(46))

        self.assertTrue(np.isfinite(payload["current_price_z"]))
        self.assertTrue(np.isfinite(payload["current_delta_z"]))
        self.assertTrue(np.isfinite(payload["divergence"]))
        assert_shadow_only(self, payload)

    def test_dom_edge_bridge_converts_proxy_to_canonical_research_only_edge(self):
        proxy = {
            "timestamp": "2026-06-04T12:00:00+00:00",
            "method": "OHLCV_DOM_proxy",
            "evidence_level": "proxy_shadow_only",
            "source_data_provider": "topstep-readonly-market-data",
            "source_data_stale": False,
            "current_clv": 0.5,
            "current_price_z": -2.5,
            "current_delta_z": -0.5,
            "signals": [
                {"type": "bullish_divergence", "strength": 0.8, "desc": "test"},
            ],
        }

        payload = dom_edge_bridge.convert_to_dom_edge(proxy)

        self.assertIn("OFI LONG", payload["signals"])
        self.assertIn("VWAP_DEVIATION_LONG", payload["signals"])
        self.assertTrue(payload["researchOnly"])
        self.assertTrue(payload["proxyOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["tradable_signal"])
        self.assertFalse(payload["promoted_for_execution"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual("diagnostic_only", payload["execution_role"])
        self.assertEqual("OHLCV_DOM_proxy", payload["source_method"])
        self.assertEqual("proxy_shadow_only", payload["source_evidence_level"])

    def test_dom_edge_bridge_defaults_to_canonical_repo_state(self):
        self.assertEqual(dom_edge_bridge.STATE_DIR, dom_edge_bridge.ROOT / ".rumbling-hedge" / "state")
        self.assertNotEqual(dom_edge_bridge.STATE_DIR, Path.home() / ".rumbling-hedge" / "state")

    def test_dom_proxy_main_writes_canonical_dom_edge_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "dom-proxy-signal.latest.json"
            dom_edge_file = Path(tmp) / "dom_micro_edges.json"
            with patch.object(dom_proxy_ohlcv, "STATE_FILE", state_file), \
                    patch.object(dom_proxy_ohlcv, "write_dom_edge_file", lambda signal, *args, **kwargs: dom_edge_bridge.write_dom_edge_file(signal, dom_edge_file, source_path=kwargs["source_path"])), \
                    patch.object(dom_proxy_ohlcv, "load_bars", return_value=sample_ohlcv()):
                dom_proxy_ohlcv.main()

            proxy = json.loads(state_file.read_text())
            edge = json.loads(dom_edge_file.read_text())

        self.assertEqual(proxy["method"], "OHLCV_DOM_proxy")
        self.assertTrue(edge["researchOnly"])
        self.assertTrue(edge["proxyOnly"])
        self.assertFalse(edge["writesOrders"])
        self.assertIn("signals", edge)

    def test_kalman_pairs_error_state_is_not_trade_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "kalman-pairs-signal.latest.json"
            with patch.object(kalman_pairs, "STATE_FILE", state_file), \
                 patch.object(kalman_pairs, "load_pair_data", side_effect=ValueError("missing aligned data")):
                kalman_pairs.main()

            payload = json.loads(state_file.read_text())
            self.assertEqual(payload["action"], "NO_EVIDENCE")
            self.assertEqual(payload["direction"], "neutral")
            self.assertEqual(payload["method"], "kalman_dynamic_hedge")
            self.assertEqual(payload["evidence_level"], "research_shadow_only")
            self.assertTrue(payload["source_data_stale"])
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

    def test_rolling_window_prefers_topstep_archive_for_current_nq_bars(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "NQ-1m-topstep-readonly.csv"
            rows = sample_ohlcv(500).copy()
            rows["symbol"] = "NQ"
            rows["source"] = "topstep-readonly-market-data"
            rows["contractId"] = "CON.F.US.ENQ.M26"
            rows.to_csv(archive, index=False)

            with patch.object(rolling_window_optimizer, "TOPSTEP_NQ_ARCHIVE", archive):
                bars = rolling_window_optimizer.fetch_recent_bars()

        self.assertIsNotNone(bars)
        assert bars is not None
        self.assertEqual(bars.attrs["source_data_provider"], "topstep-readonly-market-data")
        self.assertEqual(bars.attrs["bar_timeframe"], "15min")
        self.assertGreaterEqual(len(bars), 30)


if __name__ == "__main__":
    unittest.main()
