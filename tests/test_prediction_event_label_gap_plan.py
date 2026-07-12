import unittest

from scripts.prediction_event_label_gap_plan import HERMES, build_plan, default_markdown_path, render_markdown


class PredictionEventLabelGapPlanTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^prediction-event-label-gap-plan-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "eventLagDecision": "research-only",
            "gapCount": 0,
            "eventMappedGapCount": 0,
            "blockedRequirements": [],
            "labelStatusCounts": {},
            "gapItems": [],
            "nextCommands": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Event Label Gap Plan - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_mapped_event_label_gaps_are_promoted_to_collection_plan(self):
        payload = build_plan(
            event_requirements={
                "decision": "research-only-event-lag-requirements-not-cleared",
                "eventMarketMatches": [
                    {
                        "externalId": "iran-extension",
                        "question": "US announces new Iran agreement/ceasefire extension by June 3?",
                        "headline": "Trump weighs extending Iran ceasefire",
                    }
                ],
                "requirements": [
                    {"id": "fresh-timestamped-news-source", "status": "pass"},
                    {"id": "resolved-label-coverage", "status": "blocked"},
                ],
            },
            event_lag_replay={},
            label_manifest={
                "coverage": [
                    {
                        "externalId": "iran-extension",
                        "venue": "polymarket",
                        "question": "US announces new Iran agreement/ceasefire extension by June 3?",
                        "category": "geopolitics",
                        "subjectKey": "iran",
                        "status": "needs-family-label-source",
                        "familyResolvedCount": 0,
                        "subjectResolvedCount": 0,
                        "recommendedNextSource": "Polymarket closed markets plus manual settlement/event-source cards",
                        "blockers": ["too-few-family-resolved-labels"],
                    }
                ]
            },
            watchlist={"items": []},
            news={
                "articles": [
                    {
                        "headline": "Trump weighs extending Iran ceasefire",
                        "source": "unit",
                        "datetime": 1780000000,
                    }
                ]
            },
        )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["decision"], "research-only-label-gaps-remain")
        self.assertEqual(payload["eventMappedGapCount"], 1)
        self.assertEqual(payload["gapItems"][0]["externalId"], "iran-extension")
        self.assertEqual(payload["gapItems"][0]["collectionPlan"]["minimumNewResolvedLabels"]["family"], 20)
        self.assertIn("resolved-label-coverage", payload["blockedRequirements"])

    def test_next_commands_do_not_arm_execution_or_funding(self):
        payload = build_plan(
            event_requirements={"requirements": [], "eventMarketMatches": []},
            event_lag_replay={},
            label_manifest={"coverage": []},
            watchlist={"items": []},
            news={"articles": [{"headline": "Prediction market regulation update", "source": "unit"}]},
        )

        commands = " ".join(payload["nextCommands"]).lower()
        self.assertNotIn("execute", commands)
        self.assertNotIn("fund", commands)
        self.assertNotIn("broker", commands)
        self.assertFalse(payload["readyForExecution"])

    def test_mapped_items_with_usable_labels_are_not_label_gaps(self):
        payload = build_plan(
            event_requirements={
                "eventMarketMatches": [{"externalId": "iran-extension"}],
                "requirements": [{"id": "resolved-label-coverage", "status": "pass"}],
            },
            event_lag_replay={},
            label_manifest={
                "coverage": [
                    {
                        "externalId": "iran-extension",
                        "question": "US announces new Iran agreement/ceasefire extension by June 3?",
                        "category": "geopolitics",
                        "subjectKey": "iran",
                        "status": "usable-for-research-join",
                        "familyResolvedCount": 24,
                        "subjectResolvedCount": 24,
                    }
                ]
            },
            watchlist={"items": []},
            news={"articles": []},
        )

        self.assertEqual(payload["gapCount"], 0)
        self.assertEqual(payload["eventMappedGapCount"], 0)
        self.assertEqual(payload["decision"], "research-only-label-gap-plan-clear-for-replay")

    def test_non_label_blockers_do_not_look_like_label_gaps(self):
        payload = build_plan(
            event_requirements={
                "eventMarketMatches": [{"externalId": "iran-extension"}],
                "requirements": [{"id": "event-to-market-mapping", "status": "blocked"}],
            },
            event_lag_replay={},
            label_manifest={
                "coverage": [
                    {
                        "externalId": "iran-extension",
                        "question": "US announces new Iran agreement/ceasefire extension by June 3?",
                        "category": "geopolitics",
                        "subjectKey": "iran",
                        "status": "usable-for-research-join",
                        "familyResolvedCount": 24,
                        "subjectResolvedCount": 24,
                    }
                ]
            },
            watchlist={"items": []},
            news={"articles": []},
        )

        self.assertEqual(payload["gapCount"], 0)
        self.assertEqual(payload["blockedRequirements"], ["event-to-market-mapping"])
        self.assertEqual(payload["decision"], "research-only-label-gaps-cleared-but-event-requirements-blocked")
        self.assertFalse(payload["overallForwardCaptureRequired"])

    def test_clob_requirement_block_keeps_forward_capture_visible_even_when_replay_watches(self):
        payload = build_plan(
            event_requirements={
                "eventMarketMatches": [{"externalId": "iran-extension"}],
                "requirements": [
                    {"id": "resolved-label-coverage", "status": "pass"},
                    {"id": "clob-around-event-window", "status": "blocked"},
                ],
            },
            event_lag_replay={
                "decision": "research-only-event-lag-replay-watch",
                "completeEventCount": 5,
                "completeWindowCount": 5,
                "repricedWindowCount": 1,
                "blockers": [],
                "missingReasonCounts": {"no-pre-event-quote-within-window": 12},
            },
            label_manifest={
                "coverage": [
                    {
                        "externalId": "iran-extension",
                        "question": "US announces new Iran agreement/ceasefire extension by June 3?",
                        "category": "geopolitics",
                        "subjectKey": "iran",
                        "status": "usable-for-research-join",
                        "familyResolvedCount": 24,
                        "subjectResolvedCount": 24,
                    }
                ]
            },
            watchlist={"items": []},
            news={"articles": []},
        )

        self.assertEqual(payload["decision"], "research-only-label-gaps-cleared-but-event-requirements-blocked")
        self.assertFalse(payload["eventLagReplay"]["forwardCaptureRequired"])
        self.assertTrue(payload["eventRequirementForwardCaptureRequired"])
        self.assertTrue(payload["overallForwardCaptureRequired"])
        self.assertIn("standing public CLOB capture", payload["nextAction"])

    def test_clear_labels_point_to_forward_capture_when_replay_windows_are_missing(self):
        payload = build_plan(
            event_requirements={
                "eventMarketMatches": [{"externalId": "iran-extension"}],
                "requirements": [{"id": "resolved-label-coverage", "status": "pass"}],
            },
            event_lag_replay={
                "decision": "research-only-event-lag-replay-blocked",
                "completeEventCount": 0,
                "completeWindowCount": 0,
                "repricedWindowCount": 0,
                "blockers": ["too-few-complete-event-windows"],
                "missingReasonCounts": {"no-pre-event-quote-within-window": 4},
            },
            label_manifest={
                "coverage": [
                    {
                        "externalId": "iran-extension",
                        "question": "US announces new Iran agreement/ceasefire extension by June 3?",
                        "category": "geopolitics",
                        "subjectKey": "iran",
                        "status": "usable-for-research-join",
                        "familyResolvedCount": 24,
                        "subjectResolvedCount": 24,
                    }
                ]
            },
            watchlist={"items": []},
            news={"articles": []},
        )

        self.assertEqual(payload["gapCount"], 0)
        self.assertEqual(payload["decision"], "research-only-labels-clear-forward-capture-required")
        self.assertTrue(payload["eventLagReplay"]["forwardCaptureRequired"])
        self.assertTrue(payload["overallForwardCaptureRequired"])
        self.assertIn("standing public CLOB capture", payload["nextAction"])


if __name__ == "__main__":
    unittest.main()
