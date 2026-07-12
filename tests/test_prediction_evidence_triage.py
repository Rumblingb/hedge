import unittest

from scripts.prediction_evidence_triage import (
    current_clob_drift_rejected,
    current_cross_venue_universe_rejected,
    current_resolved_outcome_review_rejected,
    event_forward_capture_summary,
    fillability_summary,
    macro_rates_summary,
    next_tests,
    resolved_outcome_review,
)


class PredictionEvidenceTriageTests(unittest.TestCase):
    def test_resolved_outcome_review_keeps_joined_history_research_only(self):
        review = resolved_outcome_review(
            [
                {
                    "externalId": "arg-2026",
                    "question": "Will Argentina win the 2026 FIFA World Cup?",
                    "status": "joined-research-only",
                    "resolvedMatchCount": 312,
                    "subjectSpecificMatchCount": 14,
                    "subjectSpecificWinRate": 0.571429,
                }
            ],
            [
                {
                    "externalId": "arg-2026",
                    "blockers": ["broad-by-price-prior-only", "not-joined-to-market-specific-resolution-history"],
                }
            ],
            {
                "joinedResearchOnlyCount": 1,
                "watchCount": 1,
                "historicalRowsLoaded": 59821,
                "minSpecificMatches": 5,
                "readyForPaper": False,
                "statusCounts": {"joined-research-only": 1},
            },
        )

        self.assertEqual(review["status"], "research-only")
        self.assertEqual(review["decision"], "do-not-promote-resolved-history-without-paper-review-and-fillability")
        self.assertEqual(review["broadPriorRisk"], "high")
        self.assertFalse(review["readyForPaper"])
        self.assertEqual(review["items"][0]["decision"], "context-only-not-paper")

    def test_fillability_summary_adds_guided_research_test_without_promotion(self):
        summary = fillability_summary({
            "researchOnly": True,
            "writesOrders": False,
            "marketsInspected": 416,
            "executablePublicQuotes": 27,
            "bucketCounts": {"tight": 14, "usable": 13},
            "topExecutable": [
                {"seriesTicker": "KXFED"},
                {"seriesTicker": "KXFED"},
                {"seriesTicker": "KXCPI"},
            ],
        })
        tests = next_tests({
            "review": {"counts": {"watch": 0}},
            "watchItems": [],
            "clob": {},
            "watchBlockers": {},
            "resolvedJoin": {},
            "fillability": summary,
        })

        self.assertFalse(summary["readyForPaper"])
        self.assertEqual(summary["topSeries"], {"KXFED": 2, "KXCPI": 1})
        self.assertEqual(tests[0]["id"], "kalshi-fillability-guided-rates-scan")
        self.assertIn("not sufficient", tests[0]["promotionRule"])

    def test_next_tests_suppresses_current_narrow_scan_when_no_edge_memory_rejects_it(self):
        no_edge = {
            "entries": [
                {
                    "id": "narrow-category-cross-venue-current-universe",
                    "verdict": "needs-more-data",
                    "currentFormRejected": True,
                },
                {"id": "crypto-settlement-horizon-parser-current-form", "verdict": "no-edge"},
                {"id": "macro-rates-line-parser-current-form", "verdict": "no-edge"},
            ]
        }
        tests = next_tests({
            "review": {"counts": {"watch": 0}},
            "watchItems": [],
            "clob": {},
            "watchBlockers": {},
            "resolvedJoin": {},
            "fillability": {},
            "noEdge": no_edge,
        })

        self.assertTrue(current_cross_venue_universe_rejected(no_edge))
        self.assertNotIn("narrow-cross-venue-normalization", [item["id"] for item in tests])

    def test_next_tests_suppresses_fillability_scan_for_rejected_current_universe(self):
        no_edge = {
            "entries": [
                {
                    "id": "narrow-category-cross-venue-current-universe",
                    "verdict": "needs-more-data",
                    "currentFormRejected": True,
                },
                {"id": "crypto-settlement-horizon-parser-current-form", "verdict": "no-edge"},
                {"id": "macro-rates-line-parser-current-form", "verdict": "no-edge"},
            ]
        }
        tests = next_tests({
            "review": {"counts": {"watch": 0}},
            "watchItems": [],
            "clob": {},
            "watchBlockers": {},
            "resolvedJoin": {},
            "fillability": {"executablePublicQuotes": 20},
            "noEdge": no_edge,
        })

        self.assertNotIn("kalshi-fillability-guided-rates-scan", [item["id"] for item in tests])

    def test_next_tests_suppresses_targeted_clob_capture_when_current_drift_is_no_edge(self):
        no_edge = {
            "entries": [
                {
                    "id": "polymarket-clob-drift-persistence-current-thresholds",
                    "verdict": "no-edge",
                }
            ]
        }
        tests = next_tests({
            "review": {"counts": {"watch": 0}},
            "watchItems": [
                {
                    "externalId": "x",
                    "question": "Test market?",
                    "clobTokenId": "123",
                    "spread": 0.01,
                    "clobCaptureEligible": True,
                }
            ],
            "clob": {"blockerCounts": {"net-drift-below-threshold": 1}},
            "watchBlockers": {},
            "resolvedJoin": {},
            "fillability": {},
            "noEdge": no_edge,
        })

        self.assertTrue(current_clob_drift_rejected(no_edge))
        self.assertNotIn("targeted-clob-persistence-capture", [item["id"] for item in tests])
        self.assertNotIn("reject-current-clob-drift-hypothesis", [item["id"] for item in tests])

    def test_next_tests_suppresses_resolved_outcome_review_when_current_watchlist_is_context_only(self):
        no_edge = {
            "entries": [
                {
                    "id": "resolved-outcome-current-watchlist-context-only",
                    "verdict": "needs-more-data",
                    "currentFormRejected": True,
                }
            ]
        }
        tests = next_tests({
            "review": {"counts": {"watch": 0}},
            "watchItems": [
                {
                    "externalId": "x",
                    "blockers": ["not-joined-to-market-specific-resolution-history"],
                }
            ],
            "clob": {},
            "watchBlockers": {"not-joined-to-market-specific-resolution-history": 1},
            "resolvedJoin": {"joinedResearchOnlyCount": 1},
            "fillability": {},
            "noEdge": no_edge,
        })

        self.assertTrue(current_resolved_outcome_review_rejected(no_edge))
        self.assertNotIn("resolved-outcome-join-review", [item["id"] for item in tests])

    def test_macro_rates_summary_exposes_research_progress_without_paper_promotion(self):
        summary = macro_rates_summary(
            {
                "decision": "research-only-macro-rates-requirements-cleared",
                "blockedCount": 0,
                "passCount": 5,
            },
            {
                "decision": "research-only-macro-rates-cross-source-replay-complete",
                "rows": [
                    {
                        "ticker": "KXFED-26JUN-T3.50",
                        "yesEdgePctVsAsk": 1.8,
                        "noEdgePctVsNoAsk": -2.8,
                        "blockers": ["research-only", "needs-sample-replay"],
                    },
                    {
                        "ticker": "KXFED-26JUN-T3.75",
                        "yesEdgePctVsAsk": -2.2,
                        "noEdgePctVsNoAsk": 1.3,
                        "watchResearchOnly": True,
                        "blockers": ["research-only", "fees-and-fillability-not-stressed"],
                    },
                ],
            },
        )

        self.assertTrue(summary["requirementsCleared"])
        self.assertTrue(summary["replayComplete"])
        self.assertEqual(summary["rowCount"], 2)
        self.assertEqual(summary["watchResearchOnlyCount"], 1)
        self.assertEqual(summary["paperBlockerCounts"]["research-only"], 2)
        self.assertFalse(summary["readyForPaper"])
        self.assertFalse(summary["readyForExecution"])
        self.assertFalse(summary["writesOrders"])
        self.assertFalse(summary["touchesBroker"])

    def test_event_forward_capture_summary_keeps_stale_events_as_forward_capture_only(self):
        summary = event_forward_capture_summary(
            {
                "decision": "research-only-forward-capture-required",
                "targetCount": 0,
                "tokenSpecificCandidateCount": 0,
                "excludedMappingCandidateCount": 2,
                "excludedMappingReasonCounts": {"headline-has-multiple-event-families": 2},
                "publicCaptureReviewLeadCount": 1,
                "reviewLeadRecorderCommand": "npm run --silent bill:polymarket-clob-recorder -- --token-id 'review-token'",
                "staleContextTargetCount": 15,
                "unrecoverablePreEventTargetCount": 15,
                "completeWindowTargetCount": 0,
                "coverageStatusCounts": {"no-quotes-for-clob-token": 3, "missing-pre-event-window": 12},
                "standingTerms": "fed,cpi,iran",
                "durationSec": 900,
                "maxOutputMb": 128,
                "minFreeGb": 20,
                "blockers": ["past-event-pre-window-unrecoverable-use-forward-capture"],
                "forwardCapturePlan": {
                    "required": True,
                    "reason": "No recoverable token-specific event windows are available; use standing term capture before/through future news.",
                    "command": "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --terms 'fed,cpi,iran'",
                    "followUp": [
                        "Run the standing recorder before/through expected news windows.",
                        "Refresh news and event-market mapping after capture.",
                    ],
                },
            },
            {
                "decision": "research-only-capture-cycle-ran-still-blocked",
                "blockers": ["event-lag-replay-not-watch-ready"],
                "eventLagReplayWatchReady": False,
                "eventLagResearchWatchReady": True,
                "eventLagWatchReview": {
                    "decision": "research-only-event-lag-watch-review-visible",
                    "watchReady": True,
                    "repricedWatchWindowCount": 2,
                    "blockers": ["manual-review-required-before-forward-capture-or-paper-discussion"],
                },
            },
            {
                "decision": "research-only-event-timestamp-dataset-ready",
                "candidateCount": 20,
                "coverageStatusCounts": {"window-range-present": 5, "missing-pre-and-post-window": 12},
                "completeWindowTargetCount": 5,
                "unrecoverablePreEventTargetCount": 15,
                "forwardCaptureRequired": True,
                "readyForPaper": False,
            },
        )

        self.assertTrue(summary["present"])
        self.assertTrue(summary["forwardCaptureRequired"])
        self.assertEqual(summary["tokenSpecificCandidateCount"], 0)
        self.assertEqual(summary["excludedMappingCandidateCount"], 2)
        self.assertEqual(summary["excludedMappingReasonCounts"], {"headline-has-multiple-event-families": 2})
        self.assertEqual(summary["publicCaptureReviewLeadCount"], 1)
        self.assertIn("review-token", summary["reviewLeadRecorderCommand"])
        self.assertEqual(summary["recordableTargetCount"], 0)
        self.assertEqual(summary["unrecoverablePreEventTargetCount"], 15)
        self.assertIn("--duration-sec 900", summary["standingRecorderCommand"])
        self.assertFalse(summary["readyForPaper"])
        self.assertFalse(summary["readyForExecution"])
        self.assertFalse(summary["eventLagReplayWatchReady"])
        self.assertTrue(summary["eventLagResearchWatchReady"])
        self.assertTrue(summary["eventLagWatchReview"]["present"])
        self.assertTrue(summary["eventLagWatchReview"]["watchReady"])
        self.assertEqual(summary["eventLagWatchReview"]["repricedWatchWindowCount"], 2)
        self.assertFalse(summary["writesOrders"])
        self.assertFalse(summary["touchesBroker"])
        self.assertIn("standing public CLOB capture", summary["requiredNextEvidence"][0])
        self.assertTrue(summary["timestampDataset"]["present"])
        self.assertEqual(summary["timestampDataset"]["candidateCount"], 20)
        self.assertEqual(summary["timestampDataset"]["completeWindowTargetCount"], 5)
        self.assertEqual(summary["timestampDataset"]["unrecoverablePreEventTargetCount"], 15)
        self.assertFalse(summary["timestampDataset"]["readyForPaper"])

    def test_next_tests_includes_forward_clob_capture_when_required(self):
        tests = next_tests({
            "review": {"counts": {"watch": 0}},
            "watchItems": [],
            "clob": {},
            "watchBlockers": {},
            "resolvedJoin": {},
            "fillability": {},
            "eventForwardCapture": {
                "forwardCaptureRequired": True,
                "standingRecorderCommand": "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900",
                "blockers": ["event-market-mapping-not-token-specific"],
            },
            "noEdge": {
                "entries": [
                    {
                        "id": "narrow-category-cross-venue-current-universe",
                        "verdict": "needs-more-data",
                        "currentFormRejected": True,
                    },
                    {"id": "crypto-settlement-horizon-parser-current-form", "verdict": "no-edge"},
                    {"id": "macro-rates-line-parser-current-form", "verdict": "no-edge"},
                ]
            },
        })

        ids = [item["id"] for item in tests]
        self.assertIn("prediction-forward-event-clob-capture", ids)
        capture = next(item for item in tests if item["id"] == "prediction-forward-event-clob-capture")
        self.assertEqual(capture["oneVariable"], "forward public CLOB capture window")
        self.assertIn("polymarket-clob-recorder", capture["commandHint"])
        self.assertFalse(capture["readyForPaper"])
        self.assertFalse(capture["readyForExecution"])
        self.assertFalse(capture["writesOrders"])
        self.assertFalse(capture["touchesBroker"])


if __name__ == "__main__":
    unittest.main()
