import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_event_clob_capture_targets import VAULT, build_targets, default_markdown_path, render_markdown


class PredictionEventClobCaptureTargetsTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-event-clob-capture-targets-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "replayDecision": "research-only",
            "targetCount": 0,
            "allCandidateTargetCount": 0,
            "tokenSpecificCandidateCount": 0,
            "excludedMappingCandidateCount": 0,
            "excludedMappingReasonCounts": {},
            "publicCaptureReviewLeadCount": 0,
            "staleContextTargetCount": 0,
            "existingAssetsWithQuotes": 0,
            "coverageStatusCounts": {},
            "unrecoverablePreEventTargetCount": 0,
            "readyForPaper": False,
            "readyForExecution": False,
            "recorderCommand": "",
            "forwardCapturePlan": {},
            "standingRecorderCommand": "",
            "reviewLeadRecorderCommand": "",
            "targets": [],
            "limitations": [],
        })

        self.assertIn("# Prediction Event CLOB Capture Targets - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_builds_research_only_recorder_command_for_missing_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            clob = Path(tmp) / "clob.jsonl"
            event_time = datetime(2026, 5, 30, 12, tzinfo=timezone.utc)
            clob.write_text(json.dumps({
                "eventType": "best_bid_ask",
                "assetId": "token-with-post-only",
                "localTs": (event_time + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
                "bestBid": "0.40",
                "bestAsk": "0.42",
            }) + "\n")
            mapping = {
                "decision": "research-only-event-market-mapping-candidates-ready",
                "candidates": [
                    {
                        "externalId": "missing-market",
                        "clobTokenId": "missing-token",
                        "question": "US x Iran permanent peace deal?",
                        "headline": "Iran deal headline",
                        "articleDatetime": int(event_time.timestamp()),
                        "topBookDepth": 100,
                        "score": 10,
                    },
                    {
                        "externalId": "post-only-market",
                        "clobTokenId": "token-with-post-only",
                        "question": "US announces Iran agreement?",
                        "headline": "Iran ceasefire headline",
                        "articleDatetime": int(event_time.timestamp()),
                        "topBookDepth": 50,
                        "score": 8,
                    },
                ],
            }
            payload = build_targets(
                mapping_plan=mapping,
                replay={"decision": "research-only-event-lag-replay-blocked"},
                clob_paths=[clob],
                max_assets=2,
                duration_sec=300,
            )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["targetCount"], 0)
        self.assertEqual(payload["staleContextTargetCount"], 2)
        self.assertIn("--terms", payload["recorderCommand"])
        self.assertIn("--duration-sec 300", payload["recorderCommand"])
        self.assertIn("--max-output-mb 128", payload["recorderCommand"])
        self.assertIn("--min-free-gb 20", payload["recorderCommand"])
        statuses = {item["tokenId"]: item["coverageStatus"] for item in payload["staleContextTargets"]}
        self.assertEqual(statuses["missing-token"], "no-quotes-for-clob-token")
        self.assertEqual(statuses["token-with-post-only"], "missing-pre-and-post-window")
        self.assertIn("event-lag-replay-not-watch-ready", payload["blockers"])
        self.assertIn("past-event-pre-window-unrecoverable-use-forward-capture", payload["blockers"])
        self.assertTrue(payload["forwardCapturePlan"]["required"])
        self.assertIn("--terms", payload["standingRecorderCommand"])
        self.assertEqual(payload["maxOutputMb"], 128)
        self.assertEqual(payload["minFreeGb"], 20)

    def test_coverage_status_uses_any_quote_inside_pre_window_not_first_quote_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            clob = Path(tmp) / "clob.jsonl"
            event_time = datetime.now(timezone.utc) + timedelta(hours=2)
            asset = "token-with-valid-pre"
            rows = [
                {
                    "eventType": "best_bid_ask",
                    "assetId": asset,
                    "localTs": (event_time - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.40",
                    "bestAsk": "0.42",
                },
                {
                    "eventType": "best_bid_ask",
                    "assetId": asset,
                    "localTs": (event_time - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.41",
                    "bestAsk": "0.43",
                },
                {
                    "eventType": "best_bid_ask",
                    "assetId": asset,
                    "localTs": (event_time + timedelta(minutes=120)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.45",
                    "bestAsk": "0.47",
                },
            ]
            clob.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

            payload = build_targets(
                mapping_plan={
                    "decision": "research-only-event-market-mapping-candidates-ready",
                    "candidates": [{
                        "externalId": "valid-window-market",
                        "clobTokenId": asset,
                        "question": "Fed rate decision?",
                        "headline": "Fed headline",
                        "articleDatetime": int(event_time.timestamp()),
                        "topBookDepth": 100,
                        "score": 10,
                    }],
                },
                replay={"decision": "research-only-event-lag-replay-watch"},
                clob_paths=[clob],
                max_assets=1,
                duration_sec=120,
            )

        self.assertEqual(payload["targetCount"], 0)
        self.assertEqual(payload["completeWindowTargetCount"], 1)
        self.assertEqual(payload["staleContextTargets"][0]["coverageStatus"], "window-range-present")
        self.assertEqual(payload["blockers"], [])
        self.assertFalse(payload["forwardCapturePlan"]["required"])

    def test_ambiguous_mapping_candidates_are_excluded_from_token_specific_capture(self):
        event_time = datetime.now(timezone.utc) + timedelta(hours=2)
        payload = build_targets(
            mapping_plan={
                "decision": "research-only-event-market-mapping-blocked",
                "blockers": [
                    "ambiguous-headline-event-family-fanout",
                    "ambiguous-headline-counterparty-fanout",
                ],
                "candidates": [
                    {
                        "externalId": "ambiguous-market",
                        "clobTokenId": "ambiguous-token",
                        "question": "US x Iran permanent peace deal?",
                        "headline": "Peace deal with Iran could still spell a Fed rate hike",
                        "articleDatetime": int(event_time.timestamp()),
                        "topBookDepth": 100,
                        "score": 10,
                        "mappingStatus": "ambiguous-headline-family-review-required",
                        "specificityFlags": [
                            "headline-has-multiple-event-families",
                            "market-counterparty-not-explicit-in-headline",
                        ],
                    },
                ],
            },
            replay={"decision": "research-only-event-lag-replay-watch"},
            clob_paths=[],
            mapping_refinement={
                "publicCaptureReviewLeads": [
                    {
                        "tokenId": "review-token",
                        "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                        "counterparty": "iran/us",
                        "deadlineText": "june 30",
                        "status": "fillable-live-book",
                        "spread": 0.02,
                        "reviewUseOnly": "public-capture-fillability-lead; not a mapping override, signal, or paper approval",
                    }
                ]
            },
            max_assets=5,
            duration_sec=120,
        )

        self.assertEqual(payload["candidateCount"], 1)
        self.assertEqual(payload["tokenSpecificCandidateCount"], 0)
        self.assertEqual(payload["excludedMappingCandidateCount"], 1)
        self.assertEqual(payload["targetCount"], 0)
        self.assertIn("event-market-mapping-not-token-specific", payload["blockers"])
        self.assertIn("ambiguous-mapping-candidates-excluded-from-token-capture", payload["blockers"])
        self.assertEqual(payload["publicCaptureReviewLeadCount"], 1)
        self.assertIn("--token-id 'review-token'", payload["reviewLeadRecorderCommand"])
        self.assertEqual(payload["forwardCapturePlan"]["reviewLeadCommand"], payload["reviewLeadRecorderCommand"])
        self.assertIn("not a mapping override", payload["publicCaptureReviewLeads"][0]["reviewUseOnly"])
        self.assertIn("headline-has-multiple-event-families", payload["excludedMappingReasonCounts"])
        self.assertIn("market-counterparty-not-explicit-in-headline", payload["excludedMappingReasonCounts"])
        self.assertTrue(payload["forwardCapturePlan"]["required"])
        self.assertIn("standing term capture", payload["forwardCapturePlan"]["reason"])
        self.assertIn("--terms", payload["recorderCommand"])

    def test_manual_selected_forward_capture_candidate_bypasses_ambiguous_fanout_for_research_capture_only(self):
        event_time = datetime.now(timezone.utc) + timedelta(hours=2)
        payload = build_targets(
            mapping_plan={
                "decision": "research-only-event-market-mapping-blocked",
                "blockers": [
                    "ambiguous-headline-event-family-fanout",
                    "ambiguous-headline-counterparty-fanout",
                ],
                "candidates": [
                    {
                        "externalId": "2354003",
                        "clobTokenId": "selected-token",
                        "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                        "headline": "Peace deal with Iran could still spell a Fed rate hike",
                        "articleDatetime": int(event_time.timestamp()),
                        "topBookDepth": 100,
                        "score": 10,
                        "mappingStatus": "ambiguous-headline-family-review-required",
                        "specificityFlags": [
                            "headline-has-multiple-event-families",
                            "market-counterparty-not-explicit-in-headline",
                        ],
                    },
                    {
                        "externalId": "1962237",
                        "clobTokenId": "still-ambiguous-token",
                        "question": "US x Iran permanent peace deal by June 30, 2026?",
                        "headline": "Peace deal with Iran could still spell a Fed rate hike",
                        "articleDatetime": int(event_time.timestamp()),
                        "topBookDepth": 100,
                        "score": 9,
                        "mappingStatus": "ambiguous-headline-family-review-required",
                        "specificityFlags": [
                            "headline-has-multiple-event-families",
                            "market-counterparty-not-explicit-in-headline",
                        ],
                    },
                ],
            },
            replay={"decision": "research-only-event-lag-replay-watch"},
            clob_paths=[],
            mapping_refinement={
                "decision": "research-only-mapping-refinement-ready-for-forward-capture",
                "readyForForwardCapture": True,
                "headlineReviews": [
                    {
                        "mappingQuality": "manual-selected-forward-capture-watch",
                        "manualSelectedExternalId": "2354003",
                        "manualSelectedTokenId": "selected-token",
                        "manualSelectedQuestion": "US announces new Iran agreement/ceasefire extension by June 30?",
                    }
                ],
            },
            max_assets=5,
            duration_sec=120,
        )

        self.assertEqual(payload["decision"], "research-only-forward-capture-review-leads-ready")
        self.assertEqual(payload["manualSelectedForwardCaptureCount"], 1)
        self.assertEqual(payload["tokenSpecificCandidateCount"], 1)
        self.assertEqual(payload["excludedMappingCandidateCount"], 1)
        self.assertNotIn("event-market-mapping-not-token-specific", payload["blockers"])
        self.assertNotIn("ambiguous-mapping-candidates-excluded-from-token-capture", payload["blockers"])
        self.assertIn("--token-id 'selected-token'", payload["reviewLeadRecorderCommand"])
        self.assertEqual(payload["forwardCapturePlan"]["reviewLeadCommand"], payload["reviewLeadRecorderCommand"])
        self.assertIn("Manual review selected", payload["forwardCapturePlan"]["reason"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_deadline_ladder_candidates_create_review_lead_command_without_clearing_mapping(self):
        event_time = datetime.now(timezone.utc) + timedelta(hours=2)
        payload = build_targets(
            mapping_plan={
                "decision": "research-only-event-market-mapping-blocked",
                "blockers": ["ambiguous-headline-counterparty-fanout"],
                "candidates": [
                    {
                        "externalId": "ambiguous-market",
                        "clobTokenId": "ambiguous-token",
                        "question": "US x Iran permanent peace deal by June 30, 2026?",
                        "headline": "Donald Trump asks for amendments to agreed upon draft of US-Iran ceasefire deal",
                        "articleDatetime": int(event_time.timestamp()),
                        "mappingStatus": "ambiguous-headline-family-review-required",
                        "specificityFlags": ["headline-has-multiple-event-families"],
                    },
                ],
            },
            replay={"decision": "research-only-event-lag-replay-watch"},
            clob_paths=[],
            mapping_refinement={
                "decision": "research-only-mapping-refinement-required",
                "readyForForwardCapture": False,
                "deadlineLadderCaptureCandidates": [
                    {
                        "tokenId": "agreement-ladder-token",
                        "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                        "deadlineText": "june 30",
                        "bestBid": 0.71,
                        "bestAsk": 0.72,
                        "spreadPct": 1,
                        "reviewUseOnly": "deadline-ladder-forward-capture-only; not a mapping override, paper approval, signal, or execution approval",
                    }
                ],
            },
            max_assets=5,
            duration_sec=120,
        )

        self.assertEqual(payload["decision"], "research-only-forward-capture-required")
        self.assertEqual(payload["deadlineLadderCaptureCandidateCount"], 1)
        self.assertEqual(payload["publicCaptureReviewLeadCount"], 1)
        self.assertEqual(payload["publicCaptureReviewLeads"][0]["leadType"], "deadline-ladder-forward-capture")
        self.assertIn("--token-id 'agreement-ladder-token'", payload["reviewLeadRecorderCommand"])
        self.assertIn("deadline ladder", payload["forwardCapturePlan"]["reason"])
        self.assertIn("event-market-mapping-not-token-specific", payload["blockers"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])

    def test_manual_selected_forward_capture_survives_mapping_plan_refresh_shape_change(self):
        event_time = datetime.now(timezone.utc) - timedelta(hours=3)
        payload = build_targets(
            mapping_plan={
                "decision": "research-only-event-market-mapping-blocked",
                "blockers": ["ambiguous-headline-counterparty-fanout"],
                "candidates": [],
            },
            replay={"decision": "research-only-event-lag-replay-blocked"},
            clob_paths=[],
            mapping_refinement={
                "decision": "research-only-mapping-refinement-ready-for-forward-capture",
                "readyForForwardCapture": True,
                "headlineReviews": [
                    {
                        "mappingQuality": "manual-selected-forward-capture-watch",
                        "headline": "Peace deal with Iran could still spell a Fed rate hike",
                        "eventIso": event_time.isoformat(),
                        "manualSelectedExternalId": "2354003",
                        "manualSelectedTokenId": "selected-review-token",
                        "manualSelectedQuestion": "US announces new Iran agreement/ceasefire extension by June 30?",
                    }
                ],
            },
            max_assets=5,
            duration_sec=120,
        )

        self.assertEqual(payload["decision"], "research-only-forward-capture-review-leads-ready")
        self.assertEqual(payload["manualSelectedForwardCaptureCount"], 1)
        self.assertEqual(payload["publicCaptureReviewLeadCount"], 1)
        self.assertEqual(payload["publicCaptureReviewLeads"][0]["tokenId"], "selected-review-token")
        self.assertIn("--token-id 'selected-review-token'", payload["reviewLeadRecorderCommand"])
        self.assertEqual(payload["targetCount"], 0)
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])


if __name__ == "__main__":
    unittest.main()
