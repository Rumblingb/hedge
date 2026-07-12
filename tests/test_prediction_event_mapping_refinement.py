import unittest

from scripts.prediction_event_mapping_refinement import build_refinement


class PredictionEventMappingRefinementTests(unittest.TestCase):
    def test_flags_manual_review_fanout_and_spread_rejection_as_research_only(self):
        manual_review = {
            "decision": "research-only-manual-review-no-paper",
            "reviewedWindows": [
                {
                    "externalId": "2270330",
                    "headline": "Iran peace deal headline",
                    "eventIso": "2026-05-30T16:04:20+00:00",
                    "decision": "reject-paper",
                    "reasons": ["move-does-not-clear-half-spread"],
                },
                {
                    "externalId": "2354003",
                    "headline": "Iran peace deal headline",
                    "eventIso": "2026-05-30T16:04:20+00:00",
                    "decision": "keep-research",
                    "reasons": ["same-headline-maps-to-multiple-markets"],
                },
            ],
        }
        mapping_plan = {
            "candidates": [
                {
                    "externalId": "2270330",
                    "headline": "Iran peace deal headline",
                    "question": "US x Iran permanent peace deal by June 15, 2026?",
                },
                {
                    "externalId": "2354003",
                    "clobTokenId": "token-2354003",
                    "headline": "Iran peace deal headline",
                    "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                },
            ]
        }

        recorder = {
            "liveQualityDiagnostics": {
                "assets": [
                    {
                        "tokenId": "token-2354003",
                        "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                        "status": "fillable-live-book",
                        "liveBestBid": 0.63,
                        "liveBestAsk": 0.65,
                        "liveSpread": 0.02,
                        "liveBidSize": 200,
                        "liveAskSize": 1000,
                        "lastBookLocalTs": "2026-05-31T05:01:00Z",
                    }
                ]
            }
        }

        payload = build_refinement(manual_review, mapping_plan, recorder)

        self.assertEqual(payload["decision"], "research-only-mapping-refinement-required")
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForForwardCapture"])
        self.assertIn("spread-quality-rejected-current-watch-window", payload["blockers"])
        self.assertIn("ambiguous-headline-to-market-fanout", payload["blockers"])
        self.assertEqual(payload["mappingQualityCounts"]["reject-spread-and-ambiguous-fanout"], 1)
        self.assertEqual(payload["mappingRepairTargetCount"], 1)
        self.assertEqual(payload["mappingRepairTargets"][0]["candidateCount"], 2)
        self.assertEqual(payload["publicCaptureReviewLeadCount"], 1)
        self.assertEqual(payload["publicCaptureReviewLeads"][0]["tokenId"], "token-2354003")
        self.assertEqual(payload["publicCaptureReviewLeads"][0]["counterparty"], "iran/us")
        self.assertIn("not a mapping override", payload["publicCaptureReviewLeads"][0]["reviewUseOnly"])
        self.assertIn("geopolitical-agreement", payload["mappingRepairTargets"][0]["candidateFamilyCounts"])
        self.assertIn("deadline-choice-requires-forward-market-selection", payload["mappingRepairTargets"][0]["specificityFlagCounts"])
        self.assertIn("single event family selected", payload["mappingRepairTargets"][0]["blockedUntil"])
        self.assertEqual(payload["deadlineLadderCaptureCandidateCount"], 1)
        self.assertEqual(payload["deadlineLadderCaptureCandidates"][0]["tokenId"], "token-2354003")
        self.assertIn("not a mapping override", payload["deadlineLadderCaptureCandidates"][0]["reviewUseOnly"])
        self.assertEqual(payload["headlineReviews"][0]["nextSingleVariable"], "market specificity")
        self.assertEqual(payload["oneVariableRule"]["currentVariable"], "market specificity/source capture quality")
        self.assertIn("threshold tuning", payload["oneVariableRule"]["blockedVariables"])
        specificity = payload["headlineReviews"][0]["candidateSpecificityRows"]
        self.assertEqual(len(specificity), 2)
        self.assertIn("deadline-choice-requires-forward-market-selection", specificity[0]["specificityIssues"])
        self.assertNotIn("headline-has-multiple-event-families", specificity[0]["specificityIssues"])

    def test_mixed_macro_and_geopolitical_headline_preserves_both_families(self):
        manual_review = {
            "decision": "research-only-manual-review-no-paper",
            "reviewedWindows": [
                {
                    "externalId": "2270330",
                    "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                    "eventIso": "2026-05-30T16:04:20+00:00",
                    "decision": "reject-paper",
                    "reasons": ["same-headline-maps-to-multiple-markets"],
                },
            ],
        }
        mapping_plan = {
            "candidates": [
                {
                    "externalId": "2270330",
                    "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                    "question": "US x Iran permanent peace deal by June 15, 2026?",
                },
                {
                    "externalId": "fed-1",
                    "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                    "question": "Will the Fed hike interest rates in June?",
                },
            ]
        }

        payload = build_refinement(manual_review, mapping_plan)

        specificity = payload["headlineReviews"][0]["candidateSpecificityRows"]
        geo = next(item for item in specificity if item["externalId"] == "2270330")
        rates = next(item for item in specificity if item["externalId"] == "fed-1")
        self.assertEqual(
            sorted(geo["headlineEventFamilies"]),
            ["geopolitical-agreement", "macro-rates"],
        )
        self.assertTrue(geo["familyMatch"])
        self.assertTrue(rates["familyMatch"])
        self.assertIn("headline-has-multiple-event-families", geo["specificityIssues"])
        self.assertIn("headline-does-not-identify-counterparty", geo["specificityIssues"])
        self.assertNotIn("headline-family-differs-from-question-family", geo["specificityIssues"])
        self.assertEqual(payload["mappingRepairTargetCount"], 1)
        self.assertEqual(
            sorted(payload["mappingRepairTargets"][0]["headlineEventFamilies"]),
            ["geopolitical-agreement", "macro-rates"],
        )

    def test_deadline_ladder_capture_candidates_exclude_adjacent_wrong_themes(self):
        manual_review = {
            "decision": "research-only-manual-review-no-paper",
            "reviewedWindows": [
                {
                    "externalId": "agreement-1",
                    "headline": "Donald Trump asks for amendments to agreed upon draft of US-Iran ceasefire deal",
                    "eventIso": "2026-05-31T05:52:34+00:00",
                    "decision": "keep-research",
                    "reasons": ["same-headline-maps-to-multiple-markets"],
                },
            ],
        }
        mapping_plan = {
            "candidates": [
                {
                    "externalId": "agreement-1",
                    "clobTokenId": "agreement-token",
                    "headline": "Donald Trump asks for amendments to agreed upon draft of US-Iran ceasefire deal",
                    "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                    "marketActors": ["iran", "trump", "us"],
                    "marketEventFamilies": ["geopolitical-agreement"],
                    "mappingStatus": "candidate-review-required",
                    "topBookDepth": 1000,
                },
                {
                    "externalId": "peace-1",
                    "clobTokenId": "peace-token",
                    "headline": "Donald Trump asks for amendments to agreed upon draft of US-Iran ceasefire deal",
                    "question": "US x Iran permanent peace deal by June 30, 2026?",
                    "marketActors": ["iran", "us"],
                    "marketEventFamilies": ["geopolitical-agreement"],
                    "mappingStatus": "candidate-review-required",
                    "topBookDepth": 2000,
                },
                {
                    "externalId": "uranium-1",
                    "clobTokenId": "uranium-token",
                    "headline": "Donald Trump asks for amendments to agreed upon draft of US-Iran ceasefire deal",
                    "question": "Will Trump agree to Iranian enrichment of uranium by May 31?",
                    "marketActors": ["iran", "trump", "us"],
                    "marketEventFamilies": ["geopolitical-agreement"],
                    "mappingStatus": "candidate-review-required",
                    "topBookDepth": 3000,
                },
            ],
        }

        payload = build_refinement(manual_review, mapping_plan)

        self.assertEqual(payload["decision"], "research-only-mapping-refinement-required")
        self.assertEqual(payload["deadlineLadderCaptureCandidateCount"], 1)
        self.assertEqual(payload["deadlineLadderCaptureCandidates"][0]["tokenId"], "agreement-token")
        self.assertEqual(
            payload["mappingRepairTargets"][0]["deadlineLadderCaptureCandidates"][0]["question"],
            "US announces new Iran agreement/ceasefire extension by June 30?",
        )
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_single_clean_mapping_can_advance_to_forward_capture_only(self):
        manual_review = {
            "decision": "research-only-manual-review-watch",
            "reviewedWindows": [
                {
                    "externalId": "market-1",
                    "headline": "Fed cuts rates headline",
                    "eventIso": "2026-05-30T16:04:20+00:00",
                    "decision": "keep-watch",
                    "reasons": [],
                }
            ],
        }
        mapping_plan = {"candidates": [{"externalId": "market-1", "headline": "Fed cuts rates headline"}]}

        payload = build_refinement(manual_review, mapping_plan)

        self.assertEqual(payload["decision"], "research-only-mapping-refinement-ready-for-forward-capture")
        self.assertTrue(payload["readyForForwardCapture"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["blockers"], [])
        self.assertEqual(payload["mappingRepairTargetCount"], 0)
        self.assertEqual(payload["headlineReviews"][0]["nextSingleVariable"], "forward public CLOB capture")
        self.assertEqual(payload["oneVariableRule"]["currentVariable"], "forward public CLOB capture")

    def test_clean_manual_keep_watch_selection_resolves_fanout_for_forward_capture_only(self):
        manual_review = {
            "decision": "research-only-manual-review-watch",
            "reviewedWindows": [
                {
                    "externalId": "2354003",
                    "clobTokenId": "token-2354003",
                    "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                    "eventIso": "2026-05-30T16:04:20+00:00",
                    "decision": "keep-watch",
                    "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                    "reasons": [],
                }
            ],
        }
        mapping_plan = {
            "candidates": [
                {
                    "externalId": "2354003",
                    "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                    "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                },
                {
                    "externalId": "1962237",
                    "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                    "question": "US x Iran permanent peace deal by June 30, 2026?",
                },
            ],
        }

        payload = build_refinement(manual_review, mapping_plan)

        self.assertEqual(payload["decision"], "research-only-mapping-refinement-ready-for-forward-capture")
        self.assertTrue(payload["readyForForwardCapture"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertNotIn("ambiguous-headline-to-market-fanout", payload["blockers"])
        self.assertEqual(payload["mappingRepairTargetCount"], 0)
        review = payload["headlineReviews"][0]
        self.assertEqual(review["mappingQuality"], "manual-selected-forward-capture-watch")
        self.assertTrue(review["fanoutResolvedByManualReview"])
        self.assertEqual(review["manualSelectedExternalId"], "2354003")
        self.assertEqual(review["manualSelectedTokenId"], "token-2354003")
        self.assertEqual(review["nextSingleVariable"], "forward public CLOB capture")

    def test_missing_mapping_plan_blocks_refinement(self):
        payload = build_refinement(
            {
                "reviewedWindows": [
                    {
                        "externalId": "market-1",
                        "headline": "Fed cuts rates headline",
                        "decision": "keep-watch",
                        "reasons": [],
                    }
                ]
            },
            {},
        )

        self.assertIn("mapping-plan-has-no-current-candidates", payload["blockers"])
        self.assertIn("manual-review-window-missing-from-current-mapping-plan", payload["blockers"])
        self.assertFalse(payload["readyForForwardCapture"])


if __name__ == "__main__":
    unittest.main()
