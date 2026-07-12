import tempfile
import unittest
from pathlib import Path

from scripts.build_data_master_csv import analyze_csv, build_payload, find_csvs, write_csv


class BuildDataMasterCsvTest(unittest.TestCase):
    def test_analyzes_csv_schema_range_symbols_and_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "ALL-2MARKETS-NQ-ES-15m-longterm-normalized.csv"
            csv_path.write_text(
                "ts,symbol,open,high,low,close,volume\n"
                "2000-01-03 08:30:00,ES,100,101,99,100.5,0\n"
                "2025-12-11 20:45:00,NQ,200,202,198,201,100\n"
            )

            row = analyze_csv(csv_path)

        self.assertEqual(row.rows, 2)
        self.assertEqual(row.date_column, "ts")
        self.assertEqual(row.date_min, "2000-01-03 08:30:00")
        self.assertEqual(row.date_max, "2025-12-11 20:45:00")
        self.assertEqual(row.symbols, ["ES", "NQ"])
        self.assertEqual(row.timeframe, "15min")
        self.assertIn("cross-symbol-non-overlap-normalized-research-only", row.blockers)
        self.assertEqual(row.usage, "manual-review-before-use")

    def test_writes_machine_catalog_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "NQ-1m-3yr.csv"
            dataset.write_text(
                "ts,symbol,open,high,low,close,volume\n"
                "2022-12-26 18:01:00,NQ,13759,13760,13750,13755,10\n"
                "2025-12-11 20:52:00,NQ,26650,26656,26600,26610,20\n"
            )
            rows = [analyze_csv(path) for path in find_csvs([root])]
            output = root / "master.csv"
            write_csv(output, rows)
            payload = build_payload(rows, output)

            text = output.read_text()

        self.assertIn("relative_path", text)
        self.assertIn("NQ-1m-3yr.csv", text)
        self.assertEqual(payload["datasetCount"], 1)
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertIn("topDatasets", payload)

    def test_fx_cash_proxy_is_symbolized_but_not_futures_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "EURUSD-1min.csv"
            rows = [
                "datetime,open,high,low,close,volume",
                "2000-05-30 17:27:00,0.9300,0.9310,0.9290,0.9305,100",
            ]
            rows.extend(f"2000-05-31 00:{idx % 60:02d}:00,0.9300,0.9310,0.9290,0.9305,100" for idx in range(1000))
            rows.append("2026-05-29 16:58:00,1.1300,1.1310,1.1290,1.1305,100")
            csv_path.write_text("\n".join(rows))

            row = analyze_csv(csv_path)

        self.assertEqual(row.symbols, ["EURUSD"])
        self.assertEqual(row.timeframe, "1min")
        self.assertIn("cash-fx-proxy-not-futures-contract", row.blockers)
        self.assertEqual(row.trust_tier, "silver-research")
        self.assertEqual(row.usage, "research-with-blocker-review")


if __name__ == "__main__":
    unittest.main()
