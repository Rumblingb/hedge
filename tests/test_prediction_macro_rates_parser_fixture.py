import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.prediction_macro_rates_parser_fixture import (
    VAULT,
    build_fixture,
    default_markdown_path,
    parse_kalshi_kxfed,
    parse_polymarket_fed_decision,
    render_markdown,
    resolve_prior,
)


class PredictionMacroRatesParserFixtureTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-macro-rates-parser-fixture-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "polymarketFedDecisionCount": 0,
            "kalshiKxfedThresholdCount": 0,
            "sameMeetingPairCount": 0,
            "comparablePairCount": 0,
            "blockers": [],
            "pairs": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Macro/Rates Parser Fixture - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_parses_polymarket_fed_bps_brackets(self):
        row = {
            "venue": "polymarket",
            "externalId": "pm-cut-25",
            "marketQuestion": "Will the Fed decrease interest rates by 25 bps after the June 2026 meeting?",
            "expiry": "2026-06-17T00:00:00Z",
            "settlementText": "Resolves based on the FOMC statement.",
            "price": 0.01,
        }

        parsed = parse_polymarket_fed_decision(row)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["meetingDate"], "2026-06-17")
        self.assertEqual(parsed["deltaBps"], -25)
        self.assertEqual(parsed["bucket"], "cut-25")

    def test_parses_kalshi_kxfed_thresholds(self):
        parsed = parse_kalshi_kxfed({
            "ticker": "KXFED-26JUN-T3.75",
            "seriesTicker": "KXFED",
            "title": "Will the upper bound of the federal funds rate be above 3.75% following the Fed's Jun 17, 2026 meeting?",
            "yesBid": 0.02,
            "yesAsk": 0.03,
        })

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["meetingDate"], "2026-06-17")
        self.assertEqual(parsed["thresholdUpperBound"], 3.75)

    def test_missing_prior_source_blocks_comparison_even_with_same_meeting_pairs(self):
        payload = build_fixture(
            macro_snapshot=[
                {
                    "venue": "polymarket",
                    "externalId": "pm-no-change",
                    "marketQuestion": "Will there be no change in Fed interest rates after the June 2026 meeting?",
                    "expiry": "2026-06-17T00:00:00Z",
                    "settlementText": "This market resolves to the amount of basis points the upper bound is changed by versus prior.",
                    "price": 0.98,
                }
            ],
            kalshi_fillability={
                "topExecutable": [
                    {
                        "ticker": "KXFED-26JUN-T3.50",
                        "seriesTicker": "KXFED",
                        "title": "Will the upper bound of the federal funds rate be above 3.50% following the Fed's Jun 17, 2026 meeting?",
                        "yesBid": 0.96,
                        "yesAsk": 0.97,
                    }
                ]
            },
            prior_upper_bound=None,
            prior_source=None,
        )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["sameMeetingPairCount"], 1)
        self.assertEqual(payload["comparablePairCount"], 0)
        self.assertIn("missing-explicit-prior-upper-bound-source", payload["blockers"])

    def test_explicit_prior_builds_truth_table_without_execution_approval(self):
        payload = build_fixture(
            macro_snapshot=[
                {
                    "venue": "polymarket",
                    "externalId": "pm-no-change",
                    "marketQuestion": "Will there be no change in Fed interest rates after the June 2026 meeting?",
                    "expiry": "2026-06-17T00:00:00Z",
                    "settlementText": "This market resolves to the amount of basis points the upper bound is changed by versus prior.",
                    "price": 0.98,
                },
                {
                    "venue": "polymarket",
                    "externalId": "pm-cut-25",
                    "marketQuestion": "Will the Fed decrease interest rates by 25 bps after the June 2026 meeting?",
                    "expiry": "2026-06-17T00:00:00Z",
                    "settlementText": "This market resolves to the amount of basis points the upper bound is changed by versus prior.",
                    "price": 0.01,
                },
            ],
            kalshi_fillability={
                "topExecutable": [
                    {
                        "ticker": "KXFED-26JUN-T3.50",
                        "seriesTicker": "KXFED",
                        "title": "Will the upper bound of the federal funds rate be above 3.50% following the Fed's Jun 17, 2026 meeting?",
                    },
                    {
                        "ticker": "KXFED-26JUN-T3.75",
                        "seriesTicker": "KXFED",
                        "title": "Will the upper bound of the federal funds rate be above 3.75% following the Fed's Jun 17, 2026 meeting?",
                    },
                ]
            },
            prior_upper_bound=3.75,
            prior_source="test-official-source",
        )

        self.assertEqual(payload["decision"], "research-only-fed-kalshi-parser-fixture-ready")
        self.assertEqual(payload["sameMeetingPairCount"], 4)
        self.assertEqual(payload["comparablePairCount"], 4)
        self.assertFalse(payload["readyForPaper"])

    def test_resolves_prior_from_official_source_artifact(self):
        with TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "fed-prior.json"
            artifact.write_text(
                """
{
  "decision": "research-only-fed-prior-upper-bound-source-ready",
  "dataUsable": true,
  "effectiveDate": "2025-12-11",
  "priorUpperBound": 3.75,
  "source": {"url": "https://www.federalreserve.gov/monetarypolicy/openmarket.htm"}
}
""".strip()
            )

            prior, source = resolve_prior(
                explicit_prior=None,
                explicit_source="manual-unset",
                source_artifact=artifact,
            )

        self.assertEqual(prior, 3.75)
        self.assertIn("federalreserve.gov", source)
        self.assertIn("effectiveDate=2025-12-11", source)


if __name__ == "__main__":
    unittest.main()
