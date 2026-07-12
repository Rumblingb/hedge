import argparse
import tempfile
import unittest
from pathlib import Path

from scripts.prediction_category_drilldown import (
    build_next_tests,
    build_report,
    category_for_text,
    summarize_kalshi_fillability,
    summarize_snapshot,
    write_narrow_snapshots,
)


class PredictionCategoryDrilldownTest(unittest.TestCase):
    def test_classifies_common_prediction_categories(self):
        self.assertEqual(category_for_text("Bitcoin above 100k tomorrow"), "crypto")
        self.assertEqual(category_for_text("Ethereum above 5k tomorrow"), "crypto")
        self.assertEqual(category_for_text("Will CPI rise more than 0.3%?"), "macro-rates")
        self.assertEqual(category_for_text("Will Argentina win the World Cup?"), "sports")
        self.assertEqual(category_for_text("Will Netherlands win the 2026 FIFA World Cup?"), "sports")
        self.assertEqual(category_for_text("Daily Coinflip"), "other")
        self.assertEqual(category_for_text("Will a full-scale military conflict between the US and Iran resume?"), "geopolitics")
        self.assertEqual(category_for_text("Will WTI Crude Oil hit $80 in May?"), "commodities")
        self.assertEqual(category_for_text("Will Alejandro Tabilo win the 2026 Men's French Open?"), "sports")
        self.assertEqual(category_for_text("AC Monza vs. US Catanzaro 1929"), "sports")
        self.assertEqual(category_for_text("Will Iran win the 2026 FIFA World Cup?"), "sports")
        self.assertEqual(category_for_text("Will US vs Iran war resume by June?"), "geopolitics")
        self.assertEqual(category_for_text("Strait of Hormuz traffic returns to normal by end of May?"), "geopolitics")
        self.assertEqual(category_for_text("US announces new Iran ceasefire extension by June 30?"), "geopolitics")
        self.assertEqual(category_for_text("Will Saudi Aramco be the second-largest company by market cap?"), "equities")
        self.assertEqual(category_for_text("Will Arsenal win the 2025-26 Champions League?"), "sports")
        self.assertEqual(category_for_text("Will MOUZ win IEM Cologne Major 2026?"), "sports")
        self.assertEqual(category_for_text("Will the 2028 Democratic nominee be inaugurated as president?"), "politics")

    def test_builds_research_only_next_tests_for_cross_venue_categories(self):
        categories = summarize_snapshot([
            {"venue": "polymarket", "marketQuestion": "Bitcoin above 100k tomorrow", "spreadPct": 0.01, "displayedSize": 1000, "clobTokenId": "a"},
            {"venue": "manifold", "marketQuestion": "Bitcoin 100k tomorrow", "spreadPct": 0.02, "displayedSize": 100},
            {"venue": "polymarket", "marketQuestion": "Will France win the World Cup?", "spreadPct": 0.01, "displayedSize": 500, "clobTokenId": "b"},
            {"venue": "polymarket", "marketQuestion": "Will WTI Crude Oil hit $80 in May?", "spreadPct": 0.01, "displayedSize": 500, "clobTokenId": "c"},
            {"venue": "manifold", "marketQuestion": "Will US gas price hit $5 in May?", "spreadPct": 0.03, "displayedSize": 100},
        ])

        tests = build_next_tests(categories, {"crypto": {"reasonCounts": {"temporal-mismatch": 2}}})

        crypto = next(item for item in tests if item["category"] == "crypto")
        self.assertEqual(crypto["oneVariable"], "settlement horizon")
        self.assertIn("Research-only", crypto["promotionRule"])
        commodities = next(item for item in tests if item["category"] == "commodities")
        self.assertEqual(commodities["oneVariable"], "reference market and line parser")

    def test_prioritizes_futures_adjacent_prediction_lanes_over_misc_other(self):
        categories = summarize_snapshot([
            *[
                {"venue": "polymarket", "marketQuestion": f"Will the highest temperature in London be {value}C on May 29?"}
                for value in range(70)
            ],
            {"venue": "manifold", "marketQuestion": "Will London weather be warm tomorrow?"},
            {"venue": "polymarket", "marketQuestion": "Will WTI Crude Oil hit $80 in May?"},
            {"venue": "manifold", "marketQuestion": "Will US gas price hit $5 in May?"},
            {"venue": "polymarket", "marketQuestion": "Will CPI rise more than 0.3%?"},
            {"venue": "kalshi", "marketQuestion": "Will CPI inflation be above forecast?"},
            {"venue": "polymarket", "marketQuestion": "Bitcoin above 100k tomorrow"},
            {"venue": "manifold", "marketQuestion": "Bitcoin above 100k tomorrow"},
            {"venue": "polymarket", "marketQuestion": "US x Iran peace deal by June?"},
            {"venue": "manifold", "marketQuestion": "Will US-Iran war resume by June?"},
            {"venue": "polymarket", "marketQuestion": "Will NVIDIA be the largest company by market cap?"},
            {"venue": "manifold", "marketQuestion": "Will QCOM stock reach $300?"},
            {"venue": "polymarket", "marketQuestion": "Will the 2028 Democratic nominee be a governor?"},
            {"venue": "manifold", "marketQuestion": "Will a mayor win the next local election?"},
        ])

        tests = build_next_tests(categories, {})
        categories_in_queue = [item["category"] for item in tests]

        self.assertIn("commodities", categories_in_queue)
        self.assertIn("macro-rates", categories_in_queue)
        self.assertNotIn("other", categories_in_queue)

    def test_kalshi_fillability_boosts_fillable_macro_rates_lane(self):
        categories = summarize_snapshot([
            {"venue": "polymarket", "marketQuestion": "Will CPI rise more than 0.3%?"},
            {"venue": "kalshi", "marketQuestion": "Will CPI inflation be above forecast?"},
            {"venue": "polymarket", "marketQuestion": "Will the 2028 Democratic nominee be a governor?"},
            {"venue": "manifold", "marketQuestion": "Will a mayor win the next local election?"},
        ])
        fillability = summarize_kalshi_fillability({
            "generatedAt": "2026-05-30T00:00:00+00:00",
            "researchOnly": True,
            "writesOrders": False,
            "readyForPaper": False,
            "marketsInspected": 2,
            "executablePublicQuotes": 2,
            "bucketCounts": {"tight": 2},
            "topExecutable": [
                {"ticker": "KXFED-26JUN-T3.75", "seriesTicker": "KXFED", "bucket": "tight", "executable": True},
                {"ticker": "KXCPI-26MAY-T0.6", "seriesTicker": "KXCPI", "bucket": "tight", "executable": True},
            ],
        })

        tests = build_next_tests(categories, {}, fillability)
        macro = next(item for item in tests if item["category"] == "macro-rates")

        self.assertTrue(macro["fillabilityGuided"])
        self.assertEqual(macro["kalshiFillability"]["executablePublicQuotes"], 2)
        self.assertEqual(macro["kalshiFillability"]["seriesTickers"], {"KXFED": 1, "KXCPI": 1})

    def test_report_never_promotes_paper(self):
        args = argparse.Namespace(snapshot="/missing/snapshot.json", cycle="/missing/cycle.json", kalshi_fillability="/missing/fillability.json")

        report = build_report(args)

        self.assertTrue(report["researchOnly"])
        self.assertFalse(report["writesOrders"])
        self.assertFalse(report["readyForPaper"])
        self.assertTrue(report["kalshiFillability"]["researchOnly"])
        self.assertFalse(report["kalshiFillability"]["writesOrders"])

    def test_writes_research_only_category_snapshot_inputs(self):
        rows = [
            {"venue": "polymarket", "marketQuestion": "Bitcoin above 100k tomorrow"},
            {"venue": "manifold", "marketQuestion": "Bitcoin above 100k tomorrow"},
            {"venue": "polymarket", "marketQuestion": "Will Spain win the World Cup?"},
        ]
        next_tests = [
            {"id": "crypto-narrow-scan", "category": "crypto", "promotionRule": "Research-only."},
            {"id": "sports-narrow-scan", "category": "sports", "promotionRule": "Research-only."},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_narrow_snapshots(rows, next_tests, Path(tmp))

            self.assertEqual([item["category"] for item in manifest], ["crypto", "sports"])
            self.assertTrue(all(item["researchOnly"] for item in manifest))
            self.assertTrue(all(not item["writesOrders"] for item in manifest))
            self.assertTrue((Path(tmp) / "crypto.json").exists())
            self.assertTrue((Path(tmp) / "sports.json").exists())
            self.assertTrue((Path(tmp) / "manifest.latest.json").exists())


if __name__ == "__main__":
    unittest.main()
