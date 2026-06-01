import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from scripts import databento_orderflow_feature_smoke as smoke


class DatabentoOrderflowFeatureSmokeTests(unittest.TestCase):
    def test_no_quotes_stays_research_only_and_separate_from_realtime_state(self):
        with patch.dict(os.environ, {}, clear=True):
            payload = smoke.build_report(
                timeout_seconds=0.01,
                fetcher=lambda **_kwargs: None,
                now=datetime(2026, 5, 30, 5, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(payload["status"], "NO_QUOTES_MARKET_CLOSED")
        self.assertEqual(payload["decision"], "research-only-orderflow-feature-visible-execution-locked")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["writesRealtimeQuoteState"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["features"]["researchUsable"])
        self.assertFalse(payload["features"]["domProxyReplacementReady"])
        self.assertEqual(payload["safeEnv"]["BILL_ENABLE_FUTURES_DEMO_EXECUTION"], "false")
        self.assertEqual(payload["databentoProcessOptIn"]["BILL_DATABENTO_REALTIME_ENABLED"], "true")

    def test_execution_grade_bid_ask_depth_creates_snapshot_features_only(self):
        quote = {
            "source": "databento_realtime",
            "execution_grade": True,
            "execution_block_reason": None,
            "price_nq": 30405.25,
            "price_es": 7595.75,
            "bid_nq": 30405.0,
            "ask_nq": 30405.5,
            "bid_size_nq": 11,
            "ask_size_nq": 9,
            "bid_es": 7595.5,
            "ask_es": 7596.0,
            "bid_size_es": 4,
            "ask_size_es": 6,
            "event_ts_nq": "2026-05-30T05:00:00+00:00",
            "event_ts_es": "2026-05-30T05:00:00+00:00",
            "latency_ms": 100,
        }

        with patch.dict(os.environ, {}, clear=True):
            payload = smoke.build_report(timeout_seconds=0.01, fetcher=lambda **_kwargs: quote)

        self.assertEqual(payload["status"], "WATCH_RESEARCH_ONLY")
        self.assertFalse(payload["readyForExecution"])
        self.assertTrue(payload["features"]["researchUsable"])
        self.assertTrue(payload["features"]["snapshotOnly"])
        self.assertFalse(payload["features"]["domProxyReplacementReady"])
        rows = {row["symbol"]: row for row in payload["features"]["rows"]}
        self.assertEqual(rows["NQ"]["spread"], 0.5)
        self.assertEqual(rows["NQ"]["level1SizeImbalance"], 0.1)
        self.assertEqual(rows["ES"]["level1SizeImbalance"], -0.2)
        self.assertIn("OOS comparison", payload["promotionRule"])

    def test_execution_grade_without_depth_is_research_usable_but_not_imbalance_ready(self):
        quote = {
            "source": "databento_realtime",
            "execution_grade": True,
            "price_nq": 30405.25,
            "price_es": 7595.75,
            "bid_nq": 30405.0,
            "ask_nq": 30405.5,
            "bid_es": 7595.5,
            "ask_es": 7596.0,
        }

        payload = smoke.build_report(timeout_seconds=0.01, fetcher=lambda **_kwargs: quote)

        self.assertEqual(payload["status"], "WATCH_RESEARCH_ONLY")
        self.assertTrue(payload["features"]["researchUsable"])
        self.assertFalse(payload["features"]["completeDepthSize"])
        self.assertIsNone(payload["features"]["rows"][0]["level1SizeImbalance"])

    def test_report_restores_databento_env_after_temporary_opt_in(self):
        with patch.dict(os.environ, {
            "BILL_DATABENTO_REALTIME_ENABLED": "false",
            "BILL_DATABENTO_SCHEMA": "custom-schema",
        }, clear=True):
            payload = smoke.build_report(
                timeout_seconds=0.01,
                fetcher=lambda **_kwargs: None,
                now=datetime(2026, 5, 30, 5, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(payload["databentoProcessOptIn"]["BILL_DATABENTO_REALTIME_ENABLED"], "false")
            self.assertEqual(payload["databentoProcessOptIn"]["BILL_DATABENTO_SCHEMA"], "custom-schema")
            self.assertEqual(os.environ["BILL_DATABENTO_REALTIME_ENABLED"], "false")
            self.assertEqual(os.environ["BILL_DATABENTO_SCHEMA"], "custom-schema")
            self.assertNotIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION", os.environ)
            self.assertNotIn("RH_TOPSTEP_READ_ONLY", os.environ)
            self.assertNotIn("RH_LIVE_EXECUTION_ENABLED", os.environ)


if __name__ == "__main__":
    unittest.main()
