import unittest
from pathlib import Path

from scripts import ai_scientist_data_access_audit as audit


class AiScientistDataAccessAuditTest(unittest.TestCase):
    def test_audit_separates_available_data_from_template_visible_data(self):
        payload = audit.build_audit(
            template_defaults={
                "15m": Path("/repo/data/free/NQ-2022-2025-15m.csv"),
                "60m-es": Path("/repo/data/free/ES-2000-2019-60m.csv"),
            },
            data_master={
                "datasetCount": 4,
                "tierCounts": {"gold-walkforward": 3},
                "topDatasets": [
                    {
                        "path": "/repo/data/free/NQ-2022-2025-15m.csv",
                        "rows": 70685,
                        "timeframe": "15min",
                        "trustTier": "gold-walkforward",
                        "symbols": ["NQ"],
                    },
                    {
                        "path": "data/free/NQ-1min-2022-2025.csv",
                        "rows": 1048575,
                        "timeframe": "1min",
                        "trustTier": "gold-walkforward",
                        "symbols": ["NQ"],
                    },
                    {
                        "path": "data/research/ALL-6MARKETS-1m-30d.csv",
                        "rows": 175871,
                        "timeframe": "1min",
                        "trustTier": "gold-walkforward",
                        "symbols": ["NQ", "ES"],
                    },
                ],
            },
        )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["decision"], "research-only-ai-scientist-data-access-incomplete")
        self.assertEqual(payload["templateDefaultCount"], 2)
        self.assertEqual(payload["goldWalkforwardCount"], 3)
        self.assertEqual(payload["visibleGoldWalkforwardCount"], 1)
        self.assertEqual(len(payload["missingHighValueDatasets"]), 2)
        self.assertIn("ai-scientist-1m-entry-data", [item["id"] for item in payload["nextOneVariableWiring"]])

    def test_markdown_lists_feature_gaps_and_next_wiring(self):
        payload = audit.build_audit(
            template_defaults={},
            data_master={"datasetCount": 0, "tierCounts": {}, "topDatasets": []},
        )

        markdown = audit.render_markdown(payload)

        self.assertIn("AI-Scientist Data Access Audit", markdown)
        self.assertIn("Feature Gaps", markdown)
        self.assertIn("one-minute-entry-data", markdown)
        self.assertIn("ai-scientist-leading-indicator-join", markdown)


if __name__ == "__main__":
    unittest.main()
