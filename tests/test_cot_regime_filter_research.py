import tempfile
import unittest
from pathlib import Path

from scripts.cot_regime_filter_research import (
    CotRegime,
    feed_date_map,
    latest_regime_for,
    policy_allows,
    read_cot_regimes,
)


class CotRegimeFilterResearchTests(unittest.TestCase):
    def test_policy_blocks_only_opposite_extremes(self):
        risk_on = {"regime": "dealer-short-contrarian-support", "dealerZ52": -1.8, "leveragedMoneyZ52": 0.1}
        risk_off = {"regime": "dealer-long-contrarian-resistance", "dealerZ52": 1.8, "leveragedMoneyZ52": -0.1}

        self.assertTrue(policy_allows(risk_on, 1, "block-opposite-extreme"))
        self.assertFalse(policy_allows(risk_on, -1, "block-opposite-extreme"))
        self.assertFalse(policy_allows(risk_off, 1, "block-opposite-extreme"))
        self.assertTrue(policy_allows(risk_off, -1, "block-opposite-extreme"))

    def test_latest_regime_uses_release_lag_not_report_date(self):
        regimes = [
            CotRegime("2026-05-19", "2026-05-22", "neutral-positioning", 0, 0, 0, 0),
            CotRegime("2026-05-26", "2026-05-29", "dealer-long-contrarian-resistance", 1, -1, 2, -1),
        ]

        self.assertEqual(latest_regime_for(__import__("datetime").date(2026, 5, 28), regimes).reportDate, "2026-05-19")
        self.assertEqual(latest_regime_for(__import__("datetime").date(2026, 5, 29), regimes).reportDate, "2026-05-26")

    def test_feed_map_joins_only_available_reports(self):
        regimes = [
            CotRegime("2026-05-19", "2026-05-22", "neutral-positioning", 0, 0, 0, 0),
            CotRegime("2026-05-26", "2026-05-29", "dealer-long-contrarian-resistance", 1, -1, 2, -1),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "feed.csv"
            feed.write_text(
                "datetime,open,high,low,close,volume\n"
                "2026-05-28 14:30:00,1,1,1,1,1\n"
                "2026-05-29 14:30:00,1,1,1,1,1\n"
            )
            mapped = feed_date_map(feed, regimes)

        self.assertEqual(mapped["2026-05-28"]["reportDate"], "2026-05-19")
        self.assertEqual(mapped["2026-05-29"]["reportDate"], "2026-05-26")

    def test_read_cot_regimes_supports_current_core_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            cot = Path(tmp) / "cot.csv"
            cot.write_text(
                "contract_market_name,report_date_as_yyyy_mm_dd,open_interest_all,"
                "dealer_positions_long_all,dealer_positions_short_all,"
                "lev_money_positions_long,lev_money_positions_short\n"
                + "\n".join(
                    f"NASDAQ-100 Consolidated,2026-0{month}-01T00:00:00.000,1000,"
                    f"{400 + index * 10},{600 - index * 10},{550 - index * 5},{450 + index * 5}"
                    for index, month in enumerate(range(1, 7), start=1)
                )
                + "\n"
            )

            regimes = read_cot_regimes(cot, "NQ", release_lag_days=3)

        self.assertEqual(len(regimes), 6)
        self.assertEqual(regimes[-1].reportDate, "2026-06-01")
        self.assertEqual(regimes[-1].availableDate, "2026-06-04")


if __name__ == "__main__":
    unittest.main()
