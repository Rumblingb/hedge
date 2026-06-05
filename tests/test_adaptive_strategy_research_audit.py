import unittest
from pathlib import Path

from scripts import adaptive_strategy_research_audit as audit


class AdaptiveStrategyResearchAuditTest(unittest.TestCase):
    def build_payload(self):
        return audit.build_audit(
            build_plan_text="The bet: 53/56 strategies have positive expectancy. Multi-TF entry (+6% R improvement).",
            build_plan_path=Path("build-plan.md"),
            factory={
                "status": "blocked",
                "quantCoverage": {"profilesEvaluated": 53},
                "gates": {"walkforwardDeployable": False},
                "researchContext": {
                    "noEdgeLedger": {
                        "learningSummary": {
                            "promotableProfiles": 0,
                            "needsMoreDataProfiles": 53,
                        }
                    }
                },
            },
            one_variable={
                "resultSummary": {
                    "bestObserved": {
                        "experimentId": "ny-morning-only",
                        "baselineId": "orb-breakout-15m",
                        "oosTradeCount": 50,
                        "oosNetPoints": 713.25,
                        "oosProfitFactor": 1.4629239,
                        "walkforwardPositiveFoldShare": 1.0,
                        "blockers": ["walkforward-oos-profit-factor-too-low"],
                    },
                    "nextFollowUp": {
                        "oneVariable": "walkforward PF/cost stress detail only",
                        "why": "Strongest blocked watch result.",
                    },
                }
            },
            entry={
                "bestResearchWatch": {
                    "id": "long_on_1m_red_candle_after_15m_bullish_signal",
                    "coveragePct": 9.2715,
                    "oos": {
                        "tradeCount": 5,
                        "netPoints": 303.1094,
                        "profitFactor": 5.762247,
                    },
                    "blockers": ["too-few-oos-trades", "coverage-too-thin"],
                }
            },
            no_edge={
                "decision": "research-only-futures-no-edge-memory",
                "count": 3,
                "noEdgeCount": 1,
                "needsNewFeatureCount": 1,
                "promotableCount": 0,
                "entries": [
                    {
                        "id": "entry-hypothesis-fakeout_retrace_filter_skip_large_upper_wick",
                        "verdict": "no-edge",
                    },
                    {
                        "id": "entry-hypothesis-long_on_1m_red_candle_after_15m_bullish_signal",
                        "verdict": "needs-new-feature",
                    },
                ],
            },
            walkforward={
                "status": "reject",
                "configs": [
                    {
                        "id": "fixed-20d-5d",
                        "summary": {
                            "deployableWindows": 0,
                            "positiveWindows": 0,
                            "totalTrades": 3,
                            "netR": -1.9,
                            "profitFactor": 0.11,
                        },
                    }
                ],
            },
            hermes_notes={
                "founder": "Capital permission ZERO_NEW_RISK. No-trade is valid. One-variable tests only. Broker proof required.",
                "handoff": "The strategy loop is a research harness, not an execution engine.",
                "session": "Session shadow turns first trade into learning data. Keep 50K policy separate from 100K demo context.",
            },
        )

    def test_positive_expectancy_claim_is_not_promoted(self):
        payload = self.build_payload()

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])

        claim = payload["claimReview"][0]
        self.assertEqual(claim["claim"], "53/56 strategies have positive expectancy")
        self.assertEqual(claim["status"], "not-proven")
        self.assertEqual(claim["promotableProfiles"], 0)
        self.assertEqual(claim["needsMoreDataProfiles"], 53)
        self.assertIn("zero-promotable-profiles", claim["contradictions"])

    def test_factory_learning_summary_list_does_not_crash_claim_review(self):
        payload = audit.build_audit(
            build_plan_text="53/56 strategies have positive expectancy",
            build_plan_path=Path("build-plan.md"),
            factory={
                "status": "blocked",
                "quantCoverage": {"profilesEvaluated": 53},
                "gates": {"walkforwardDeployable": False},
                "researchContext": {
                    "noEdgeLedger": {
                        "learningSummary": ["shape changed"],
                        "needsMoreDataProfiles": 53,
                        "promotableProfiles": 0,
                    }
                },
            },
            one_variable={},
            entry={},
            no_edge={"promotableCount": 0, "needsNewFeatureCount": 53},
            walkforward={},
            hermes_notes={},
        )

        claim = payload["claimReview"][0]
        self.assertEqual(claim["status"], "not-proven")
        self.assertEqual(claim["needsMoreDataProfiles"], 53)

    def test_walkforward_stitched_oos_shape_is_summarized(self):
        payload = audit.build_audit(
            build_plan_text="",
            build_plan_path=Path("build-plan.md"),
            factory={},
            one_variable={},
            entry={},
            no_edge={},
            walkforward={
                "status": "reject",
                "configs": [
                    {
                        "configId": "fixed-20d-5d",
                        "stitchedOos": {
                            "deployableWindows": 0,
                            "positiveWindows": 0,
                            "totalTrades": 3,
                            "netTotalR": -1.9259,
                            "profitFactor": 0.1116,
                        },
                    }
                ],
            },
            hermes_notes={},
        )

        config = payload["walkforward"]["configs"][0]
        self.assertEqual(config["id"], "fixed-20d-5d")
        self.assertEqual(config["totalTrades"], 3)
        self.assertEqual(config["netR"], -1.9259)
        self.assertEqual(config["profitFactor"], 0.1116)

    def test_best_watches_remain_research_only(self):
        payload = self.build_payload()

        watches = {watch["id"]: watch for watch in payload["currentBestWatches"]}
        self.assertEqual(watches["ny-morning-only"]["status"], "watch-only")
        self.assertEqual(watches["ny-morning-only"]["oosTradeCount"], 50)
        self.assertFalse(watches["ny-morning-only"]["readyForExecution"])
        self.assertEqual(
            watches["long_on_1m_red_candle_after_15m_bullish_signal"]["status"],
            "needs-broker-grade-overlap",
        )
        self.assertEqual(
            watches["long_on_1m_red_candle_after_15m_bullish_signal"]["coveragePct"],
            9.2715,
        )

    def test_queue_prevents_retesting_retired_fakeout_form(self):
        payload = self.build_payload()

        queue = {item["id"]: item for item in payload["researchQueue"]}
        self.assertEqual(queue["fakeout-filter-redesign"]["status"], "current-form-retired")
        self.assertEqual(queue["daily-htf-regime-overlay"]["oneVariable"], "daily/higher-timeframe regime tag only")

    def test_markdown_surfaces_not_deployable_truth(self):
        payload = self.build_payload()
        markdown = audit.render_markdown(payload)

        self.assertIn("Ready for execution: `False`", markdown)
        self.assertIn("53/56 strategies have positive expectancy", markdown)
        self.assertIn("zero-promotable-profiles", markdown)
        self.assertIn("ny-morning-only", markdown)
        self.assertIn("Promotion Definition", markdown)

    def test_hermes_memory_alignment_is_machine_readable(self):
        payload = self.build_payload()
        alignment = payload["hermesMemoryAlignment"]

        self.assertTrue(alignment["signals"]["zeroNewRisk"])
        self.assertTrue(alignment["signals"]["researchHarnessNotExecutionEngine"])
        self.assertTrue(alignment["signals"]["sessionShadow"])
        self.assertTrue(alignment["signals"]["firstTradeLearningData"])
        self.assertTrue(alignment["signals"]["fiftyKPolicy"])
        self.assertIn("Convert mistake tags into one-variable research hypotheses", " ".join(alignment["hermesInstruction"]))


if __name__ == "__main__":
    unittest.main()
