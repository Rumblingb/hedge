import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.gex_backtest import compute_daily_gex, load_return_proxy, parse_size, run_backtest


def sample_option_chain() -> pd.DataFrame:
    rows = []
    for day, spot in [("2021-01-04", 370.0), ("2021-01-05", 372.0), ("2021-01-06", 371.0)]:
        for strike in [350.0, 370.0, 390.0]:
            rows.append({
                "[QUOTE_DATE]": day,
                "[UNDERLYING_LAST]": spot,
                "[STRIKE]": strike,
                "[C_SIZE]": "10 x 20",
                "[P_SIZE]": "8 x 12",
                "[C_VOLUME]": 100,
                "[P_VOLUME]": 80,
                "[C_GAMMA]": 0.02,
                "[P_GAMMA]": 0.015,
            })
    return pd.DataFrame(rows)


class GexBacktestTest(unittest.TestCase):
    def test_parse_size_uses_larger_side_and_fails_closed(self):
        self.assertEqual(parse_size("10 x 25"), 25.0)
        self.assertEqual(parse_size("bad"), 0.0)
        self.assertEqual(parse_size(None), 0.0)

    def test_compute_daily_gex_outputs_research_features(self):
        daily = compute_daily_gex(sample_option_chain())

        self.assertEqual(len(daily), 3)
        self.assertIn("net_gex", daily.columns)
        self.assertIn("atm_gex_pct_w", daily.columns)
        self.assertIn("gamma_flip", daily.columns)
        self.assertTrue(daily["gamma_flip"].notna().all())

    def test_run_backtest_is_research_only_metric_source(self):
        gex = compute_daily_gex(sample_option_chain())
        returns = pd.DataFrame({
            "date": pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-06"]),
            "proxy_close": [3700.0, 3710.0, 3690.0],
            "proxy_return": [0.0027, -0.0054, 0.001],
        })

        merged, metrics = run_backtest(gex, returns)

        self.assertEqual(len(merged), 3)
        self.assertEqual(metrics["rows"], 3)
        self.assertIn("signAtmGex", metrics)
        self.assertIn("buyHold", metrics)

    def test_load_return_proxy_accepts_cross_asset_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cross.csv"
            pd.DataFrame({
                "Date": ["2021-01-04", "2021-01-05"],
                "S&P500": [3700.0, 3710.0],
            }).to_csv(path, index=False)

            out = load_return_proxy(path)

        self.assertEqual(list(out.columns), ["date", "proxy_close", "proxy_return"])
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
