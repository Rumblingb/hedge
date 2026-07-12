import json
import tempfile
import unittest
from pathlib import Path

from scripts.prediction_event_capture_cycle import (
    HERMES,
    build_cycle,
    command_text,
    default_markdown_path,
    recorder_cmd,
    render_markdown,
)


class PredictionEventCaptureCycleTest(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^prediction-event-capture-cycle-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "mode": "dry-run",
            "targetCount": 0,
            "eventNews": {},
            "eventMarketMapping": {},
            "eventTimestampDataset": {},
            "eventLagReplayDecision": "research-only",
            "eventLagReplayBlockers": [],
            "eventLagResearchWatchReady": False,
            "eventLagSensitivity": {},
            "eventLagWatchReview": {},
            "completeEventCount": 0,
            "completeWindowCount": 0,
            "repricedWindowCount": 0,
            "eventLagReplayMissingReasonCounts": {},
            "executedRecorder": {},
            "latestRecorder": {},
            "readyForPaper": False,
            "readyForExecution": False,
            "steps": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Event Capture Cycle - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_dry_run_cycle_is_research_only_and_skips_recorder(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-capture-targets-ready",
                "durationSec": 900,
                "coverageStatusCounts": {"missing-pre-event-window": 2},
                "targets": [
                    {"tokenId": "111"},
                    {"tokenId": "222"},
                ],
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={
                "decision": "research-only-event-lag-replay-blocked",
                "completeEventCount": 0,
                "completeWindowCount": 0,
                "repricedWindowCount": 0,
                "blockers": ["too-few-complete-event-windows"],
                "missingReasonCounts": {"no-pre-event-quote-within-window": 4},
            },
            recorder_latest={"status": "ok", "messages": 760, "selectedAssets": 15, "writesOrders": False},
            clob_microstructure={"decision": "research-only", "readyFeatureCount": 3, "capture": {"recordsRead": 8607}},
        )

        self.assertEqual(payload["decision"], "research-only-capture-cycle-dry-run-ready")
        self.assertEqual(payload["mode"], "dry-run")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["eventLagReplayWatchReady"])
        self.assertFalse(payload["eventLagResearchWatchReady"])
        self.assertFalse(payload["captureCycleEvidencePassed"])
        self.assertFalse(payload["paperPromotionEvidencePassed"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["targetCount"], 2)
        self.assertEqual(payload["targetDecision"], "research-only-capture-targets-ready")
        self.assertEqual(payload["captureMode"], "token-targets")
        self.assertEqual(payload["eventLagReplay"], "research-only-event-lag-replay-blocked")
        self.assertEqual(payload["eventLagReplayBlockers"], ["too-few-complete-event-windows"])
        self.assertEqual(payload["replayMissing"]["no-pre-event-quote-within-window"], 4)
        self.assertEqual(payload["eventLagReplayMissingReasonCounts"]["no-pre-event-quote-within-window"], 4)
        self.assertEqual(payload["completeEvents"], 0)
        self.assertEqual(payload["completeWindows"], 0)
        self.assertEqual(payload["repricedWindows"], 0)
        self.assertEqual(payload["completeWindowCount"], 0)
        self.assertFalse(payload["eventTimestampDataset"]["present"])
        by_id = {step["id"]: step for step in payload["steps"]}
        self.assertEqual(by_id["refresh-timestamps-before-capture"]["status"], "planned")
        self.assertEqual(by_id["refresh-timestamps-after-capture"]["status"], "planned")
        self.assertEqual(by_id["sensitivity-event-lag"]["status"], "planned")
        self.assertEqual(by_id["review-event-lag-watch"]["status"], "planned")
        self.assertEqual(by_id["record-public-clob"]["status"], "skipped-dry-run")
        self.assertIn("--token-id 111 --token-id 222", by_id["record-public-clob"]["command"])
        self.assertIn("event-lag-replay-not-watch-ready", payload["blockers"])
        self.assertNotIn("dry-run-only; pass --run-recorder to collect public CLOB data", payload["blockers"])
        self.assertTrue(payload["latestRecorder"]["evidencePresent"])
        self.assertTrue(payload["eventNews"]["present"])
        self.assertEqual(payload["eventMarketMapping"]["candidateCount"], 4)
        self.assertFalse(payload["eventLagSensitivity"]["present"])
        self.assertFalse(payload["eventLagWatchReview"]["present"])
        self.assertEqual(payload["safeEnv"]["BILL_ENABLE_FUTURES_DEMO_EXECUTION"], "false")
        self.assertEqual(payload["safeEnv"]["RH_TOPSTEP_READ_ONLY"], "true")
        self.assertEqual(payload["safeEnv"]["RH_LIVE_EXECUTION_ENABLED"], "false")

    def test_cycle_surfaces_event_timestamp_dataset_summary(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-forward-capture-required",
                "targets": [],
                "standingTerms": "fed",
                "tokenSpecificCandidateCount": 5,
                "excludedMappingCandidateCount": 15,
                "excludedMappingReasonCounts": {"ambiguous-mapping-status": 15},
                "mappingBlockers": ["ambiguous-headline-event-family-fanout"],
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_timestamp_dataset={
                "decision": "research-only-event-timestamp-dataset-ready",
                "candidateCount": 20,
                "coverageStatusCounts": {"window-range-present": 5},
                "completeWindowTargetCount": 5,
                "unrecoverablePreEventTargetCount": 15,
                "forwardCaptureRequired": True,
                "readyForPaper": False,
            },
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0},
            event_lag_replay={"decision": "research-only-event-lag-replay-blocked"},
            recorder_latest={},
            clob_microstructure={},
        )

        self.assertTrue(payload["eventTimestampDataset"]["present"])
        self.assertEqual(payload["eventTimestampDataset"]["candidateCount"], 20)
        self.assertEqual(payload["eventTimestampDataset"]["coverageStatusCounts"], {"window-range-present": 5})
        self.assertEqual(payload["eventTimestampDataset"]["unrecoverablePreEventTargetCount"], 15)
        self.assertFalse(payload["eventTimestampDataset"]["readyForPaper"])
        self.assertEqual(payload["tokenSpecificCandidateCount"], 5)
        self.assertEqual(payload["tokenSpecificCandidates"], 5)
        self.assertEqual(payload["excludedMappingCandidateCount"], 15)
        self.assertEqual(payload["excludedMappingCandidates"], 15)
        self.assertEqual(payload["excludedMappingReasonCounts"], {"ambiguous-mapping-status": 15})
        self.assertEqual(payload["excludedReasons"], {"ambiguous-mapping-status": 15})
        self.assertEqual(payload["mappingBlockers"], ["ambiguous-headline-event-family-fanout"])
        self.assertTrue(payload["forwardRequired"])

    def test_cycle_surfaces_event_lag_sensitivity_without_promoting_paper(self):
        payload = build_cycle(
            capture_targets={"decision": "research-only-forward-capture-required", "targets": [], "standingTerms": "fed"},
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0},
            event_lag_replay={
                "decision": "research-only-event-lag-replay-blocked",
                "blockers": ["no-post-event-repricing-after-half-spread"],
            },
            event_lag_sensitivity={
                "decision": "research-only-event-lag-sensitivity-watch",
                "bestCompleteWindowCount": 5,
                "bestRepricedWindowCount": 2,
                "watchScenarioCount": 2,
                "watchReady": True,
                "blockers": ["watch-only-scenario-found-manual-review-required"],
                "readyForPaper": False,
                "readyForExecution": False,
            },
            event_lag_watch_review={
                "decision": "research-only-event-lag-watch-review-visible",
                "watchScenarioCount": 2,
                "repricedWatchWindowCount": 2,
                "watchReady": True,
                "blockers": ["manual-review-required-before-forward-capture-or-paper-discussion"],
                "readyForPaper": False,
                "readyForExecution": False,
            },
            recorder_latest={},
            clob_microstructure={},
        )

        self.assertTrue(payload["eventLagSensitivity"]["present"])
        self.assertTrue(payload["eventLagSensitivity"]["watchReady"])
        self.assertEqual(payload["eventLagSensitivity"]["bestRepricedWindowCount"], 2)
        self.assertEqual(payload["eventLagSensitivity"]["watchScenarioCount"], 2)
        self.assertTrue(payload["eventLagWatchReview"]["present"])
        self.assertTrue(payload["eventLagWatchReview"]["visible"])
        self.assertTrue(payload["eventLagWatchReview"]["watchReady"])
        self.assertTrue(payload["eventLagResearchWatchReady"])
        self.assertEqual(payload["eventLagWatchReview"]["repricedWatchWindowCount"], 2)
        self.assertIn("event-lag-replay-not-watch-ready", payload["blockers"])
        self.assertFalse(payload["paperPromotionEvidencePassed"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_dry_run_without_latest_recorder_evidence_keeps_recorder_blocker(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-capture-targets-ready",
                "targets": [{"tokenId": "111"}],
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={"decision": "research-only-event-lag-replay-blocked"},
            recorder_latest={"status": "ok", "messages": 0, "writesOrders": False},
            clob_microstructure={},
        )

        self.assertFalse(payload["latestRecorder"]["evidencePresent"])
        self.assertIn("dry-run-only; pass --run-recorder to collect public CLOB data", payload["blockers"])

    def test_forward_capture_required_decision_is_valid_research_input(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-forward-capture-required",
                "targets": [],
                "standingTerms": "fed,cpi",
                "staleContextTargetCount": 2,
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={"decision": "research-only-event-lag-replay-blocked"},
            recorder_latest={},
            clob_microstructure={},
            run_recorder=True,
            ran_steps=[{"id": "record-public-clob", "status": "pass", "command": "npm run ... --terms fed,cpi"}],
        )

        self.assertNotIn("capture-targets-not-ready", payload["blockers"])
        self.assertEqual(payload["captureMode"], "standing-terms")
        self.assertIn("event-lag-replay-not-watch-ready", payload["blockers"])
        self.assertFalse(payload["readyForExecution"])

    def test_review_lead_forward_capture_decision_uses_selected_token_without_mapping_blocker(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-forward-capture-review-leads-ready",
                "targets": [],
                "mappingRefinementReadyForForwardCapture": True,
                "publicCaptureReviewLeads": [
                    {
                        "tokenId": "selected-review-token",
                        "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                    }
                ],
                "tokenSpecificCandidateCount": 6,
                "excludedMappingCandidateCount": 14,
                "excludedMappingReasonCounts": {"ambiguous-mapping-status": 14},
                "mappingBlockers": [
                    "ambiguous-headline-event-family-fanout",
                    "ambiguous-headline-counterparty-fanout",
                ],
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-blocked", "candidateCount": 20},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={"decision": "research-only-event-lag-replay-watch"},
            recorder_latest={"status": "ok", "messages": 1, "writesOrders": False},
            clob_microstructure={},
        )

        self.assertEqual(payload["captureMode"], "review-lead-token")
        self.assertEqual(payload["targetCount"], 0)
        self.assertEqual(payload["reviewLeadTargetCount"], 1)
        self.assertEqual(payload["tokens"], ["selected-review-token"])
        self.assertNotIn("capture-targets-not-ready", payload["blockers"])
        self.assertNotIn("event-market-mapping-not-ready", payload["blockers"])
        by_id = {step["id"]: step for step in payload["steps"]}
        self.assertIn("--token-id selected-review-token", by_id["record-public-clob"]["command"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_planned_run_recorder_review_lead_command_uses_selected_token(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-forward-capture-review-leads-ready",
                "targets": [],
                "mappingRefinementReadyForForwardCapture": True,
                "publicCaptureReviewLeads": [{"tokenId": "selected-review-token"}],
                "standingTerms": "fed,cpi",
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-blocked", "candidateCount": 20},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={"decision": "research-only-event-lag-replay-watch"},
            recorder_latest={},
            clob_microstructure={},
            run_recorder=True,
        )

        by_id = {step["id"]: step for step in payload["steps"]}
        self.assertEqual(payload["captureMode"], "review-lead-token")
        self.assertIn("--token-id selected-review-token", by_id["record-public-clob"]["command"])
        self.assertNotIn("--terms fed,cpi", by_id["record-public-clob"]["command"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_run_recorder_mode_still_never_marks_paper_or_execution_ready(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-capture-targets-ready",
                "targets": [{"tokenId": "abc"}],
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={
                "decision": "research-only-event-lag-replay-watch",
                "completeEventCount": 5,
                "repricedWindowCount": 4,
            },
            recorder_latest={},
            clob_microstructure={},
            duration_sec=30,
            run_recorder=True,
            ran_steps=[{"id": "record-public-clob", "status": "pass", "command": "npm run ..."}],
        )

        self.assertEqual(payload["decision"], "research-only-capture-cycle-ran")
        self.assertEqual(payload["mode"], "run-recorder")
        self.assertEqual(payload["executedCaptureMode"], "no-targets")
        self.assertTrue(payload["eventLagReplayWatchReady"])
        self.assertTrue(payload["captureCycleEvidencePassed"])
        self.assertFalse(payload["paperPromotionEvidencePassed"])
        self.assertIn("paper-review-requires-positive-fillability-and-spread-adjusted-replay", payload["paperPromotionBlockers"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForLive"])
        self.assertEqual(payload["blockers"], [])
        self.assertEqual(payload["steps"][0]["status"], "pass")

    def test_run_recorder_preserves_executed_token_command_after_refresh(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-forward-capture-required",
                "targets": [],
                "standingTerms": "fed,cpi",
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={"decision": "research-only-event-lag-replay-blocked"},
            recorder_latest={},
            clob_microstructure={},
            duration_sec=30,
            run_recorder=True,
            ran_steps=[
                {
                    "id": "record-public-clob",
                    "status": "pass",
                    "argv": [
                        "npm",
                        "run",
                        "--silent",
                        "bill:polymarket-clob-recorder",
                        "--",
                        "--duration-sec",
                        "30",
                        "--max-assets",
                        "1",
                        "--token-id",
                        "selected-review-token",
                    ],
                    "command": "npm run --silent bill:polymarket-clob-recorder -- --token-id selected-review-token",
                    "publicMarketDataOnly": True,
                    "writesOrders": False,
                    "touchesBroker": False,
                }
            ],
        )

        self.assertEqual(payload["captureMode"], "standing-terms")
        self.assertEqual(payload["executedCaptureMode"], "token-targets")
        self.assertEqual(payload["executedRecorder"]["tokenIds"], ["selected-review-token"])
        self.assertEqual(payload["executedRecorder"]["maxAssets"], 1)
        self.assertTrue(payload["executedRecorder"]["publicMarketDataOnly"])
        self.assertFalse(payload["executedRecorder"]["writesOrders"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_no_recordable_tokens_uses_standing_terms_without_paper_promotion(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-forward-capture-required",
                "targets": [],
                "standingTerms": "fed,cpi,iran",
                "standingMaxAssets": 12,
                "staleContextTargetCount": 4,
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={"decision": "research-only-event-lag-replay-blocked"},
            recorder_latest={},
            clob_microstructure={},
            duration_sec=30,
            run_recorder=True,
            ran_steps=[{"id": "record-public-clob", "status": "pass", "command": "npm run ... --terms fed,cpi,iran"}],
        )

        self.assertEqual(payload["captureMode"], "standing-terms")
        self.assertEqual(payload["standingTerms"], "fed,cpi,iran")
        self.assertEqual(payload["standingMaxAssets"], 12)
        self.assertEqual(payload["staleContextTargetCount"], 4)
        self.assertNotIn("no-event-clob-capture-targets", payload["blockers"])
        self.assertIn("event-lag-replay-not-watch-ready", payload["blockers"])
        self.assertFalse(payload["readyForPaper"])

    def test_run_recorder_mode_reports_still_blocked_when_replay_not_watch_ready(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-capture-targets-ready",
                "targets": [{"tokenId": "abc"}],
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={"decision": "research-only-event-lag-replay-blocked"},
            recorder_latest={},
            clob_microstructure={},
            duration_sec=30,
            run_recorder=True,
        )

        self.assertEqual(payload["decision"], "research-only-capture-cycle-ran-still-blocked")
        self.assertIn("event-lag-replay-not-watch-ready", payload["blockers"])
        self.assertFalse(payload["eventLagReplayWatchReady"])
        self.assertFalse(payload["captureCycleEvidencePassed"])
        self.assertFalse(payload["paperPromotionEvidencePassed"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_run_recorder_marks_failed_followup_step_as_blocker(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-capture-targets-ready",
                "targets": [{"tokenId": "abc"}],
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={"decision": "research-only-event-lag-replay-watch"},
            recorder_latest={},
            clob_microstructure={},
            run_recorder=True,
            ran_steps=[{"id": "refresh-news-after-capture", "status": "fail", "command": "npm run ..."}],
        )

        self.assertEqual(payload["decision"], "research-only-capture-cycle-ran-still-blocked")
        self.assertIn("cycle-step-failed", payload["blockers"])
        self.assertEqual(payload["failedStepIds"], ["refresh-news-after-capture"])
        self.assertFalse(payload["captureCycleEvidencePassed"])
        self.assertFalse(payload["readyForExecution"])

    def test_recorder_selected_assets_reports_count_for_list_payloads(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-capture-targets-ready",
                "targets": [{"tokenId": "abc"}],
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={"decision": "research-only-event-lag-replay-watch"},
            recorder_latest={
                "status": "ok",
                "messages": 12,
                "selectedAssets": [{"tokenId": "abc"}, {"tokenId": "def"}],
                "writesOrders": False,
            },
            clob_microstructure={},
            run_recorder=True,
            ran_steps=[{"id": "record-public-clob", "status": "pass", "command": "npm run ..."}],
        )

        self.assertEqual(payload["latestRecorder"]["selectedAssetCount"], 2)
        self.assertEqual(len(payload["latestRecorder"]["selectedAssets"]), 2)
        self.assertFalse(payload["latestRecorder"]["writesOrders"])

    def test_live_quality_blocks_capture_evidence_when_books_are_not_fillable(self):
        payload = build_cycle(
            capture_targets={
                "decision": "research-only-capture-targets-ready",
                "targets": [{"tokenId": "abc"}],
            },
            event_news={"decision": "research-only-event-news-rss-ready", "itemCount": 12},
            event_market_mapping={"decision": "research-only-event-market-mapping-candidates-ready", "candidateCount": 4},
            event_lag_requirements={"decision": "research-only-event-lag-requirements-cleared", "blockedCount": 0, "passCount": 4},
            event_lag_replay={
                "decision": "research-only-event-lag-replay-watch",
                "completeEventCount": 5,
                "repricedWindowCount": 4,
            },
            recorder_latest={
                "status": "ok",
                "messages": 42,
                "selectedAssets": [{"tokenId": "abc"}],
                "selectionDiagnostics": {"rejectionCounts": {"below-min-price": 2}},
                "liveQualityDiagnostics": {
                    "selectedAssetCount": 1,
                    "observedLiveBookCount": 1,
                    "fillableLiveBookCount": 0,
                    "statusCounts": {"live-spread-too-wide": 1},
                    "readyForPaperEvidence": False,
                },
                "writesOrders": False,
            },
            clob_microstructure={},
            run_recorder=True,
            ran_steps=[{"id": "record-public-clob", "status": "pass", "command": "npm run ..."}],
        )

        self.assertEqual(payload["decision"], "research-only-capture-cycle-ran-still-blocked")
        self.assertIn("recorder-live-quality-not-fillable", payload["blockers"])
        self.assertIn("paper-review-requires-fillable-live-books", payload["paperPromotionBlockers"])
        self.assertFalse(payload["captureCycleEvidencePassed"])
        self.assertFalse(payload["paperPromotionEvidencePassed"])
        self.assertEqual(payload["latestRecorder"]["liveQualityDiagnostics"]["fillableLiveBookCount"], 0)
        self.assertEqual(payload["latestRecorder"]["selectionDiagnostics"]["rejectionCounts"]["below-min-price"], 2)

    def test_recorder_command_is_argv_not_shell_dependent(self):
        argv = recorder_cmd(["tok one", "tok-two"], duration_sec=120)
        self.assertEqual(argv[:7], [
            "npm",
            "run",
            "--silent",
            "bill:polymarket-clob-recorder",
            "--",
            "--duration-sec",
            "120",
        ])
        self.assertIn("tok one", argv)
        self.assertIn("--max-output-mb", argv)
        self.assertIn("128", argv)
        self.assertIn("--min-free-gb", argv)
        self.assertIn("20", argv)
        self.assertIn("--token-id 'tok one'", command_text(argv))

    def test_recorder_command_supports_standing_terms(self):
        argv = recorder_cmd([], duration_sec=120, terms="fed,cpi", max_assets=7)
        self.assertEqual(argv, [
            "npm",
            "run",
            "--silent",
            "bill:polymarket-clob-recorder",
            "--",
            "--duration-sec",
            "120",
            "--max-assets",
            "7",
            "--max-output-mb",
            "128",
            "--min-free-gb",
            "20",
            "--terms",
            "fed,cpi",
        ])

    def test_recorder_command_accepts_stricter_storage_overrides(self):
        argv = recorder_cmd(
            [],
            duration_sec=120,
            terms="fed,cpi",
            max_assets=7,
            max_output_mb=64,
            min_free_gb=30,
        )

        self.assertIn("--max-output-mb", argv)
        self.assertIn("64", argv)
        self.assertIn("--min-free-gb", argv)
        self.assertIn("30", argv)


if __name__ == "__main__":
    unittest.main()
