import unittest

from scripts.kalshi_fillability_snapshot import build_snapshot, bucket_for_spread, infer_series_ticker, row_from_market


class KalshiFillabilitySnapshotTests(unittest.TestCase):
    def test_bucket_for_spread(self):
        self.assertEqual(bucket_for_spread(None), "no-two-sided-book")
        self.assertEqual(bucket_for_spread(1.0), "tight")
        self.assertEqual(bucket_for_spread(4.0), "usable")
        self.assertEqual(bucket_for_spread(10.0), "wide")
        self.assertEqual(bucket_for_spread(20.0), "too-wide")

    def test_infer_series_ticker_from_market_ticker(self):
        self.assertEqual(infer_series_ticker({"ticker": "KXFED-26DEC-T2.75"}), "KXFED")
        self.assertEqual(infer_series_ticker({"series_ticker": "KXCPI", "ticker": "OTHER-1"}), "KXCPI")

    def test_row_from_market_excludes_combo_and_wide_books(self):
        combo = row_from_market({
            "ticker": "KXMVE-TEST",
            "series_ticker": "KXTEST",
            "title": "yes A,yes B,yes C",
            "yes_bid_dollars": "0.48",
            "yes_ask_dollars": "0.50",
        })
        wide = row_from_market({
            "ticker": "KXTEST-1",
            "series_ticker": "KXTEST",
            "title": "Will CPI rise more than 0.2%?",
            "yes_bid_dollars": "0.20",
            "yes_ask_dollars": "0.40",
        })

        self.assertFalse(combo.executable)
        self.assertEqual(combo.reason, "combo-like market excluded")
        self.assertFalse(wide.executable)
        self.assertEqual(wide.bucket, "too-wide")

    def test_build_snapshot_is_research_only(self):
        row = row_from_market({
            "ticker": "KXCPI-TEST",
            "series_ticker": "KXCPI",
            "title": "Will CPI rise more than 0.2%?",
            "yes_bid_dollars": "0.48",
            "yes_ask_dollars": "0.50",
            "liquidity_dollars": "25.00",
        })

        snapshot = build_snapshot([row])

        self.assertTrue(snapshot["researchOnly"])
        self.assertFalse(snapshot["writesOrders"])
        self.assertFalse(snapshot["touchesBroker"])
        self.assertFalse(snapshot["tradable_signal"])
        self.assertFalse(snapshot["readyForPaper"])
        self.assertEqual(snapshot["executablePublicQuotes"], 1)
        self.assertEqual(snapshot["topExecutable"][0]["ticker"], "KXCPI-TEST")


if __name__ == "__main__":
    unittest.main()
