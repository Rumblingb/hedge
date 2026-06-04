import unittest

import pandas as pd

from scripts.unified_backtest import apply_prop_firm


class UnifiedBacktestTest(unittest.TestCase):
    def test_apply_prop_firm_accepts_fractional_daily_pnl(self):
        trades = pd.DataFrame(
            [
                {
                    "entry_day": "2026-06-04",
                    "contracts": 3,
                    "pnl_dollars": -218.25,
                }
            ]
        )

        result = apply_prop_firm(trades)

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(float(result.iloc[0]["daily_pnl"]), -227.25)
        self.assertAlmostEqual(float(result.iloc[0]["pnl_after_costs"]), -227.25)


if __name__ == "__main__":
    unittest.main()
