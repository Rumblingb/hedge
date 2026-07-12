import unittest
from pathlib import Path

from scripts.prediction_label_source_manifest import (
    VAULT,
    build_label_manifest,
    coverage_for_watch_item,
    default_markdown_path,
    render_markdown,
)


class PredictionLabelSourceManifestTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-label-source-manifest-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "watchCount": 0,
            "historicalRowsLoaded": 0,
            "labelCardRowsLoaded": 0,
            "usableForResearchJoinCount": 0,
            "itemsNeedingNewLabelSource": 0,
            "statusCounts": {},
            "coverage": [],
            "repeatedFamilies": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Label Source Manifest - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_subject_specific_label_shortage_is_explicit(self):
        item = {
            "venue": "polymarket",
            "externalId": "iran-2026",
            "question": "US announces new Iran agreement/ceasefire extension by June 3?",
            "outcomeLabel": "Yes",
        }
        historical = [
            {
                "venue": "polymarket",
                "externalId": f"generic-{idx}",
                "question": f"Will there be a ceasefire deal in market {idx}?",
                "outcomes": '["Yes", "No"]',
                "outcome_prices": '["1", "0"]',
            }
            for idx in range(6)
        ]

        report = coverage_for_watch_item(
            item,
            historical,
            min_score=0.05,
            min_matches=5,
            min_specific_matches=2,
            min_overlap_tokens=1,
            min_specific_overlap_tokens=1,
            top_matches=5,
        )

        self.assertEqual(report["status"], "needs-subject-label-source")
        self.assertEqual(report["familyResolvedCount"], 6)
        self.assertEqual(report["subjectResolvedCount"], 0)
        self.assertIn("too-few-subject-resolved-labels", report["blockers"])

    def test_manifest_never_marks_items_paper_ready(self):
        watchlist = {
            "items": [
                {
                    "venue": "polymarket",
                    "externalId": "arg-2026",
                    "question": "Will Argentina win the 2026 FIFA World Cup?",
                    "outcomeLabel": "Yes",
                }
            ]
        }
        historical = [
            {
                "venue": "polymarket",
                "externalId": f"arg-{year}",
                "question": f"Will Argentina win the {year} World Cup?",
                "outcomes": '["Yes", "No"]',
                "outcome_prices": '["1", "0"]',
            }
            for year in range(2010, 2016)
        ]

        payload = build_label_manifest(
            watchlist=watchlist,
            historical=historical,
            manifest_path=Path("/tmp/prediction-manifest.json"),
            min_score=0.05,
            min_matches=5,
            min_specific_matches=5,
            min_overlap_tokens=2,
            min_specific_overlap_tokens=1,
        )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["items"], payload["coverage"])
        self.assertIn("historicalManifest", payload["sources"])
        self.assertEqual(payload["usableForResearchJoinCount"], 1)
        self.assertEqual(payload["coverage"][0]["status"], "usable-for-research-join")
        self.assertIn("No item in this manifest approves paper", payload["hardRules"][2])

    def test_label_card_rows_can_supply_subject_specific_history_research_only(self):
        item = {
            "venue": "polymarket",
            "externalId": "iran-2026",
            "question": "US announces new Iran agreement/ceasefire extension by June 3?",
            "outcomeLabel": "Yes",
        }
        label_card_rows = [
            {
                "venue": "polymarket",
                "externalId": f"iran-card-{idx}",
                "question": f"Iran military response label {idx}?",
                "closeTime": "2024-10-31T12:00:00Z",
                "settlementSourceUrl": "https://polymarket.com/event/example",
                "outcomeLabel": "Yes",
                "outcomeWon": "false",
                "marketType": "military-action",
                "subjectKey": "iran",
                "category": "geopolitics",
                "cardPath": "/tmp/geopolitics-iran.md",
            }
            for idx in range(5)
        ]

        report = coverage_for_watch_item(
            item,
            historical=[],
            label_card_rows=label_card_rows,
            min_score=0.35,
            min_matches=5,
            min_specific_matches=5,
            min_overlap_tokens=2,
            min_specific_overlap_tokens=1,
            top_matches=5,
        )

        self.assertEqual(report["status"], "usable-for-research-join")
        self.assertEqual(report["labelCardFamilyRows"], 5)
        self.assertEqual(report["labelCardSubjectRows"], 5)
        self.assertEqual(report["rawArchiveSubjectResolvedCount"], 0)


if __name__ == "__main__":
    unittest.main()
