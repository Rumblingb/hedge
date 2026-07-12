import unittest

from scripts.prediction_macro_rates_requirements import (
    VAULT,
    build_requirements,
    default_markdown_path,
    render_markdown,
)


class PredictionMacroRatesRequirementsTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-macro-rates-requirements-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "passCount": 0,
            "blockedCount": 0,
            "requirements": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Macro/Rates Requirements - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_parser_mismatch_blocks_macro_rates_research(self):
        payload = build_requirements(
            fillability={
                "executablePublicQuotes": 20,
                "bucketCounts": {"tight": 10, "usable": 10},
                "topExecutable": [
                    {"seriesTicker": "KXFED", "executable": True},
                    {"seriesTicker": "KXCPI", "executable": True},
                ],
            },
            narrow_scan={
                "reports": [
                    {
                        "category": "macro-rates",
                        "viablePairs": 0,
                        "diagnostics": {
                            "crossVenuePairs": 3068,
                            "rejectReasons": {
                                "market-type-mismatch": 3068,
                                "outcome-mismatch": 3068,
                                "temporal-mismatch": 2783,
                            },
                        },
                    }
                ]
            },
            macro_snapshot=[
                {
                    "marketQuestion": "Will the Fed decrease interest rates by 25 bps after the June 2026 meeting?",
                    "settlementText": "FOMC calendar https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm and open market https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
                },
                {"marketQuestion": "Will the Fed make no change after the June 2026 meeting?"},
            ],
            label_manifest={"usableForResearchJoinCount": 1, "items": []},
            parser_fixture={
                "decision": "research-only-fed-kalshi-parser-fixture-blocked",
                "blockers": ["missing-explicit-prior-upper-bound-source"],
                "comparablePairCount": 0,
            },
        )

        by_id = {item["id"]: item for item in payload["requirements"]}

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["decision"], "research-only-macro-rates-requirements-not-cleared")
        self.assertEqual(by_id["public-macro-quotes-fillable-enough-for-research"]["status"], "pass")
        self.assertEqual(by_id["polymarket-fed-decision-source-card"]["status"], "pass")
        self.assertEqual(by_id["source-specific-parser-normalization"]["status"], "blocked")
        self.assertEqual(by_id["macro-rates-resolved-label-history"]["status"], "blocked")

    def test_macro_rates_research_gate_can_clear_without_paper_approval(self):
        payload = build_requirements(
            fillability={
                "executablePublicQuotes": 5,
                "bucketCounts": {"tight": 2},
                "topExecutable": [{"seriesTicker": "KXFED", "executable": True}],
            },
            narrow_scan={
                "reports": [
                    {
                        "category": "macro-rates",
                        "viablePairs": 4,
                        "diagnostics": {"crossVenuePairs": 4, "rejectReasons": {}},
                    }
                ]
            },
            macro_snapshot=[
                {
                    "marketQuestion": "Will the Fed decrease interest rates by 25 bps after the June 2026 meeting?",
                    "settlementText": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
                },
                {"marketQuestion": "Will the Fed make no change after the June 2026 meeting?"},
            ],
            label_manifest={
                "usableForResearchJoinCount": 3,
                "coverage": [
                    {"category": "macro-rates", "status": "usable-for-research-join"},
                    {"category": "macro-rates", "status": "usable-for-research-join"},
                    {"category": "macro-rates", "status": "usable-for-research-join"},
                ],
            },
            parser_fixture={
                "decision": "research-only-fed-kalshi-parser-fixture-ready",
                "blockers": [],
                "comparablePairCount": 4,
            },
            resolved_labels={
                "decision": "research-only-macro-rates-resolved-labels-blocked",
                "usableForResearchJoinCount": 0,
                "officialComparableCount": 0,
                "officialAgreementRate": 0.0,
            },
        )

        self.assertEqual(payload["blockedCount"], 0)
        self.assertEqual(payload["decision"], "research-only-macro-rates-requirements-cleared")
        self.assertFalse(payload["readyForPaper"])

    def test_official_resolved_label_artifact_can_clear_macro_label_requirement(self):
        payload = build_requirements(
            fillability={
                "executablePublicQuotes": 5,
                "bucketCounts": {"tight": 2},
                "topExecutable": [{"seriesTicker": "KXFED", "executable": True}],
            },
            narrow_scan={
                "reports": [
                    {
                        "category": "macro-rates",
                        "viablePairs": 4,
                        "diagnostics": {"crossVenuePairs": 4, "rejectReasons": {}},
                    }
                ]
            },
            macro_snapshot=[
                {
                    "marketQuestion": "Will the Fed decrease interest rates by 25 bps after the June 2026 meeting?",
                    "settlementText": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
                },
                {"marketQuestion": "Will the Fed make no change after the June 2026 meeting?"},
            ],
            label_manifest={"usableForResearchJoinCount": 0, "coverage": []},
            parser_fixture={
                "decision": "research-only-fed-kalshi-parser-fixture-ready",
                "blockers": [],
                "comparablePairCount": 4,
            },
            resolved_labels={
                "decision": "research-only-macro-rates-resolved-labels-ready",
                "usableForResearchJoinCount": 20,
                "officialComparableCount": 20,
                "officialAgreementRate": 1.0,
                "blockers": [],
            },
        )

        by_id = {item["id"]: item for item in payload["requirements"]}

        self.assertEqual(by_id["macro-rates-resolved-label-history"]["status"], "pass")
        self.assertEqual(payload["decision"], "research-only-macro-rates-requirements-cleared")


if __name__ == "__main__":
    unittest.main()
