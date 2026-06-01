import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import scripts.data_freshness_gate as gate


class DataFreshnessGateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.addCleanup(self.tmpdir.cleanup)

        self.original_paths = {
            "REALTIME_STATE": gate.REALTIME_STATE,
            "LEGACY_REALTIME_STATE": gate.LEGACY_REALTIME_STATE,
            "STATE_DIR": gate.STATE_DIR,
            "LEGACY_STATE_DIR": gate.LEGACY_STATE_DIR,
        }
        self.addCleanup(self.restore_paths)

        gate.REALTIME_STATE = self.tmp_path / "realtime-quote.latest.json"
        gate.LEGACY_REALTIME_STATE = self.tmp_path / "legacy-realtime-quote.latest.json"
        gate.STATE_DIR = self.tmp_path
        gate.LEGACY_STATE_DIR = self.tmp_path / "legacy"

    def restore_paths(self):
        for name, value in self.original_paths.items():
            setattr(gate, name, value)

    def write_realtime_state(self, payload):
        gate.REALTIME_STATE.write_text(json.dumps(payload))

    def test_fallback_delayed_quote_is_stale_even_when_timestamp_is_fresh(self):
        now = datetime.now(timezone.utc).isoformat()
        self.write_realtime_state({
            "price_nq": 123.0,
            "timestamp": now,
            "source": "yahoo_fallback",
            "update_mode_nq": "delayed_120s",
        })

        result = gate.check_freshness("NQ=F")

        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["source"], "yahoo_fallback")
        self.assertIn("not execution-grade realtime data", result["reason"])

    def test_tradingview_pro_delayed_stream_is_stale(self):
        now = datetime.now(timezone.utc).isoformat()
        self.write_realtime_state({
            "price_nq": 123.0,
            "timestamp": now,
            "source": "tradingview_pro",
            "update_mode_nq": "delayed_streaming_600",
        })

        result = gate.check_freshness("NQ=F")

        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["source"], "tradingview_pro")
        self.assertIn("delayed_streaming_600", result["reason"])
        self.assertIn("not execution-grade realtime data", result["reason"])

    def test_bridge_labeled_tradingview_pro_delayed_is_stale(self):
        now = datetime.now(timezone.utc).isoformat()
        self.write_realtime_state({
            "price_nq": 123.0,
            "timestamp": now,
            "source": "tradingview_pro_delayed",
            "original_source": "tradingview_pro",
            "update_mode_nq": "delayed_streaming_600",
            "execution_grade": False,
        })

        result = gate.check_freshness("NQ=F")

        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["source"], "tradingview_pro_delayed")
        self.assertIn("delayed_streaming_600", result["reason"])

    def test_tradingview_public_stream_is_stale(self):
        now = datetime.now(timezone.utc).isoformat()
        self.write_realtime_state({
            "price_nq": 123.0,
            "timestamp": now,
            "source": "tradingview_public",
            "update_mode_nq": "streaming",
        })

        result = gate.check_freshness("NQ=F")

        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["source"], "tradingview_public")
        self.assertIn("public TradingView", result["reason"])

    def test_fresh_realtime_quote_passes(self):
        now = datetime.now(timezone.utc).isoformat()
        self.write_realtime_state({
            "price_nq": 123.0,
            "timestamp": now,
            "source": "tradingview_ws",
            "update_mode_nq": "realtime",
        })

        result = gate.check_freshness("NQ=F")

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["source"], "tradingview_ws")
        self.assertEqual(result["reason"], "ok")


if __name__ == "__main__":
    unittest.main()
