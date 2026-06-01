import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from scripts import databento_realtime_smoke as smoke


class DatabentoRealtimeSmokeTests(unittest.TestCase):
    def test_no_quotes_is_research_only_and_not_failure_to_run(self):
        with patch.dict(os.environ, {}, clear=True):
            payload = smoke.build_report(
                timeout_seconds=0.01,
                fetcher=lambda **_kwargs: None,
                now=datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(payload["status"], "NO_QUOTES")
        self.assertFalse(payload["readyForExecutionDataProof"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["writesRealtimeQuoteState"])
        self.assertEqual(payload["safeEnv"]["BILL_ENABLE_FUTURES_DEMO_EXECUTION"], "false")
        self.assertEqual(payload["safeEnv"]["RH_TOPSTEP_READ_ONLY"], "true")
        self.assertEqual(payload["databentoProcessOptIn"]["BILL_DATABENTO_REALTIME_ENABLED"], "true")
        self.assertTrue(payload["session"]["likelyOpen"])

    def test_no_quotes_on_saturday_is_labeled_market_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            payload = smoke.build_report(
                timeout_seconds=0.01,
                fetcher=lambda **_kwargs: None,
                now=datetime(2026, 5, 30, 5, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(payload["status"], "NO_QUOTES_MARKET_CLOSED")
        self.assertFalse(payload["readyForExecutionDataProof"])
        self.assertFalse(payload["session"]["likelyOpen"])
        self.assertIn("Saturday", payload["quoteSummary"]["reason"])

    def test_execution_grade_databento_quotes_mark_data_proof_ready(self):
        quote = {
            "source": "databento_realtime",
            "execution_grade": True,
            "execution_block_reason": None,
            "price_nq": 30405.25,
            "price_es": 7595.75,
            "bid_nq": 30405.0,
            "ask_nq": 30405.5,
            "bid_es": 7595.5,
            "ask_es": 7596.0,
            "event_ts_nq": "2026-05-30T05:00:00+00:00",
            "event_ts_es": "2026-05-30T05:00:00+00:00",
            "latency_ms": 100,
            "databento_dataset": "GLBX.MDP3",
            "databento_schema": "mbp-1",
        }

        with patch.dict(os.environ, {}, clear=True):
            payload = smoke.build_report(timeout_seconds=0.01, fetcher=lambda **_kwargs: quote)

        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["readyForExecutionDataProof"])
        self.assertTrue(payload["quoteSummary"]["bidAskNqPresent"])
        self.assertTrue(payload["quoteSummary"]["bidAskEsPresent"])
        self.assertIn("does not approve trading", payload["promotionRule"])

    def test_report_restores_databento_env_after_temporary_opt_in(self):
        with patch.dict(os.environ, {
            "BILL_DATABENTO_REALTIME_ENABLED": "false",
            "BILL_DATABENTO_DATASET": "CUSTOM.DATASET",
        }, clear=True):
            payload = smoke.build_report(
                timeout_seconds=0.01,
                fetcher=lambda **_kwargs: None,
                now=datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(payload["databentoProcessOptIn"]["BILL_DATABENTO_REALTIME_ENABLED"], "false")
            self.assertEqual(payload["databentoProcessOptIn"]["BILL_DATABENTO_DATASET"], "CUSTOM.DATASET")
            self.assertEqual(os.environ["BILL_DATABENTO_REALTIME_ENABLED"], "false")
            self.assertEqual(os.environ["BILL_DATABENTO_DATASET"], "CUSTOM.DATASET")
            self.assertNotIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION", os.environ)
            self.assertNotIn("RH_TOPSTEP_READ_ONLY", os.environ)
            self.assertNotIn("RH_LIVE_EXECUTION_ENABLED", os.environ)


if __name__ == "__main__":
    unittest.main()
