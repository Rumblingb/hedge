import unittest

from scripts.futures_evidence_triage import (
    build_next_tests,
    build_fabervaale_next_tests,
    databento_orderflow_summary,
    fabervaale_broker_grade_summary,
    fabervaale_cost_stress_summary,
    fabervaale_orb_comparison,
    fabervaale_orb_summary,
    fabervaale_walkforward_summary,
    lower_timeframe_current_form_rejected,
)


class FuturesEvidenceTriageTests(unittest.TestCase):
    def test_suppresses_rejected_lower_timeframe_current_forms(self):
        lower_timeframe = {
            "15m": {"status": "reject-current-oos"},
            "30m": {"status": "reject-current-oos"},
        }
        no_edge = {
            "entries": [
                {"id": "wq-vol-regime-15m-current-form", "verdict": "needs-new-feature"},
                {"id": "wq-vol-regime-30m-current-form", "verdict": "no-edge"},
            ]
        }

        tests = build_next_tests(
            walkforward_failures={"stitched-oos-sample-too-thin": 1},
            rolling_failures={"testTradeCount": 1},
            vol_summary={"aggregate": {"netR": 0}},
            inverse_summary={},
            lower_timeframe=lower_timeframe,
            cost_gate={},
            no_edge=no_edge,
        )

        self.assertTrue(lower_timeframe_current_form_rejected(no_edge, lower_timeframe))
        self.assertNotIn("lower-timeframe-vol-regime-current-form-rejected", [item["id"] for item in tests])
        self.assertNotIn("increase-oos-sample-before-parameter-mining", [item["id"] for item in tests])

    def test_suppresses_retired_60m_and_cost_survivor_review_from_no_edge_memory(self):
        no_edge = {
            "entries": [
                {"id": "wq-vol-regime-60m-current-form", "verdict": "no-edge"},
                {
                    "id": "backtrader-full-sample-survivors-with-zero-vol-oos-survivors",
                    "verdict": "no-edge",
                },
            ]
        }

        tests = build_next_tests(
            walkforward_failures={},
            rolling_failures={"deflatedExpectancyR": 2},
            vol_summary={"aggregate": {"netR": -12.5}},
            inverse_summary={"status": "reject-current-oos", "aggregate": {"netR": -3.0}},
            lower_timeframe={},
            cost_gate={"backtrader": {"rowsScored": 12}},
            no_edge=no_edge,
        )

        ids = [item["id"] for item in tests]
        self.assertNotIn("retire-vol-regime-60m-current-form", ids)
        self.assertNotIn("cost-slippage-survivor-review", ids)

    def test_fabervaale_orb_summary_keeps_thin_sample_blocked(self):
        summary = fabervaale_orb_summary({
            "decision": "research-only-historical-session-replay-blocked",
            "strategy": "fabervaale-orb",
            "tradeCount": 11,
            "oosStats": {"trades": 5, "netR": 1.02, "profitFactor": 2.0},
            "blockers": ["too-few-oos-trades", "too-few-trades-for-historical-replay"],
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        })

        self.assertTrue(summary["present"])
        self.assertEqual(summary["promotionDecision"], "blocked-thin-sample")
        self.assertTrue(summary["sampleBlocked"])
        self.assertFalse(summary["readyForExecution"])
        self.assertFalse(summary["readyForDemoExpansion"])
        self.assertFalse(summary["writesOrders"])
        self.assertFalse(summary["touchesBroker"])

    def test_fabervaale_comparison_keeps_local_watch_research_only(self):
        comparison = fabervaale_orb_comparison(
            {
                "decision": "research-only-historical-session-replay-blocked",
                "strategy": "fabervaale-orb",
                "tradeCount": 11,
                "oosStats": {"trades": 5},
                "blockers": ["too-few-oos-trades"],
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
            },
            {
                "decision": "research-only-historical-session-replay-watch",
                "strategy": "fabervaale-orb",
                "tradeCount": 34,
                "oosStats": {"trades": 14, "netR": 4.03, "profitFactor": 3.2},
                "blockers": [],
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
            },
        )

        self.assertEqual(
            comparison["decision"],
            "research-watch-needs-broker-grade-data-and-larger-clean-sample",
        )
        self.assertFalse(comparison["readyForDemoExpansion"])
        self.assertFalse(comparison["readyForExecution"])
        self.assertFalse(comparison["writesOrders"])
        self.assertFalse(comparison["touchesBroker"])
        self.assertEqual(comparison["local5m60dResearch"]["promotionDecision"], "watch-research-only")

    def test_fabervaale_broker_grade_summary_blocks_thin_topstep_replay(self):
        summary = fabervaale_broker_grade_summary({
            "decision": "research-only-historical-session-replay-blocked",
            "strategy": "fabervaale-orb",
            "inputPath": ".rumbling-hedge/research/topstep-readonly-bars/NQ-1m-topstep-readonly.csv",
            "tradeCount": 1,
            "oosStats": {"trades": 0, "netR": 0},
            "blockers": ["too-few-oos-trades", "too-few-trades-for-historical-replay"],
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        })

        self.assertEqual(summary["sourceRole"], "broker-grade-current-topstep-readonly")
        self.assertEqual(summary["promotionDecision"], "blocked-thin-sample")
        self.assertEqual(summary["oosTradeCount"], 0)
        self.assertIn("at least 50 OOS broker-grade trades", " ".join(summary["requiredNextEvidence"]))
        self.assertFalse(summary["readyForExecution"])
        self.assertFalse(summary["writesOrders"])

    def test_fabervaale_walkforward_summary_blocks_thin_fold_count(self):
        summary = fabervaale_walkforward_summary({
            "decision": "research-only-historical-session-walkforward-blocked",
            "foldSize": 10,
            "foldCount": 3,
            "positiveFoldShare": 1.0,
            "worstFoldNetR": 2.0,
            "aggregateStats": {"trades": 34, "netR": 8.8},
            "blockers": ["too-few-complete-walkforward-folds"],
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        })

        self.assertEqual(summary["promotionDecision"], "blocked-thin-walkforward-sample")
        self.assertTrue(summary["sampleBlocked"])
        self.assertFalse(summary["readyForDemoExpansion"])
        self.assertFalse(summary["readyForExecution"])
        self.assertFalse(summary["writesOrders"])
        self.assertFalse(summary["touchesBroker"])

    def test_fabervaale_cost_stress_summary_is_watch_only_even_when_cases_survive(self):
        summary = fabervaale_cost_stress_summary({
            "decision": "research-only-historical-session-cost-stress-watch",
            "caseCount": 2,
            "survivingCaseCount": 2,
            "cases": [
                {"costPointsRoundTrip": 2.0, "survives": True, "oosStats": {"netR": 4.0}},
                {"costPointsRoundTrip": 6.0, "survives": True, "oosStats": {"netR": 3.6}},
            ],
            "blockers": [],
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        })

        self.assertEqual(summary["promotionDecision"], "watch-research-only")
        self.assertTrue(summary["allCostCasesSurvive"])
        self.assertFalse(summary["readyForDemoExpansion"])
        self.assertFalse(summary["readyForExecution"])
        self.assertFalse(summary["writesOrders"])
        self.assertFalse(summary["touchesBroker"])
        self.assertIn("walk-forward sample depth must clear", summary["requiredNextEvidence"])

    def test_databento_orderflow_feature_smoke_is_never_execution_clearance(self):
        summary = databento_orderflow_summary({
            "status": "WATCH_RESEARCH_ONLY",
            "decision": "research-only-orderflow-feature-visible-execution-locked",
            "features": {
                "featureFamily": "databento-top-of-book-mbp1",
                "snapshotOnly": True,
                "researchUsable": True,
                "completeBidAsk": True,
                "completeDepthSize": True,
                "domProxyReplacementReady": False,
                "rows": [{"symbol": "NQ"}, {"symbol": "ES"}],
                "reason": "snapshot available",
            },
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        })

        self.assertTrue(summary["present"])
        self.assertTrue(summary["researchUsable"])
        self.assertTrue(summary["completeDepthSize"])
        self.assertFalse(summary["domProxyReplacementReady"])
        self.assertFalse(summary["readyForExecution"])
        self.assertFalse(summary["readyForDemoExpansion"])
        self.assertFalse(summary["writesOrders"])
        self.assertFalse(summary["touchesBroker"])
        self.assertTrue(any("rolling no-lookahead capture" in item for item in summary["requiredNextEvidence"]))

    def test_fabervaale_watch_artifacts_generate_actionable_next_tests(self):
        tests = build_fabervaale_next_tests(
            comparison={
                "local5m60dResearch": {
                    "promotionDecision": "watch-research-only",
                },
            },
            walkforward={
                "promotionDecision": "blocked-thin-walkforward-sample",
            },
            cost_stress={
                "promotionDecision": "watch-research-only",
            },
            orderflow={
                "researchUsable": False,
                "completeDepthSize": False,
            },
        )

        ids = [item["id"] for item in tests]
        self.assertEqual(ids[0], "fabervaale-orb-broker-grade-5m-depth")
        self.assertIn("fabervaale-orb-walkforward-depth", ids)
        self.assertIn("fabervaale-orb-cost-stress-holdout", ids)
        self.assertIn("orderflow-current-depth-capture", ids)
        self.assertTrue(all(item["track"] == "futures" for item in tests))


if __name__ == "__main__":
    unittest.main()
