import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import refresh_futures_research_data as refresh


class RefreshFuturesResearchDataTest(unittest.TestCase):
    def test_incomplete_symbol_set_does_not_overwrite_all_markets_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_data_dir = refresh.DATA_DIR
            refresh.DATA_DIR = Path(tmp)
            out_path = refresh.DATA_DIR / "ALL-6MARKETS-15m-60d-normalized.csv"
            out_path.write_text("existing\n")

            def fake_fetch(label, ticker, interval, period):
                if label == "NQ":
                    return [], {"symbol": label, "ticker": ticker, "interval": interval, "rows": 0, "status": "empty"}
                return [
                    {"ts": "2026-05-29T20:45:00.000Z", "symbol": label, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
                ], {"symbol": label, "ticker": ticker, "interval": interval, "rows": 1, "status": "ok", "latestTs": "2026-05-29T20:45:00.000Z"}

            try:
                with patch.object(refresh, "fetch_symbol", side_effect=fake_fetch):
                    report = refresh.refresh_interval("15m", None, True)
            finally:
                refresh.DATA_DIR = original_data_dir

            self.assertFalse(report["completeSymbolSet"])
            self.assertEqual(report["missingSymbols"], ["NQ"])
            self.assertFalse(report["wroteFile"])
            self.assertEqual(out_path.read_text(), "existing\n")

    def test_missing_symbol_can_be_recovered_from_existing_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_data_dir = refresh.DATA_DIR
            refresh.DATA_DIR = Path(tmp)
            out_path = refresh.DATA_DIR / "ALL-6MARKETS-15m-60d-normalized.csv"
            out_path.write_text(
                "ts,symbol,open,high,low,close,volume\n"
                "2026-05-29T20:45:00.000Z,NQ,1,1,1,1,10\n"
            )

            def fake_fetch(label, ticker, interval, period):
                if label == "NQ":
                    return [], {"symbol": label, "ticker": ticker, "interval": interval, "rows": 0, "status": "empty"}
                return [
                    {"ts": "2026-05-29T20:45:00.000Z", "symbol": label, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
                ], {"symbol": label, "ticker": ticker, "interval": interval, "rows": 1, "status": "ok", "latestTs": "2026-05-29T20:45:00.000Z"}

            try:
                with patch.object(refresh, "fetch_symbol", side_effect=fake_fetch):
                    report = refresh.refresh_interval("15m", None, True)
            finally:
                refresh.DATA_DIR = original_data_dir

            self.assertTrue(report["completeSymbolSet"])
            self.assertEqual(report["missingSymbols"], [])
            self.assertEqual(report["recoveredSymbols"], ["NQ"])
            self.assertTrue(report["wroteFile"])
            self.assertIn("NQ", out_path.read_text())

    def test_build_report_blocks_missing_symbol(self):
        args = argparse.Namespace(intervals=["15m"], period=None, dry_run=True)

        with patch.object(refresh, "refresh_interval") as interval:
            interval.return_value = {
                "interval": "15m",
                "rows": 10,
                "missingSymbols": ["NQ"],
                "zeroVolumeTailSymbols": [],
            }
            report = refresh.build_report(args)

        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("15m missing symbols: NQ", report["blockers"])


if __name__ == "__main__":
    unittest.main()
