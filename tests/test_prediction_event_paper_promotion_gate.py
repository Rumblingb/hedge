import unittest

from scripts.prediction_event_paper_promotion_gate import build_gate


class PredictionEventPaperPromotionGateTests(unittest.TestCase):
    def test_forward_capture_watch_stays_blocked_without_paper_grade_evidence(self):
        payload = build_gate(
            capture_cycle={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "captureCycleEvidencePassed": True,
                "paperPromotionEvidencePassed": False,
                "paperPromotionBlockers": [
                    "paper-review-requires-positive-fillability-and-spread-adjusted-replay",
                ],
                "completeWindowCount": 5,
                "repricedWindowCount": 1,
                "executedRecorder": {
                    "publicMarketDataOnly": True,
                    "tokenIds": ["selected-review-token"],
                    "writesOrders": False,
                    "touchesBroker": False,
                },
                "latestRecorder": {
                    "writesOrders": False,
                    "liveQualityDiagnostics": {
                        "fillableLiveBookCount": 1,
                        "statusCounts": {"fillable-live-book": 1},
                    },
                },
            },
            manual_review={
                "decision": "research-only-manual-review-watch",
                "decisionCounts": {"keep-watch": 1},
                "forwardCaptureEvidencePresent": True,
                "writesOrders": False,
                "touchesBroker": False,
                "blockers": ["paper-promotion-evidence-still-required-after-forward-capture"],
            },
            event_requirements={
                "decision": "research-only-event-lag-requirements-not-cleared",
                "researchOnly": True,
                "blockedCount": 1,
            },
            event_label_gap_plan={
                "decision": "research-only-label-gaps-cleared-but-event-requirements-blocked",
                "gapCount": 0,
                "eventMappedGapCount": 0,
                "blockedRequirements": ["clob-around-event-window"],
            },
            resolved_join={
                "decision": "research-only; resolved outcomes are context until spread, fillability, fees, and promotion review agree",
                "readyForPaper": False,
                "joinedResearchOnlyCount": 1,
                "statusCounts": {"joined-research-only": 1},
            },
            label_manifest={
                "decision": "research-only; build better resolved labels before paper/demo promotion",
                "readyForPaper": False,
                "usableForResearchJoinCount": 3,
            },
            market_mapping={
                "decision": "research-only-event-market-mapping-blocked",
                "readyForPaper": False,
                "ambiguousHeadlineCount": 1,
                "ambiguousCounterpartyHeadlineCount": 1,
                "blockers": ["ambiguous-headline-event-family-fanout"],
            },
            mapping_refinement={
                "decision": "research-only-mapping-refinement-ready-for-forward-capture",
                "readyForPaper": False,
                "blockers": [],
            },
            clob_microstructure={
                "decision": "research-only-current-fixed-features-exhausted",
                "readyForPaper": False,
                "readyFeatureCount": 0,
            },
            clob_edge_gate={
                "status": "REJECT_NO_EDGE",
                "readyForPaper": False,
                "watchResearchGroups": 0,
                "writesOrders": False,
                "touchesBroker": False,
            },
        )

        self.assertEqual(payload["decision"], "research-only-paper-promotion-blocked")
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertIn("forward-public-clob-capture", [row["id"] for row in payload["checklist"] if row["status"] == "pass"])
        self.assertIn("manual-review-watch", [row["id"] for row in payload["checklist"] if row["status"] == "pass"])
        self.assertIn("no-lookahead-event-window", payload["blockedIds"])
        self.assertIn("resolved-label-paper-coverage", payload["blockedIds"])
        self.assertIn("event-market-mapping-clean", payload["blockedIds"])
        self.assertIn("post-spread-clob-edge", payload["blockedIds"])
        self.assertIn("research-safety-locks", [row["id"] for row in payload["checklist"] if row["status"] == "pass"])

    def test_fillable_forward_capture_without_repriced_window_gets_precise_blocker(self):
        payload = build_gate(
            capture_cycle={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "captureCycleEvidencePassed": False,
                "paperPromotionEvidencePassed": False,
                "completeWindowCount": 0,
                "repricedWindowCount": 0,
                "executedRecorder": {
                    "publicMarketDataOnly": True,
                    "tokenIds": ["selected-review-token"],
                    "writesOrders": False,
                    "touchesBroker": False,
                },
                "latestRecorder": {
                    "writesOrders": False,
                    "liveQualityDiagnostics": {
                        "fillableLiveBookCount": 1,
                        "statusCounts": {"fillable-live-book": 1},
                    },
                },
            },
            manual_review={
                "decision": "research-only-manual-review-watch",
                "decisionCounts": {"keep-watch": 1},
                "forwardCaptureEvidencePresent": True,
                "writesOrders": False,
                "touchesBroker": False,
            },
            event_requirements={"researchOnly": True, "blockedCount": 1},
            event_label_gap_plan={"gapCount": 0, "eventMappedGapCount": 0, "blockedRequirements": ["clob-around-event-window"]},
            resolved_join={"readyForPaper": False, "joinedResearchOnlyCount": 1},
            label_manifest={"readyForPaper": False},
            market_mapping={"readyForPaper": False, "ambiguousHeadlineCount": 1, "ambiguousCounterpartyHeadlineCount": 0, "blockers": []},
            mapping_refinement={"readyForPaper": False, "blockers": []},
            clob_microstructure={"readyForPaper": False, "readyFeatureCount": 0},
            clob_edge_gate={"readyForPaper": False, "watchResearchGroups": 0, "writesOrders": False, "touchesBroker": False},
        )

        forward_capture = next(row for row in payload["checklist"] if row["id"] == "forward-public-clob-capture")
        self.assertEqual(forward_capture["status"], "blocked")
        self.assertTrue(forward_capture["evidence"]["safePublicCapturePresent"])
        self.assertEqual(forward_capture["evidence"]["fillableLiveBookCount"], 1)
        self.assertIn("no no-lookahead repriced complete event window", forward_capture["blocker"])
        self.assertNotIn("missing or unsafe", forward_capture["blocker"])

    def test_all_subgates_can_mark_paper_review_ready_without_execution(self):
        payload = build_gate(
            capture_cycle={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "captureCycleEvidencePassed": True,
                "paperPromotionEvidencePassed": True,
                "completeWindowCount": 8,
                "repricedWindowCount": 3,
                "executedRecorder": {
                    "publicMarketDataOnly": True,
                    "tokenIds": ["token"],
                    "writesOrders": False,
                    "touchesBroker": False,
                },
                "latestRecorder": {"writesOrders": False},
            },
            manual_review={
                "decision": "research-only-manual-review-watch",
                "decisionCounts": {"keep-watch": 1},
                "forwardCaptureEvidencePresent": True,
                "writesOrders": False,
                "touchesBroker": False,
            },
            event_requirements={"researchOnly": True, "blockedCount": 0},
            event_label_gap_plan={"gapCount": 0, "eventMappedGapCount": 0, "blockedRequirements": []},
            resolved_join={"readyForPaper": True, "joinedResearchOnlyCount": 5},
            label_manifest={"readyForPaper": True},
            market_mapping={
                "readyForPaper": True,
                "ambiguousHeadlineCount": 0,
                "ambiguousCounterpartyHeadlineCount": 0,
                "blockers": [],
            },
            mapping_refinement={"readyForPaper": True, "blockers": []},
            clob_microstructure={"readyForPaper": True, "readyFeatureCount": 1},
            clob_edge_gate={
                "readyForPaper": True,
                "watchResearchGroups": 2,
                "writesOrders": False,
                "touchesBroker": False,
            },
        )

        self.assertEqual(payload["decision"], "paper-promotion-review-ready")
        self.assertTrue(payload["readyForPaper"])
        self.assertTrue(payload["readyForPaperReview"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["movesFunds"])
        self.assertEqual(payload["blockedIds"], [])


if __name__ == "__main__":
    unittest.main()
