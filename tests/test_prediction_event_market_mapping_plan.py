import unittest

from scripts.prediction_event_market_mapping_plan import (
    VAULT,
    actor_tokens,
    build_plan,
    candidate_for,
    default_markdown_path,
    event_families,
    render_markdown,
    subject_tokens,
)


class PredictionEventMarketMappingPlanTests(unittest.TestCase):
    def test_normalizes_crypto_subject_aliases(self):
        self.assertEqual(subject_tokens("BTC rallies"), {"bitcoin"})
        self.assertEqual(subject_tokens("Ethereum follows ETH"), {"ethereum"})

    def test_crypto_direction_must_match_market_line(self):
        article = {
            "headline": "BTC rallies and reaches a new weekly high",
            "source": "unit",
            "datetime": 1782202224,
        }
        down_market = {
            "externalId": "btc-down",
            "venue": "polymarket",
            "category": "crypto",
            "marketQuestion": "Will Bitcoin dip below $60,000 by June 30?",
            "settlementText": "Resolves using the BTC/USDT price on Binance.",
            "expiry": "2026-06-30T16:00:00Z",
        }
        up_market = {
            **down_market,
            "externalId": "btc-up",
            "marketQuestion": "Will Bitcoin reach above $70,000 by June 30?",
        }

        self.assertIsNone(candidate_for(article, down_market))
        candidate = candidate_for(article, up_market)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["subjectOverlap"], ["bitcoin"])
        self.assertEqual(candidate["eventFamilyOverlap"], ["crypto-price"])
        self.assertEqual(candidate["headlineCryptoDirections"], ["up"])
        self.assertEqual(candidate["marketCryptoDirections"], ["up"])

    def test_crypto_threshold_fanout_remains_ambiguous(self):
        article = {"headline": "Bitcoin rallies as momentum improves", "source": "unit", "datetime": 1782202224}
        markets = [
            {
                "externalId": f"btc-{level}",
                "venue": "polymarket",
                "category": "crypto",
                "marketQuestion": f"Will the price of Bitcoin be above ${level},000 by June 30?",
                "settlementText": "Resolves using the BTC/USDT price on Binance.",
                "expiry": "2026-06-30T16:00:00Z",
            }
            for level in (60, 70)
        ]

        payload = build_plan(news={"articles": [article]}, markets=markets, minimum_candidates=1)

        self.assertEqual(payload["candidateCount"], 2)
        self.assertIn("ambiguous-headline-market-line-fanout", payload["blockers"])
        self.assertTrue(all(item["mappingStatus"] == "ambiguous-market-line-review-required" for item in payload["candidates"]))

    def test_crypto_price_maps_only_to_compatible_band(self):
        article = {
            "headline": "Bitcoin crashes below $63K as liquidations top $500M",
            "source": "unit",
            "datetime": 1782202224,
        }
        range_market = {
            "externalId": "btc-range",
            "venue": "polymarket",
            "category": "crypto",
            "marketQuestion": "Will the price of Bitcoin be between $62,000 and $64,000 on June 23?",
            "settlementText": "Resolves using the BTC/USDT price on Binance.",
            "expiry": "2026-06-23T16:00:00Z",
        }
        low_market = {
            **range_market,
            "externalId": "btc-low",
            "marketQuestion": "Will the price of Bitcoin be less than $56,000 on June 23?",
        }

        candidate = candidate_for(article, range_market)
        self.assertIsNotNone(candidate)
        self.assertTrue(candidate["cryptoValueMatch"])
        self.assertEqual(candidate["headlineCryptoPriceValues"], [63000.0, 500000000.0])
        self.assertIsNone(candidate_for(article, low_market))

    def test_rejects_named_token_that_only_mentions_bitcoin_in_its_brand(self):
        article = {
            "headline": "BOB (Build on Bitcoin) price today, BOB to USD live price, marketcap and chart",
            "source": "unit",
            "datetime": 1782202224,
        }
        market = {
            "externalId": "btc-above",
            "venue": "polymarket",
            "category": "crypto",
            "marketQuestion": "Will the price of Bitcoin be above $64,000 on June 23?",
            "settlementText": "Resolves using the BTC/USDT price on Binance.",
            "expiry": "2026-06-23T16:00:00Z",
        }

        self.assertIsNone(candidate_for(article, market))

    def test_rejects_non_price_monetary_value_as_crypto_price(self):
        article = {
            "headline": "Bitcoin liquidations top $500M during selloff",
            "source": "unit",
            "datetime": 1782202224,
        }
        market = {
            "externalId": "btc-above",
            "venue": "polymarket",
            "category": "crypto",
            "marketQuestion": "Will the price of Bitcoin be above $64,000 on June 23?",
            "settlementText": "Resolves using the BTC/USDT price on Binance.",
            "expiry": "2026-06-23T16:00:00Z",
        }

        self.assertIsNone(candidate_for(article, market))

    def test_crypto_price_is_bound_to_the_nearest_named_asset(self):
        article = {
            "headline": "ETH, SOL, DOGE price news: Bitcoin under $63,000 amid tech selloff",
            "source": "unit",
            "datetime": 1782202224,
        }
        bitcoin_market = {
            "externalId": "btc-range",
            "venue": "polymarket",
            "category": "crypto",
            "marketQuestion": "Will the price of Bitcoin be between $62,000 and $64,000 on June 23?",
            "settlementText": "Resolves using the BTC/USDT price on Binance.",
            "expiry": "2026-06-23T16:00:00Z",
        }
        ethereum_market = {
            **bitcoin_market,
            "externalId": "eth-above",
            "marketQuestion": "Will the price of Ethereum be above $2,000 on June 23?",
        }

        candidate = candidate_for(article, bitcoin_market)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["cryptoMatchedSubjects"], ["bitcoin"])
        self.assertIsNone(candidate_for(article, ethereum_market))

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

    def test_rejects_commercial_deal_headline_from_geopolitical_market(self):
        article = {
            "headline": "Fanatics strikes deal to offer prediction markets in U.S.",
            "source": "unit",
            "datetime": 1782187153,
        }
        market = {
            "externalId": "iran-peace",
            "venue": "polymarket",
            "category": "geopolitics",
            "marketQuestion": "US x Iran permanent peace deal by June 30, 2026?",
            "settlementText": "Permanent peace agreement between the United States and Iran.",
            "expiry": "2026-12-31T00:00:00Z",
        }

        self.assertIsNone(candidate_for(article, market))

    def test_rejects_market_deadline_before_article_timestamp(self):
        article = {
            "headline": "U.S. and Iran agree to oil sanctions deal",
            "source": "unit",
            "datetime": 1782202224,
        }
        expired_market = {
            "externalId": "expired-oil",
            "venue": "polymarket",
            "category": "geopolitics",
            "marketQuestion": "Will the US agree to Iranian oil sanction relief by May 31?",
            "settlementText": "Resolves on an agreement between the United States and Iran.",
            "expiry": "2026-12-31T00:00:00Z",
        }
        active_market = {
            **expired_market,
            "externalId": "active-oil",
            "marketQuestion": "Will the US agree to Iranian oil sanction relief by June 30?",
        }

        self.assertIsNone(candidate_for(article, expired_market))
        self.assertIsNotNone(candidate_for(article, active_market))

    def test_rejects_rate_hike_headline_from_rate_cut_contract(self):
        article = {
            "headline": "Fed signals a series of rate hikes this year",
            "source": "unit",
            "datetime": 1782202224,
        }
        cut_market = {
            "externalId": "cut",
            "venue": "polymarket",
            "category": "macro-rates",
            "marketQuestion": "Will the Fed decrease interest rates by 25 bps after the July 2026 meeting?",
            "settlementText": "Resolves using the Federal Reserve target interest rate.",
            "expiry": "2026-07-29T00:00:00Z",
        }
        hike_market = {
            **cut_market,
            "externalId": "hike",
            "marketQuestion": "Will the Fed increase interest rates by 25 bps after the July 2026 meeting?",
        }

        self.assertIsNone(candidate_for(article, cut_market))
        self.assertIsNotNone(candidate_for(article, hike_market))

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
        self.assertEqual(payload["decision"], "research-only-event-market-mapping-blocked")
        self.assertIn("ambiguous-headline-market-line-fanout", payload["blockers"])
        self.assertEqual(payload["ambiguousMarketLineHeadlineCount"], 1)
        self.assertTrue(payload["headlineFamilyFanout"][0]["marketLineAmbiguous"])
        self.assertEqual(payload["candidates"][0]["mappingStatus"], "ambiguous-market-line-review-required")
        self.assertEqual(payload["ambiguousHeadlineCount"], 0)
        self.assertEqual(payload["ambiguousCounterpartyHeadlineCount"], 0)
        self.assertEqual(payload["ambiguousHeadlineFamilyFanout"], [])
        self.assertEqual(payload["ambiguousHeadlineCounterpartyFanout"], [])


if __name__ == "__main__":
    unittest.main()
