import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import databento_realtime_smoke as smoke
from scripts import realtime_data_bridge as bridge


class Header:
    def __init__(self, instrument_id=1, ts_event=1_780_000_000_000_000_000):
        self.instrument_id = instrument_id
        self.ts_event = ts_event


class Level:
    def __init__(self, bid_px, ask_px, bid_sz=1, ask_sz=1):
        self.bid_px = bid_px
        self.ask_px = ask_px
        self.bid_sz = bid_sz
        self.ask_sz = ask_sz


class MboLikeRecord:
    def __init__(self, instrument_id, bid_px, ask_px):
        self.hd = Header(instrument_id=instrument_id)
        self.levels = [Level(bid_px=bid_px, ask_px=ask_px)]


class FakeLiveClient:
    def __init__(self, key):
        self.key = key
        self.symbology_map = {
            1: {"stype_in_symbol": "NQ.v.0", "stype_out_symbol": "NQM6"},
            2: ["ES.v.0", "ESM6"],
        }
        self.callback = None
        self.subscriptions = []

    def add_callback(self, callback):
        self.callback = callback

    def subscribe(self, **kwargs):
        self.subscriptions.append(kwargs)

    def start(self):
        self.callback(MboLikeRecord(1, 30_405_000_000_000, 30_405_500_000_000))
        self.callback(MboLikeRecord(2, 7_595_500_000_000, 7_596_000_000_000))

    def stop(self):
        pass


class DatabentoRealtimeSmokeTests(unittest.TestCase):
    def test_process_databento_env_overrides_bill_env_for_data_only_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "bill.env"
            env_file.write_text(
                "\n".join([
                    "DATABENTO_API_KEY=from-file",
                    "BILL_DATABENTO_REALTIME_ENABLED=false",
                    "BILL_DATABENTO_DATASET=FILE.DATASET",
                ])
            )
            with patch.object(bridge, "BILL_ENV", env_file), patch.dict(os.environ, {
                "DATABENTO_API_KEY": "from-process",
                "BILL_DATABENTO_REALTIME_ENABLED": "true",
                "BILL_DATABENTO_DATASET": "PROCESS.DATASET",
            }, clear=True):
                env = bridge.load_databento_env()

        self.assertEqual(env["DATABENTO_API_KEY"], "from-process")
        self.assertEqual(env["BILL_DATABENTO_REALTIME_ENABLED"], "true")
        self.assertEqual(env["BILL_DATABENTO_DATASET"], "PROCESS.DATASET")

    def test_bridge_maps_header_instrument_id_via_symbology_map(self):
        with patch.dict(os.environ, {
            "BILL_DATABENTO_REALTIME_ENABLED": "true",
            "DATABENTO_API_KEY": "secret",
        }, clear=True):
            quote = bridge.fetch_databento_realtime(
                quiet=True,
                client_factory=FakeLiveClient,
                timeout_seconds=0.01,
            )

        self.assertIsNotNone(quote)
        self.assertEqual(quote["source"], "databento_realtime")
        self.assertTrue(quote["execution_grade"])
        self.assertEqual(quote["price_nq"], 30405.25)
        self.assertEqual(quote["price_es"], 7595.75)
        self.assertEqual(quote["databento_diagnostic"]["quotes_seen"], ["es", "nq"])
        self.assertGreaterEqual(quote["databento_diagnostic"]["records_with_symbol"], 2)

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
        self.assertEqual(payload["quoteSummary"]["diagnostic"], {})

    def test_no_quotes_reason_surfaces_databento_request_error(self):
        summary = smoke.summarize_quote(
            None,
            {"likelyOpen": True},
            {"errors": ["Unable to submit the request because there is an unpaid invoice."]},
        )

        self.assertEqual(summary["status"], "NO_QUOTES")
        self.assertIn("unpaid invoice", summary["reason"])

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
        self.assertEqual(payload["quoteSummary"]["diagnostic"], {})
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
