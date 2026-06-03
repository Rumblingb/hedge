import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import scripts.realtime_data_bridge as bridge


class RealtimeDataBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.addCleanup(self.tmpdir.cleanup)

        self.original_paths = {
            "STATE_DIR": bridge.STATE_DIR,
            "LEGACY_STATE_DIR": bridge.LEGACY_STATE_DIR,
            "STATE_FILE": bridge.STATE_FILE,
            "LEGACY_STATE_FILE": bridge.LEGACY_STATE_FILE,
        }
        self.addCleanup(self.restore_paths)

        bridge.STATE_DIR = self.tmp_path
        bridge.LEGACY_STATE_DIR = self.tmp_path / "legacy"
        bridge.STATE_FILE = self.tmp_path / "realtime-quote.latest.json"
        bridge.LEGACY_STATE_FILE = bridge.LEGACY_STATE_DIR / "realtime-quote.latest.json"

    def restore_paths(self):
        for name, value in self.original_paths.items():
            setattr(bridge, name, value)

    def test_annotate_tradingview_pro_delayed_is_not_execution_grade(self):
        data = bridge.annotate_quote_quality({
            "source": "tradingview_pro",
            "price_nq": 30405.25,
            "price_es": 7595.75,
            "update_mode_nq": "delayed_streaming_600",
            "update_mode_es": "delayed_streaming_600",
        })

        self.assertEqual(data["source"], "tradingview_pro_delayed")
        self.assertEqual(data["original_source"], "tradingview_pro")
        self.assertFalse(data["execution_grade"])
        self.assertIn("delayed", data["execution_block_reason"])

    def test_check_state_freshness_fails_closed_on_fresh_delayed_quote(self):
        now = datetime.now(timezone.utc).isoformat()
        payload = bridge.annotate_quote_quality({
            "timestamp": now,
            "source": "tradingview_pro",
            "price_nq": 30405.25,
            "price_es": 7595.75,
            "update_mode_nq": "delayed_streaming_600",
            "update_mode_es": "delayed_streaming_600",
        })
        bridge.STATE_FILE.write_text(json.dumps(payload))

        result = bridge.check_state_freshness()

        self.assertFalse(result["fresh"])
        self.assertFalse(result["execution_grade"])
        self.assertIn("delayed", result["execution_block_reason"])

    def test_check_state_freshness_passes_on_allowlisted_realtime_quote(self):
        now = datetime.now(timezone.utc).isoformat()
        payload = bridge.annotate_quote_quality({
            "timestamp": now,
            "source": "tradingview_ws",
            "price_nq": 30405.25,
            "price_es": 7595.75,
            "update_mode_nq": "realtime",
            "update_mode_es": "realtime",
        })
        bridge.STATE_FILE.write_text(json.dumps(payload))

        result = bridge.check_state_freshness()

        self.assertTrue(result["fresh"])
        self.assertTrue(result["execution_grade"])
        self.assertIsNone(result["execution_block_reason"])

    def test_databento_realtime_is_default_disabled(self):
        called = False

        def fake_factory(**_kwargs):
            nonlocal called
            called = True
            raise AssertionError("client should not be constructed when disabled")

        with patch.dict(os.environ, {"DATABENTO_API_KEY": "test-key"}, clear=False), \
            patch.object(bridge, "BILL_ENV", self.tmp_path / "missing.env"):
            result = bridge.fetch_databento_realtime(quiet=True, client_factory=fake_factory, timeout_seconds=0.01)

        self.assertIsNone(result)
        self.assertFalse(called)

    def test_databento_realtime_fake_client_returns_execution_grade_quotes(self):
        class FakeClient:
            def __init__(self, key):
                self.key = key
                self.callback = None
                self.symbology_map = {
                    1: "NQ.v.0",
                    2: "ES.v.0",
                }
                self.subscribe_args = None
                self.started = False
                self.stopped = False

            def add_callback(self, callback):
                self.callback = callback

            def subscribe(self, **kwargs):
                self.subscribe_args = kwargs

            def start(self):
                self.started = True
                level_nq = SimpleNamespace(
                    bid_px=int(30405.00 * bridge.FIXED_PRICE_SCALE),
                    ask_px=int(30405.50 * bridge.FIXED_PRICE_SCALE),
                    bid_sz=11,
                    ask_sz=9,
                )
                level_es = SimpleNamespace(
                    bid_px=int(7595.50 * bridge.FIXED_PRICE_SCALE),
                    ask_px=int(7595.75 * bridge.FIXED_PRICE_SCALE),
                    bid_sz=4,
                    ask_sz=6,
                )
                self.callback(SimpleNamespace(instrument_id=1, levels=[level_nq], ts_event=1_780_000_000_000_000_000))
                self.callback(SimpleNamespace(instrument_id=2, levels=[level_es], ts_event=1_780_000_000_500_000_000))

            def stop(self):
                self.stopped = True

        instances = []

        def fake_factory(**kwargs):
            client = FakeClient(**kwargs)
            instances.append(client)
            return client

        with patch.dict(os.environ, {
            "BILL_DATABENTO_REALTIME_ENABLED": "true",
            "DATABENTO_API_KEY": "test-key",
        }, clear=False), patch.object(bridge, "BILL_ENV", self.tmp_path / "missing.env"):
            result = bridge.fetch_databento_realtime(quiet=True, client_factory=fake_factory, timeout_seconds=0.01)

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "databento_realtime")
        self.assertTrue(result["execution_grade"])
        self.assertIsNone(result["execution_block_reason"])
        self.assertEqual(result["price_nq"], 30405.25)
        self.assertEqual(result["price_es"], 7595.625)
        self.assertEqual(result["bid_nq"], 30405.0)
        self.assertEqual(result["bid_size_nq"], 11)
        self.assertEqual(result["ask_es"], 7595.75)
        self.assertEqual(result["ask_size_es"], 6)
        self.assertEqual(instances[0].subscribe_args["dataset"], bridge.DATABENTO_DATASET)
        self.assertEqual(instances[0].subscribe_args["schema"], bridge.DATABENTO_SCHEMA)
        self.assertEqual(instances[0].subscribe_args["stype_in"], "continuous")
        self.assertTrue(instances[0].started)
        self.assertTrue(instances[0].stopped)

    def test_databento_realtime_can_be_enabled_from_bill_env(self):
        class EmptyClient:
            def __init__(self, key):
                self.key = key
                self.symbology_map = {}

            def add_callback(self, _callback):
                pass

            def subscribe(self, **_kwargs):
                pass

            def start(self):
                pass

            def stop(self):
                pass

        bill_env = self.tmp_path / "bill.env"
        bill_env.write_text("\n".join([
            "DATABENTO_API_KEY=test-key",
            "BILL_DATABENTO_REALTIME_ENABLED=true",
        ]))
        instances = []

        def fake_factory(**kwargs):
            client = EmptyClient(**kwargs)
            instances.append(client)
            return client

        with patch.dict(os.environ, {}, clear=True), patch.object(bridge, "BILL_ENV", bill_env):
            result = bridge.fetch_databento_realtime(quiet=True, client_factory=fake_factory, timeout_seconds=0.01)

        self.assertIsNone(result)
        self.assertEqual(instances[0].key, "test-key")

    def test_databento_only_mode_does_not_write_fallback_state_when_no_databento_quote(self):
        with patch.object(bridge, "fetch_databento_realtime", return_value=None), \
            patch.object(bridge, "fetch_tv_websocket", side_effect=AssertionError("TV fallback should not run")), \
            patch.object(bridge, "fetch_yahoo_fallback", side_effect=AssertionError("Yahoo fallback should not run")), \
            patch.object(sys, "argv", ["realtime_data_bridge.py", "--quiet", "--databento-only"]):
            rc = bridge.main()

        self.assertEqual(rc, 1)
        self.assertFalse(bridge.STATE_FILE.exists())

    def test_databento_only_mode_writes_only_execution_grade_databento_state(self):
        payload = bridge.annotate_quote_quality({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "databento_realtime",
            "price_nq": 30405.25,
            "price_es": 7595.75,
            "update_mode_nq": "realtime",
            "update_mode_es": "realtime",
        })

        with patch.object(bridge, "fetch_databento_realtime", return_value=payload), \
            patch.object(bridge, "fetch_tv_websocket", side_effect=AssertionError("TV fallback should not run")), \
            patch.object(bridge, "fetch_yahoo_fallback", side_effect=AssertionError("Yahoo fallback should not run")), \
            patch.object(sys, "argv", ["realtime_data_bridge.py", "--quiet", "--databento-only"]):
            rc = bridge.main()

        self.assertEqual(rc, 0)
        written = json.loads(bridge.STATE_FILE.read_text())
        self.assertEqual(written["source"], "databento_realtime")
        self.assertTrue(written["execution_grade"])

    def test_main_preserves_fresh_topstep_realtime_state_before_fallbacks(self):
        payload = bridge.annotate_quote_quality({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "topstep_realtime",
            "price_nq": 30405.25,
            "price_es": 7595.75,
            "update_mode_nq": "broker_realtime_signalr",
            "update_mode_es": "broker_realtime_signalr",
        })
        bridge.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        bridge.STATE_FILE.write_text(json.dumps(payload))

        with patch.object(bridge, "fetch_databento_realtime", side_effect=AssertionError("Databento should not run")), \
            patch.object(bridge, "fetch_tv_websocket", side_effect=AssertionError("TV fallback should not run")), \
            patch.object(bridge, "fetch_yahoo_fallback", side_effect=AssertionError("Yahoo fallback should not run")), \
            patch.object(sys, "argv", ["realtime_data_bridge.py", "--quiet"]):
            rc = bridge.main()

        self.assertEqual(rc, 0)
        written = json.loads(bridge.STATE_FILE.read_text())
        self.assertEqual(written["source"], "topstep_realtime")
        self.assertTrue(written["execution_grade"])
        self.assertTrue(written["preserved_existing_state"])


if __name__ == "__main__":
    unittest.main()
