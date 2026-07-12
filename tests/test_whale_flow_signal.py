import unittest

from scripts.whale_flow_signal import build_cftc_tff_signal


def tff_row(market: str, report_date: str, values: dict[int, int]) -> str:
    row = ["0"] * 41
    row[0] = market
    row[2] = report_date
    for idx, value in values.items():
        row[idx] = str(value)
    return ",".join(row)


class WhaleFlowSignalTests(unittest.TestCase):
    def test_build_cftc_tff_signal_is_shadow_only(self):
        raw = "\n".join([
            tff_row(
                "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
                "2026-05-26",
                {
                    7: 100000,
                    8: 20000,
                    9: 25000,
                    11: 50000,
                    12: 20000,
                    14: 10000,
                    15: 30000,
                    22: 5000,
                    23: 2000,
                    25: 1000,
                    26: 5000,
                    28: -1000,
                    29: 5000,
                    31: -2000,
                    32: 3000,
                },
            ),
            tff_row(
                "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE",
                "2026-05-26",
                {
                    7: 200000,
                    8: 40000,
                    9: 50000,
                    11: 60000,
                    12: 30000,
                    14: 20000,
                    15: 35000,
                    22: 7000,
                    23: 3000,
                    25: 2000,
                    26: 3000,
                    28: -2000,
                    29: 6000,
                    31: -1000,
                    32: 4000,
                },
            ),
        ])

        signal = build_cftc_tff_signal(raw, source="test-cftc")

        self.assertEqual(signal["method"], "cftc_tff_cot_weekly")
        self.assertEqual(signal["evidence_level"], "weekly_cot_shadow_only")
        self.assertTrue(signal["researchOnly"])
        self.assertFalse(signal["writesOrders"])
        self.assertFalse(signal["touchesBroker"])
        self.assertFalse(signal["tradable_signal"])
        self.assertFalse(signal["promoted_for_execution"])
        self.assertFalse(signal["readyForExecution"])
        self.assertIn("Research-only weekly COT context", signal["operator_read"])
        self.assertIn("NQ", signal["components"]["cftc_tff_cot"]["markets"])
        self.assertIn("ES", signal["components"]["cftc_tff_cot"]["markets"])
        self.assertEqual(signal["components"]["cftc_tff_cot"]["source"], "test-cftc")

    def test_build_cftc_tff_signal_requires_tracked_markets(self):
        with self.assertRaisesRegex(RuntimeError, "No NQ/ES TFF rows"):
            build_cftc_tff_signal("UNRELATED MARKET,0,2026-05-26", source="test")


if __name__ == "__main__":
    unittest.main()
