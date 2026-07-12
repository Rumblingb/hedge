import unittest

from scripts.prediction_event_lag_manual_review import build_manual_review


class PredictionEventLagManualReviewTests(unittest.TestCase):
    def test_rejects_half_spread_only_move_and_keeps_ambiguous_fanout_as_research(self):
        payload = build_manual_review({
            "decision": "research-only-event-lag-watch-review-visible",
            "watchWindows": [
                {
                    "externalId": "2270330",
                    "clobTokenId": "token-a",
                    "question": "US x Iran permanent peace deal by June 15, 2026?",
                    "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                    "eventIso": "2026-05-30T16:04:20+00:00",
                    "scenarioLabel": "min-move-0.0025",
                    "horizonMinutes": 15,
                    "midMove": 0.005,
                    "absMoveAfterHalfSpread": 0.0,
                    "preSpread": 0.01,
                    "preAgeSec": 1040.248,
                    "postDelaySec": 900.221,
                },
                {
                    "externalId": "2354003",
                    "clobTokenId": "token-b",
                    "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                    "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                    "eventIso": "2026-05-30T16:04:20+00:00",
                    "scenarioLabel": "min-move-0.0025",
                    "horizonMinutes": 15,
                    "midMove": -0.01,
                    "absMoveAfterHalfSpread": 0.005,
                    "preSpread": 0.01,
                    "preAgeSec": 652.375,
                    "postDelaySec": 901.12,
                },
            ],
        })

        self.assertEqual(payload["decision"], "research-only-manual-review-no-paper")
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertEqual(payload["decisionCounts"], {"reject-paper": 1, "keep-research": 1})
        self.assertEqual(payload["reviewedWindows"][0]["decision"], "reject-paper")
        self.assertIn("move-does-not-clear-half-spread", payload["reviewedWindows"][0]["reasons"])
        self.assertEqual(payload["reviewedWindows"][1]["decision"], "keep-research")
        self.assertIn("same-headline-maps-to-multiple-markets", payload["reviewedWindows"][1]["reasons"])
        self.assertIn("no-window-clears-manual-review-for-paper-discussion", payload["blockers"])
        self.assertIn("forward-public-clob-capture-still-required", payload["blockers"])

    def test_keeps_clean_spread_clearing_window_as_watch_only(self):
        payload = build_manual_review({
            "decision": "research-only-event-lag-watch-review-visible",
            "watchWindows": [
                {
                    "externalId": "market-1",
                    "clobTokenId": "token-a",
                    "question": "Will X happen?",
                    "headline": "X event happened",
                    "eventIso": "2026-05-30T16:04:20+00:00",
                    "horizonMinutes": 15,
                    "midMove": 0.03,
                    "absMoveAfterHalfSpread": 0.025,
                    "preSpread": 0.01,
                    "preAgeSec": 60,
                    "postDelaySec": 600,
                }
            ],
        })

        self.assertEqual(payload["decision"], "research-only-manual-review-watch")
        self.assertEqual(payload["decisionCounts"], {"keep-watch": 1})
        self.assertFalse(payload["readyForPaper"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["forwardCaptureObserved"])
        self.assertFalse(payload["forwardCaptureEvidencePresent"])
        self.assertIn("forward-public-clob-capture-still-required", payload["blockers"])

    def test_forward_capture_evidence_replaces_capture_missing_blocker_without_paper_promotion(self):
        payload = build_manual_review(
            {
                "decision": "research-only-event-lag-watch-review-visible",
                "watchWindows": [
                    {
                        "externalId": "market-1",
                        "clobTokenId": "selected-review-token",
                        "question": "Will X happen?",
                        "headline": "X event happened",
                        "eventIso": "2026-05-30T16:04:20+00:00",
                        "horizonMinutes": 15,
                        "midMove": 0.03,
                        "absMoveAfterHalfSpread": 0.025,
                        "preSpread": 0.01,
                        "preAgeSec": 60,
                        "postDelaySec": 600,
                    }
                ],
            },
            capture_cycle={
                "decision": "research-only-capture-cycle-ran",
                "captureCycleEvidencePassed": True,
                "executedRecorder": {
                    "publicMarketDataOnly": True,
                    "tokenIds": ["selected-review-token"],
                    "writesOrders": False,
                    "touchesBroker": False,
                },
            },
        )

        self.assertEqual(payload["decision"], "research-only-manual-review-watch")
        self.assertTrue(payload["forwardCaptureEvidencePresent"])
        self.assertIn("paper-promotion-evidence-still-required-after-forward-capture", payload["blockers"])
        self.assertNotIn("forward-public-clob-capture-still-required", payload["blockers"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_observed_forward_capture_without_fillability_gets_precise_blocker(self):
        payload = build_manual_review(
            {
                "decision": "research-only-event-lag-watch-review-visible",
                "watchWindows": [
                    {
                        "externalId": "market-1",
                        "clobTokenId": "selected-review-token",
                        "question": "Will X happen?",
                        "headline": "X event happened",
                        "eventIso": "2026-05-30T16:04:20+00:00",
                        "horizonMinutes": 15,
                        "midMove": 0.03,
                        "absMoveAfterHalfSpread": 0.025,
                        "preSpread": 0.01,
                        "preAgeSec": 60,
                        "postDelaySec": 600,
                    }
                ],
            },
            capture_cycle={
                "decision": "research-only-capture-cycle-ran-still-blocked",
                "captureCycleEvidencePassed": False,
                "blockers": ["recorder-live-quality-not-fillable"],
                "executedRecorder": {
                    "publicMarketDataOnly": True,
                    "tokenIds": ["selected-review-token"],
                    "writesOrders": False,
                    "touchesBroker": False,
                },
            },
        )

        self.assertEqual(payload["decision"], "research-only-manual-review-watch")
        self.assertTrue(payload["forwardCaptureObserved"])
        self.assertFalse(payload["forwardCaptureEvidencePresent"])
        self.assertIn("forward-public-clob-capture-observed-but-not-paper-grade", payload["blockers"])
        self.assertNotIn("forward-public-clob-capture-still-required", payload["blockers"])
        self.assertEqual(payload["captureCycleBlockers"], ["recorder-live-quality-not-fillable"])
        self.assertIn("failed the paper-grade evidence gate", payload["nextAction"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_latest_recorder_evidence_counts_as_observed_without_paper_promotion(self):
        payload = build_manual_review(
            {
                "decision": "research-only-event-lag-watch-review-visible",
                "watchWindows": [
                    {
                        "externalId": "market-1",
                        "clobTokenId": "latest-recorder-token",
                        "question": "Will X happen?",
                        "headline": "X event happened",
                        "eventIso": "2026-05-30T16:04:20+00:00",
                        "horizonMinutes": 15,
                        "midMove": 0.03,
                        "absMoveAfterHalfSpread": 0.025,
                        "preSpread": 0.01,
                        "preAgeSec": 60,
                        "postDelaySec": 600,
                    }
                ],
            },
            capture_cycle={
                "decision": "research-only-capture-cycle-dry-run-ready",
                "captureCycleEvidencePassed": False,
                "blockers": ["event-lag-replay-not-watch-ready"],
                "writesOrders": False,
                "touchesBroker": False,
                "latestRecorder": {
                    "evidencePresent": True,
                    "status": "ok",
                    "writesOrders": False,
                    "selectedAssets": [{"tokenId": "latest-recorder-token"}],
                    "liveQualityDiagnostics": {
                        "assets": [{"tokenId": "latest-recorder-token", "status": "fillable-live-book"}]
                    },
                },
            },
        )

        self.assertEqual(payload["decision"], "research-only-manual-review-watch")
        self.assertTrue(payload["forwardCaptureObserved"])
        self.assertFalse(payload["forwardCaptureEvidencePresent"])
        self.assertIn("forward-public-clob-capture-observed-but-not-paper-grade", payload["blockers"])
        self.assertNotIn("forward-public-clob-capture-still-required", payload["blockers"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_blocks_when_no_windows_exist(self):
        payload = build_manual_review({"decision": "research-only-event-lag-watch-review-blocked"})

        self.assertEqual(payload["decision"], "research-only-manual-review-no-paper")
        self.assertEqual(payload["reviewedWindowCount"], 0)
        self.assertIn("no-watch-windows-to-review", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
