import tempfile
import unittest
from pathlib import Path

from scripts.prediction_label_card_audit import (
    HERMES,
    build_audit,
    default_markdown_path,
    extract_label_rows,
    render_markdown,
)


class PredictionLabelCardAuditTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^prediction-label-card-audit-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "cardCount": 0,
            "validResolvedLabelRows": 0,
            "incompleteRows": 0,
            "blockers": [],
            "cards": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Label Card Audit - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_template_row_does_not_count_as_valid_label(self):
        text = """
# Prediction Label Card

Status: `candidate`

| venue | externalId | question | closeTime | settlementSourceUrl | outcomeLabel | outcomeWon | marketType | subjectKey | notes |
|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  | Yes/No | true/false | ceasefire | iran |  |
"""
        present, rows = extract_label_rows(text)

        self.assertTrue(present)
        self.assertEqual(len(rows), 1)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "geopolitics-iran.md").write_text(text)
            payload = build_audit(
                card_root=root,
                event_gap_plan={
                    "gapItems": [
                        {
                            "collectionPlan": {
                                "manualSettlementCard": str(root / "geopolitics-iran.md")
                            }
                        }
                    ]
                },
            )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["validResolvedLabelRows"], 0)
        self.assertIn("no-valid-label-card-rows", payload["blockers"])
        self.assertIn("incomplete-label-card-rows", payload["blockers"])

    def test_valid_row_can_clear_card_audit_research_only(self):
        text = """
# Prediction Label Card

Status: `active`

| venue | externalId | question | closeTime | settlementSourceUrl | outcomeLabel | outcomeWon | marketType | subjectKey | notes |
|---|---|---|---|---|---|---|---|---|---|
| polymarket | 510138 | Israel x Iran peace deal in 2024? | 2024-12-31T12:00:00Z | https://example.com/settlement | Yes | false | peace-deal | iran | comparable wording |
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = root / "geopolitics-iran.md"
            card.write_text(text)
            payload = build_audit(
                card_root=root,
                event_gap_plan={"gapItems": [{"collectionPlan": {"manualSettlementCard": str(card)}}]},
            )

        self.assertEqual(payload["validResolvedLabelRows"], 1)
        self.assertEqual(payload["incompleteRows"], 0)
        self.assertEqual(payload["decision"], "research-only-label-cards-ready-for-join-intake")
        self.assertFalse(payload["readyForExecution"])


if __name__ == "__main__":
    unittest.main()
