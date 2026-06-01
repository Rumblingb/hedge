import unittest

from scripts.fed_prior_upper_bound_source import FedTargetRangeRow
from scripts.prediction_macro_rates_resolved_labels import (
    VAULT,
    build_resolved_labels,
    default_markdown_path,
    parse_macro_rate_question,
    polymarket_yes_won,
    render_markdown,
)


class PredictionMacroRatesResolvedLabelsTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-macro-rates-resolved-labels-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "historicalRowsLoaded": 0,
            "officialComparableCount": 0,
            "officialAgreementRate": None,
            "usableForResearchJoinCount": 0,
            "kindCounts": {},
            "blockers": [],
            "sampleLabels": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Macro/Rates Resolved Labels - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_parses_threshold_and_bps_questions(self):
        threshold = parse_macro_rate_question(
            "Will the FED set interest rates above 2.25% following their scheduled July meeting?"
        )
        bps = parse_macro_rate_question(
            "Will the Fed increase interest rates by 75 bps after their September meeting?"
        )

        self.assertEqual(threshold["kind"], "upper-bound-threshold")
        self.assertEqual(threshold["thresholdUpperBound"], 2.25)
        self.assertEqual(bps["kind"], "bps-change")
        self.assertEqual(bps["direction"], "increase")
        self.assertEqual(bps["changeBps"], 75)

    def test_polymarket_yes_won_from_resolved_prices(self):
        self.assertTrue(polymarket_yes_won({"outcomes": '["Yes","No"]', "outcome_prices": '["1","0"]'}))
        self.assertFalse(polymarket_yes_won({"outcomes": '["Yes","No"]', "outcome_prices": '["0","1"]'}))
        self.assertIsNone(polymarket_yes_won({"outcomes": '["Yes","No"]', "outcome_prices": '["0.55","0.45"]'}))

    def test_builds_research_only_official_label_audit(self):
        rows = [
            {
                "externalId": f"pm-threshold-{idx}",
                "question": "Will the FED set interest rates above 2.25% following their scheduled July meeting?",
                "outcomes": '["Yes","No"]',
                "outcome_prices": '["1","0"]',
                "closeTime": "2022-07-27 00:00:00+00",
            }
            for idx in range(20)
        ]
        fed_rows = [
            FedTargetRangeRow(
                effectiveDate="2022-07-28",
                increaseBps=75,
                decreaseBps=0,
                lowerBound=2.25,
                upperBound=2.5,
                levelText="2.25-2.50",
                sourceYear=2022,
            )
        ]

        payload = build_resolved_labels(
            historical_rows=rows,
            fed_target_rows=fed_rows,
            source_url="https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
        )

        self.assertEqual(payload["decision"], "research-only-macro-rates-resolved-labels-ready")
        self.assertEqual(payload["officialComparableCount"], 20)
        self.assertEqual(payload["officialAgreementRate"], 1.0)
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_blocks_thin_history(self):
        payload = build_resolved_labels(
            historical_rows=[],
            fed_target_rows=[],
            source_url="https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
        )

        self.assertEqual(payload["decision"], "research-only-macro-rates-resolved-labels-blocked")
        self.assertIn("missing-official-fed-target-history", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
