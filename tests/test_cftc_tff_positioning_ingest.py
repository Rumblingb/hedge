import unittest
from datetime import datetime, timedelta, timezone

from scripts.cftc_tff_positioning_ingest import build_report, classify_regime


def row(contract, weeks_ago, dealer_net, lev_net, oi=1000):
    report_date = datetime(2026, 5, 26, tzinfo=timezone.utc) - timedelta(days=7 * weeks_ago)
    dealer_long = 500 + dealer_net / 2
    dealer_short = 500 - dealer_net / 2
    lev_long = 500 + lev_net / 2
    lev_short = 500 - lev_net / 2
    return {
        "contract_market_name": contract,
        "report_date_as_yyyy_mm_dd": report_date.isoformat().replace("+00:00", ""),
        "open_interest_all": str(oi),
        "dealer_positions_long_all": str(dealer_long),
        "dealer_positions_short_all": str(dealer_short),
        "asset_mgr_positions_long_all": "500",
        "asset_mgr_positions_short_all": "500",
        "lev_money_positions_long_all": str(lev_long),
        "lev_money_positions_short_all": str(lev_short),
    }


class CftcTffPositioningIngestTests(unittest.TestCase):
    def test_classify_regime_keeps_positioning_as_regime_not_trade(self):
        self.assertEqual(classify_regime(-1.8, 0.8), "risk-on-confirmed-by-leveraged-money")
        self.assertEqual(classify_regime(1.8, -0.8), "risk-off-confirmed-by-leveraged-money")
        self.assertEqual(classify_regime(0.1, 0.2), "neutral-positioning")

    def test_build_report_is_research_only_and_non_tradable(self):
        rows = []
        for contract in ("E-MINI S&P 500", "NASDAQ-100 Consolidated", "UST 10Y NOTE"):
            for weeks_ago in range(12, -1, -1):
                rows.append(row(contract, weeks_ago, dealer_net=-100 + weeks_ago * 3, lev_net=50 - weeks_ago))

        report = build_report(rows, generated_at=datetime(2026, 5, 30, tzinfo=timezone.utc))

        self.assertTrue(report["researchOnly"])
        self.assertFalse(report["writesOrders"])
        self.assertFalse(report["touchesBroker"])
        self.assertFalse(report["promoted_for_execution"])
        self.assertFalse(report["tradable_signal"])
        self.assertFalse(report["readyForExecution"])
        self.assertTrue(report["freshForWeeklyResearch"])
        self.assertEqual(report["latestReportDate"], "2026-05-26")
        self.assertEqual(set(report["markets"].keys()), {"ES", "NQ", "ZN"})

    def test_build_report_blocks_when_core_market_missing(self):
        rows = [row("E-MINI S&P 500", 0, dealer_net=0, lev_net=0)]

        report = build_report(rows, generated_at=datetime(2026, 5, 30, tzinfo=timezone.utc))

        self.assertFalse(report["freshForWeeklyResearch"])
        self.assertIn("missing markets: NQ, ZN", report["blockers"])


if __name__ == "__main__":
    unittest.main()
