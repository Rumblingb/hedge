import csv
import tempfile
import unittest
from pathlib import Path

from scripts.futures_data_quality_snapshot import build_snapshot


class FuturesDataQualitySnapshotTest(unittest.TestCase):
    def write_dataset(self, path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["ts", "symbol", "open", "high", "low", "close", "volume"])
            writer.writeheader()
            writer.writerows(rows)

    def test_percent_style_min_coverage_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            self.write_dataset(path, [
                {"ts": "2026-05-29T20:00:00.000Z", "symbol": "NQ", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                {"ts": "2026-05-29T20:15:00.000Z", "symbol": "NQ", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                {"ts": "2026-05-29T20:00:00.000Z", "symbol": "ES", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            ])

            snapshot = build_snapshot([path], min_coverage=50, max_end_lag_minutes=30)

        self.assertTrue(snapshot["pass"])
        self.assertEqual(snapshot["minCoveragePct"], 0.5)
        self.assertEqual(snapshot["datasets"][0]["failingChecks"], [])

    def test_low_symbol_coverage_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            self.write_dataset(path, [
                {"ts": "2026-05-29T20:00:00.000Z", "symbol": "NQ", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                {"ts": "2026-05-29T20:15:00.000Z", "symbol": "NQ", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                {"ts": "2026-05-29T20:30:00.000Z", "symbol": "NQ", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                {"ts": "2026-05-29T20:00:00.000Z", "symbol": "ES", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            ])

            snapshot = build_snapshot([path], min_coverage=0.95, max_end_lag_minutes=60)

        self.assertFalse(snapshot["pass"])
        self.assertIn("minCoveragePct", snapshot["datasets"][0]["failingChecks"])


if __name__ == "__main__":
    unittest.main()
