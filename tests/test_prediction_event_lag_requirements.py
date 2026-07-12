import unittest
from datetime import datetime, timezone

from scripts.prediction_event_lag_requirements import VAULT, build_requirements, default_markdown_path, render_markdown


class PredictionEventLagRequirementsTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-event-lag-requirements-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "passCount": 0,
            "blockedCount": 0,
            "requirements": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Event Lag Requirements - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_stale_news_and_thin_labels_block_event_lag(self):
        payload = build_requirements(
            news={
                "generated_at": "2026-05-01T00:00:00+00:00Z",
                "status": "BLOCKED_NO_DATA",
                "dataUsable": False,
                "api_key_status": "demo_limited",
                "fetchErrors": {"news": "HTTP Error 401", "calendar": "HTTP Error 401"},
                "articles": [{"headline": "Iran ceasefire talks continue", "source": "Reuters", "datetime": 1770000000}],
            },
            watchlist={
                "items": [
                    {"externalId": "1", "question": "US announces new Iran agreement/ceasefire extension by June 3?"},
                    {"externalId": "2", "question": "US x Iran permanent peace deal by June 15, 2026?"},
                ]
            },
            label_manifest={"usableForResearchJoinCount": 1, "statusCounts": {"needs-family-label-source": 2}},
            clob_audit={"readyFeatureCount": 4, "capture": {"recordsRead": 2852}},
            now=datetime(2026, 5, 30, tzinfo=timezone.utc),
        )

        by_id = {item["id"]: item for item in payload["requirements"]}

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["decision"], "research-only-event-lag-requirements-not-cleared")
        self.assertEqual(by_id["fresh-timestamped-news-source"]["status"], "blocked")
        self.assertEqual(by_id["fresh-timestamped-news-source"]["current"]["newsStatus"], "BLOCKED_NO_DATA")
        self.assertEqual(by_id["fresh-timestamped-news-source"]["current"]["apiKeyStatus"], "demo_limited")
        self.assertEqual(by_id["fresh-timestamped-news-source"]["current"]["fetchErrors"]["news"], "HTTP Error 401")
        self.assertEqual(by_id["resolved-label-coverage"]["status"], "blocked")
        self.assertEqual(by_id["clob-around-event-window"]["status"], "pass")

    def test_one_token_event_market_matches_are_not_enough(self):
        payload = build_requirements(
            news={
                "generated_at": "2026-05-30T00:00:00+00:00",
                "articles": [{"headline": f"Election update {idx}", "source": "unit", "datetime": idx} for idx in range(12)],
            },
            watchlist={
                "items": [
                    {"externalId": "1", "question": "Will Argentina win the 2026 FIFA World Cup?"},
                    {"externalId": "2", "question": "Will France win the 2026 FIFA World Cup?"},
                    {"externalId": "3", "question": "Will Brazil win the 2026 FIFA World Cup?"},
                ]
            },
            label_manifest={"usableForResearchJoinCount": 3, "statusCounts": {"usable-for-research-join": 3}},
            clob_audit={"readyFeatureCount": 3, "capture": {"recordsRead": 5000}},
            now=datetime(2026, 5, 30, 12, tzinfo=timezone.utc),
        )

        by_id = {item["id"]: item for item in payload["requirements"]}

        self.assertEqual(by_id["fresh-timestamped-news-source"]["status"], "pass")
        self.assertEqual(by_id["event-to-market-mapping"]["status"], "blocked")
        self.assertEqual(by_id["event-to-market-mapping"]["current"]["matchCount"], 0)

    def test_event_lag_requirements_can_clear_research_without_paper_approval(self):
        payload = build_requirements(
            news={
                "generated_at": "2026-05-30T00:00:00+00:00",
                "articles": [
                    {"headline": "Iran agreement extension talks", "source": "Reuters", "datetime": 1770000000},
                    {"headline": "Iran peace deal negotiation", "source": "Reuters", "datetime": 1770000001},
                    {"headline": "World Cup Argentina outlook", "source": "Reuters", "datetime": 1770000002},
                ] * 4,
            },
            watchlist={
                "items": [
                    {"externalId": "1", "question": "US announces new Iran agreement/ceasefire extension by June 3?"},
                    {"externalId": "2", "question": "US x Iran permanent peace deal by June 15, 2026?"},
                    {"externalId": "3", "question": "Will Argentina win the 2026 FIFA World Cup?"},
                ]
            },
            label_manifest={"usableForResearchJoinCount": 3, "statusCounts": {"usable-for-research-join": 3}},
            clob_audit={"readyFeatureCount": 3, "capture": {"recordsRead": 5000}},
            now=datetime(2026, 5, 30, 12, tzinfo=timezone.utc),
        )

        self.assertEqual(payload["blockedCount"], 0)
        self.assertEqual(payload["decision"], "research-only-event-lag-requirements-cleared")
        self.assertFalse(payload["readyForPaper"])

    def test_strict_mapping_plan_can_satisfy_event_mapping_without_paper_approval(self):
        payload = build_requirements(
            news={
                "generated_at": "2026-05-30T00:00:00+00:00",
                "articles": [{"headline": f"Iran ceasefire extension update {idx}", "source": "unit", "datetime": idx} for idx in range(12)],
            },
            watchlist={"items": []},
            label_manifest={"usableForResearchJoinCount": 3, "statusCounts": {"usable-for-research-join": 3}},
            clob_audit={"readyFeatureCount": 3, "capture": {"recordsRead": 5000}},
            event_mapping_plan={
                "decision": "research-only-event-market-mapping-candidates-ready",
                "candidates": [
                    {"externalId": f"iran-{idx}", "question": "US x Iran permanent peace deal?", "settlementTextPresent": True}
                    for idx in range(3)
                ],
            },
            now=datetime(2026, 5, 30, 12, tzinfo=timezone.utc),
        )

        by_id = {item["id"]: item for item in payload["requirements"]}
        self.assertEqual(by_id["event-to-market-mapping"]["status"], "pass")
        self.assertEqual(by_id["event-to-market-mapping"]["current"]["strictMappingCandidateCount"], 3)
        self.assertEqual(payload["blockedCount"], 0)
        self.assertFalse(payload["readyForPaper"])


if __name__ == "__main__":
    unittest.main()
