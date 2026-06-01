import unittest

from scripts.prediction_resolved_outcome_join import resolve_for_item, subject_tokens


class PredictionResolvedOutcomeJoinTests(unittest.TestCase):
    def test_subject_tokens_remove_family_terms(self):
        self.assertEqual(subject_tokens("Will Argentina win the 2026 FIFA World Cup?"), {"argentina"})

    def test_broad_family_matches_do_not_count_as_subject_specific_history(self):
        item = {
            "venue": "polymarket",
            "externalId": "arg-2026",
            "question": "Will Argentina win the 2026 FIFA World Cup?",
            "outcomeLabel": "Yes",
        }
        historical = [
            {
                "venue": "polymarket",
                "externalId": "arg-2022",
                "question": "Will Argentina win the 2022 World Cup?",
                "outcomes": '["Yes", "No"]',
                "outcome_prices": '["1", "0"]',
            },
            {
                "venue": "polymarket",
                "externalId": "bra-2022",
                "question": "Will Brazil win the 2022 World Cup?",
                "outcomes": '["Yes", "No"]',
                "outcome_prices": '["0", "1"]',
            },
            {
                "venue": "polymarket",
                "externalId": "fra-2022",
                "question": "Will France win the 2022 World Cup?",
                "outcomes": '["Yes", "No"]',
                "outcome_prices": '["0", "1"]',
            },
        ]

        report = resolve_for_item(
            item,
            historical,
            min_score=0.1,
            min_matches=3,
            min_overlap_tokens=2,
            min_specific_matches=2,
            min_specific_overlap_tokens=1,
            top_n=8,
        )

        self.assertEqual(report["resolvedMatchCount"], 3)
        self.assertEqual(report["subjectSpecificMatchCount"], 1)
        self.assertEqual(report["status"], "insufficient-subject-specific-history")
        self.assertIn("too-few-subject-specific-resolved-outcomes", report["blockers"])

    def test_subject_specific_history_can_join_research_only(self):
        item = {
            "venue": "polymarket",
            "externalId": "arg-2026",
            "question": "Will Argentina win the 2026 FIFA World Cup?",
            "outcomeLabel": "Yes",
        }
        historical = [
            {
                "venue": "polymarket",
                "externalId": f"arg-{year}",
                "question": f"Will Argentina win the {year} World Cup?",
                "outcomes": '["Yes", "No"]',
                "outcome_prices": '["1", "0"]',
            }
            for year in range(2010, 2015)
        ]

        report = resolve_for_item(
            item,
            historical,
            min_score=0.1,
            min_matches=5,
            min_overlap_tokens=2,
            min_specific_matches=5,
            min_specific_overlap_tokens=1,
            top_n=8,
        )

        self.assertEqual(report["resolvedMatchCount"], 5)
        self.assertEqual(report["subjectSpecificMatchCount"], 5)
        self.assertEqual(report["status"], "joined-research-only")
        self.assertEqual(report["subjectSpecificWinRate"], 1.0)


if __name__ == "__main__":
    unittest.main()
