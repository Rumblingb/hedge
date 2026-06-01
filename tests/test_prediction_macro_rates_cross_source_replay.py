import unittest

from scripts.prediction_macro_rates_cross_source_replay import build_replay


class PredictionMacroRatesCrossSourceReplayTests(unittest.TestCase):
    def test_builds_research_only_replay_rows(self):
        payload = build_replay(
            parser_fixture={
                "decision": "research-only-fed-kalshi-parser-fixture-ready",
                "polymarketFedDecisions": [
                    {"externalId": "pm-no-change", "price": 0.8},
                    {"externalId": "pm-cut", "price": 0.2},
                ],
                "kalshiKxfedThresholds": [
                    {
                        "ticker": "KXFED-26JUN-T3.50",
                        "question": "Above 3.50?",
                        "thresholdUpperBound": 3.5,
                        "yesBid": 0.6,
                        "yesAsk": 0.62,
                    }
                ],
                "sameMeetingPairs": [
                    {
                        "kalshiTicker": "KXFED-26JUN-T3.50",
                        "polymarketExternalId": "pm-no-change",
                        "polymarketBucket": "no-change",
                        "meetingDate": "2026-06-17",
                        "kalshiYesIfPolymarketBucketWins": True,
                    },
                    {
                        "kalshiTicker": "KXFED-26JUN-T3.50",
                        "polymarketExternalId": "pm-cut",
                        "polymarketBucket": "cut-25",
                        "meetingDate": "2026-06-17",
                        "kalshiYesIfPolymarketBucketWins": False,
                    },
                ],
            },
            requirements={"decision": "research-only-macro-rates-requirements-cleared"},
            min_edge_pct=3.0,
            max_spread_pct=5.0,
            min_sample_rows=1,
            slippage_pct=0.0,
            polymarket_macro_fee_rate=0.0,
            kalshi_taker_fee_multiplier=0.0,
        )

        self.assertEqual(payload["decision"], "research-only-macro-rates-cross-source-replay-complete")
        self.assertEqual(payload["rowCount"], 1)
        self.assertEqual(payload["rows"][0]["polymarketImpliedYesProbability"], 0.8)
        self.assertEqual(payload["rows"][0]["feeStress"]["yesNetEdgePctVsAsk"], 18.0)
        self.assertTrue(payload["rows"][0]["feeStress"]["edgeSurvivesFeeStress"])
        self.assertEqual(payload["watchResearchCount"], 1)
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_fee_stress_and_sample_depth_block_watch_rows(self):
        payload = build_replay(
            parser_fixture={
                "decision": "research-only-fed-kalshi-parser-fixture-ready",
                "polymarketFedDecisions": [
                    {"externalId": "pm-no-change", "price": 0.99},
                    {"externalId": "pm-cut", "price": 0.01},
                ],
                "kalshiKxfedThresholds": [
                    {
                        "ticker": "KXFED-26JUN-T3.50",
                        "question": "Above 3.50?",
                        "thresholdUpperBound": 3.5,
                        "yesBid": 0.94,
                        "yesAsk": 0.95,
                    }
                ],
                "sameMeetingPairs": [
                    {
                        "kalshiTicker": "KXFED-26JUN-T3.50",
                        "polymarketExternalId": "pm-no-change",
                        "polymarketBucket": "no-change",
                        "meetingDate": "2026-06-17",
                        "kalshiYesIfPolymarketBucketWins": True,
                    },
                    {
                        "kalshiTicker": "KXFED-26JUN-T3.50",
                        "polymarketExternalId": "pm-cut",
                        "polymarketBucket": "cut-25",
                        "meetingDate": "2026-06-17",
                        "kalshiYesIfPolymarketBucketWins": False,
                    },
                ],
            },
            requirements={"decision": "research-only-macro-rates-requirements-cleared"},
            min_edge_pct=3.0,
            max_spread_pct=5.0,
            min_sample_rows=20,
        )

        self.assertEqual(payload["watchResearchCount"], 0)
        self.assertIn("too-few-source-specific-sample-rows", payload["blockers"])
        self.assertIn("sample-size-too-small", payload["rows"][0]["blockers"])
        self.assertIn("yesNetEdgePctVsAsk", payload["rows"][0]["feeStress"])
        self.assertTrue(payload["rows"][0]["feeStress"]["edgeSurvivesFeeStress"])
        self.assertFalse(payload["readyForPaper"])

    def test_blocks_when_requirements_are_not_cleared(self):
        payload = build_replay(
            parser_fixture={"decision": "research-only-fed-kalshi-parser-fixture-ready"},
            requirements={"decision": "research-only-macro-rates-requirements-not-cleared"},
        )

        self.assertEqual(payload["decision"], "research-only-macro-rates-cross-source-replay-blocked")
        self.assertIn("macro-rates-requirements-not-cleared", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
