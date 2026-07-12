import unittest

from scripts.prediction_label_card_bootstrap import (
    VAULT,
    build_bootstrap,
    classify_market_type,
    default_markdown_path,
    infer_yes_outcome,
    render_markdown,
)


class PredictionLabelCardBootstrapTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-label-card-bootstrap-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "sourceRowsScanned": 0,
            "candidateRows": 0,
            "selectedRows": 0,
            "typeCounts": {},
            "blockers": [],
            "rows": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Label Card Bootstrap - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_classifies_only_iran_event_markets(self):
        self.assertEqual(classify_market_type("Israel x Iran peace deal in 2024?"), "peace-deal")
        self.assertEqual(classify_market_type("Israel military action against Iran by end of 2024?"), "military-action")
        self.assertEqual(classify_market_type("Israel strikes Iranian oil in October?"), "strike")
        self.assertIsNone(classify_market_type('Will Trump say "Iran" during Michigan rally?'))
        self.assertIsNone(classify_market_type("Will Iran win the 2024 Chess Olympiad?"))

    def test_infers_yes_outcome_from_closed_polymarket_prices(self):
        self.assertTrue(infer_yes_outcome({"outcomes": '["Yes","No"]', "outcome_prices": '["1","0"]'}))
        self.assertFalse(infer_yes_outcome({"outcomes": '["Yes","No"]', "outcome_prices": '["0","1"]'}))
        self.assertIsNone(infer_yes_outcome({"outcomes": '["Yes","No"]', "outcome_prices": '["0.55","0.45"]'}))

    def test_build_bootstrap_is_research_only_and_excludes_speech_rows(self):
        payload = build_bootstrap(
            source_rows=[
                {
                    "id": "510138",
                    "question": "Israel x Iran peace deal in 2024?",
                    "slug": "israel-x-iran-peace-deal-in-2024",
                    "outcomes": '["Yes","No"]',
                    "outcome_prices": '["0","1"]',
                    "end_date": "2024-12-31 12:00:00+00",
                    "volume": 100.0,
                },
                {
                    "id": "508636",
                    "question": 'Will Trump say "Iran" during Michigan rally?',
                    "slug": "will-trump-say-iran-during-michigan-rally",
                    "outcomes": '["Yes","No"]',
                    "outcome_prices": '["1","0"]',
                    "end_date": "2024-10-03 13:00:00+01",
                    "volume": 1000.0,
                },
            ],
            max_rows=10,
        )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["selectedRows"], 1)
        self.assertEqual(payload["rows"][0]["externalId"], "510138")
        self.assertFalse(payload["rows"][0]["outcomeWon"])


if __name__ == "__main__":
    unittest.main()
