import unittest

from scripts import ai_scientist_hermes_research_access as access


class AiScientistHermesResearchAccessTest(unittest.TestCase):
    def test_safety_ok_requires_research_only_and_no_side_effects(self):
        self.assertTrue(access.safety_ok({
            "research_only": True,
            "writes_orders": False,
            "touches_broker": False,
            "moves_funds": False,
        }))
        self.assertFalse(access.safety_ok({
            "research_only": True,
            "writes_orders": True,
            "touches_broker": False,
            "moves_funds": False,
        }))

    def test_classifies_candidate_watch_without_execution(self):
        summary = {
            "id": "3m-nq-orb",
            "decision": "research-only-template-candidate",
            "metricBlockers": [],
            "oosTradeCount": 153,
            "readyForExecution": False,
        }

        self.assertEqual(access.classify_research_posture(summary), "watch-research-candidate")

    def test_classifies_negative_or_thin_results_as_not_ready(self):
        self.assertEqual(
            access.classify_research_posture({
                "id": "30m-orb",
                "decision": "research-only-template-blocked",
                "metricBlockers": ["too-few-oos-trades"],
                "oosTradeCount": 1,
                "readyForExecution": False,
            }),
            "thin-or-no-edge",
        )
        self.assertEqual(
            access.classify_research_posture({
                "id": "15m-orb",
                "decision": "research-only-template-blocked",
                "metricBlockers": ["oos-profit-factor-too-low"],
                "oosTradeCount": 57,
                "readyForExecution": False,
            }),
            "blocked-no-edge-current-settings",
        )

    def test_render_markdown_exposes_hermes_policy(self):
        packet = {
            "generatedAt": "2026-06-07T00:00:00+00:00",
            "decision": "hermes-ai-scientist-research-access-ready",
            "readyForExecution": False,
            "writesOrders": False,
            "touchesBroker": False,
            "automationPosture": {
                "status": "PASS",
                "decision": "codex-automations-visible-research-locked",
                "activeBillAutomationCount": 4,
                "activeFuturesOpenSessionProofIds": ["bill-open-session-data-proof"],
                "activePredictionCaptureIds": ["bill-prediction-forward-clob-capture"],
            },
            "strategyEvidence": [
                {
                    "id": "3m-nq-orb",
                    "strategy": "orb",
                    "timeframe": "3m",
                    "researchPosture": "watch-research-candidate",
                    "oosNetPoints": 776.5,
                    "oosProfitFactor": 1.35,
                    "metricBlockers": [],
                }
            ],
            "hermesAccessPolicy": {
                "cheapModelUse": "Cheaper models may draft one-variable hypotheses.",
                "allowed": ["summarize final_info.json"],
                "forbidden": ["write orders"],
            },
            "safeCommands": ["npm run --silent bill:ai-scientist-data-access-audit"],
            "nextOneVariableResearch": ["Stress NQ 3m ORB by year/regime."],
        }

        markdown = access.render_markdown(packet)

        self.assertIn("AI-Scientist Hermes Research Access", markdown)
        self.assertIn("Cheaper models may draft one-variable hypotheses", markdown)
        self.assertIn("write orders", markdown)


if __name__ == "__main__":
    unittest.main()
