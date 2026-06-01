import unittest

from scripts.prediction_event_market_mapping_plan import (
    VAULT,
    actor_tokens,
    build_plan,
    candidate_for,
    default_markdown_path,
    event_families,
    render_markdown,
)


class PredictionEventMarketMappingPlanTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-event-market-mapping-plan-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "candidateCount": 0,
            "minimumCandidates": 0,
            "categories": {},
            "blockers": [],
            "ambiguousHeadlineCount": 0,
            "ambiguousCounterpartyHeadlineCount": 0,
            "ambiguousHeadlineFamilyFanout": [],
            "ambiguousHeadlineCounterpartyFanout": [],
            "candidates": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Event Market Mapping Plan - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_requires_subject_and_family_overlap(self):
        article = {"headline": "Trump weighs extending Iran ceasefire", "source": "unit", "datetime": 1}
        good_market = {
            "externalId": "iran-1",
            "venue": "polymarket",
            "category": "geopolitics",
            "marketQuestion": "US announces new Iran agreement/ceasefire extension by June 3?",
            "settlementText": "Resolves Yes if the United States and Iran extend a ceasefire agreement.",
        }
        broad_market = {
            "externalId": "pm-1",
            "venue": "polymarket",
            "category": "politics",
            "marketQuestion": "Will prediction markets be banned?",
            "settlementText": "Resolves based on market regulation.",
        }

        self.assertIsNotNone(candidate_for(article, good_market))
        self.assertIsNone(candidate_for(article, broad_market))

    def test_flags_headline_with_multiple_event_families(self):
        article = {
            "headline": "With inflation high, a peace deal with Iran could still spell a Fed rate hike",
            "source": "unit",
            "datetime": 1,
        }
        markets = [
            {
                "externalId": "iran-peace",
                "venue": "polymarket",
                "category": "geopolitics",
                "marketQuestion": "US x Iran permanent peace deal by June 30, 2026?",
                "settlementText": "Permanent peace deal or ceasefire agreement between the United States and Iran.",
            },
            {
                "externalId": "fed-hike",
                "venue": "polymarket",
                "category": "macro-rates",
                "marketQuestion": "Will the Fed increase interest rates after the June 2026 meeting?",
                "settlementText": "Resolves based on Federal Reserve target interest rates.",
            },
        ]

        self.assertEqual(event_families(article["headline"]), {"geopolitical-agreement", "macro-rates"})

        payload = build_plan(news={"articles": [article]}, markets=markets, minimum_candidates=1)

        self.assertIn("ambiguous-headline-event-family-fanout", payload["blockers"])
        self.assertEqual(payload["ambiguousHeadlineCount"], 1)
        self.assertEqual(payload["ambiguousCounterpartyHeadlineCount"], 1)
        self.assertEqual(len(payload["ambiguousHeadlineFamilyFanout"]), 1)
        self.assertEqual(len(payload["ambiguousHeadlineCounterpartyFanout"]), 1)
        self.assertTrue(payload["headlineFamilyFanout"][0]["ambiguous"])
        self.assertTrue(payload["headlineFamilyFanout"][0]["counterpartyAmbiguous"])
        self.assertTrue(payload["ambiguousHeadlineFamilyFanout"][0]["ambiguous"])
        self.assertIn("ambiguous-headline-family-review-required", payload["headlineFamilyFanout"][0]["mappingStatuses"])
        self.assertEqual(payload["candidates"][0]["mappingStatus"], "ambiguous-headline-family-review-required")
        self.assertIn("headline-has-multiple-event-families", payload["candidates"][0]["specificityFlags"])
        self.assertIn("market-counterparty-not-explicit-in-headline", payload["candidates"][0]["specificityFlags"])
        self.assertEqual(actor_tokens("United States and Iran peace deal"), {"us", "iran"})
        self.assertEqual(payload["candidates"][0]["missingHeadlineActors"], ["us"])

    def test_flags_geopolitical_counterparty_fanout_without_event_family_ambiguity(self):
        article = {
            "headline": "Iran ceasefire talks continue",
            "source": "unit",
            "datetime": 1,
        }
        markets = [
            {
                "externalId": "us-iran",
                "venue": "polymarket",
                "category": "geopolitics",
                "marketQuestion": "US x Iran permanent peace deal by June 30, 2026?",
                "settlementText": "Permanent peace deal or ceasefire agreement between the United States and Iran.",
            },
            {
                "externalId": "israel-iran",
                "venue": "polymarket",
                "category": "geopolitics",
                "marketQuestion": "Israel x Iran permanent peace deal by June 30, 2026?",
                "settlementText": "Permanent peace deal or ceasefire agreement between Israel and Iran.",
            },
        ]

        payload = build_plan(news={"articles": [article]}, markets=markets, minimum_candidates=1)

        self.assertIn("ambiguous-headline-counterparty-fanout", payload["blockers"])
        self.assertEqual(payload["ambiguousHeadlineCount"], 0)
        self.assertEqual(payload["ambiguousCounterpartyHeadlineCount"], 1)
        self.assertEqual(payload["ambiguousHeadlineFamilyFanout"], [])
        self.assertEqual(len(payload["ambiguousHeadlineCounterpartyFanout"]), 1)
        self.assertEqual(
            payload["ambiguousHeadlineCounterpartyFanout"][0]["marketActorSets"],
            [["iran", "israel"], ["iran", "us"]],
        )
        self.assertEqual(payload["candidates"][0]["mappingStatus"], "counterparty-review-required")
        self.assertIn("market-counterparty-not-explicit-in-headline", payload["candidates"][0]["specificityFlags"])

    def test_build_plan_is_research_only_and_counts_candidates(self):
        news = {
            "articles": [
                {"headline": "US and Iran ceasefire extension talks continue", "source": "unit", "datetime": 1},
            ]
        }
        markets = [
            {
                "externalId": f"iran-{idx}",
                "venue": "polymarket",
                "category": "geopolitics",
                "marketQuestion": f"US x Iran permanent peace deal by month {idx}?",
                "settlementText": "Permanent peace deal or ceasefire agreement between the United States and Iran.",
            }
            for idx in range(3)
        ]

        payload = build_plan(news=news, markets=markets, minimum_candidates=3)

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["candidateCount"], 3)
        self.assertEqual(payload["decision"], "research-only-event-market-mapping-candidates-ready")
        self.assertEqual(payload["ambiguousHeadlineCount"], 0)
        self.assertEqual(payload["ambiguousCounterpartyHeadlineCount"], 0)
        self.assertEqual(payload["ambiguousHeadlineFamilyFanout"], [])
        self.assertEqual(payload["ambiguousHeadlineCounterpartyFanout"], [])


if __name__ == "__main__":
    unittest.main()
