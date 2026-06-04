import unittest

from scripts.topstep_demo_observation_posture import build_posture, render_markdown


class TopstepDemoObservationPostureTest(unittest.TestCase):
    def test_ready_observation_still_blocks_algo_expansion_and_execution(self):
        payload = build_posture(
            goal={"blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"]},
            clearance={"status": "PASS", "allCommandsPassed": True},
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
            session_clearance={
                "machineChecksPassed": True,
                "operatorConfirmationRequired": False,
                "readyForReadOnlyProofWindow": True,
                "blockers": [],
            },
            premarket={
                "command": "premarket-risk-brief",
                "decision": "NO_TRADE_ALGO",
                "sizingPosture": {
                    "algoMaxContracts": 0,
                    "manualWatchMaxContractsIfDailyPlanClears": 0,
                },
                "risks": [
                    {"kind": "daily-plan", "severity": "hard"},
                    {"kind": "signal-quality-warning", "severity": "reduce"},
                ],
            },
            topstep_learning={"decision": "demo-learning-visible-execution-locked"},
            runtime_architecture={"decision": "runtime-architecture-visible-execution-locked"},
            source_hygiene={"sourceHygieneCleared": False, "sourceCleanBlockers": ["dirty source"]},
            prediction_gate={"decision": "research-only-paper-promotion-blocked"},
            operator_demo_pnl=3000.0,
        )

        self.assertEqual(payload["decision"], "demo-observation-ready-execution-locked")
        self.assertTrue(payload["readyForHumanDemoObservation"])
        self.assertTrue(payload["readyForReadOnlyProofWindow"])
        self.assertFalse(payload["readyForAlgoDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertEqual(payload["operatorDemoContext"]["reportedPnlDollars"], 3000.0)
        self.assertFalse(payload["operatorDemoContext"]["brokerProof"])
        self.assertIn("futures-demo-not-cleared", payload["algoExpansionBlockers"])
        self.assertIn("daily-plan", payload["premarketGate"]["hardRiskKinds"])
        self.assertEqual(payload["authorityBoundaries"]["agentsMayRouteOrders"], False)
        self.assertEqual(payload["aiScientistFit"]["fit"], "research-loop-only")

        markdown = render_markdown(payload)
        self.assertIn("Topstep Demo Observation Posture", markdown)
        self.assertIn("operator claims as context only", markdown)
        self.assertIn("eodDreaming", markdown)

    def test_missing_control_artifacts_blocks_observation(self):
        payload = build_posture(
            goal={},
            clearance={"status": "FAIL", "allCommandsPassed": False},
            handoff={},
            session_clearance={"machineChecksPassed": False},
            premarket={},
            topstep_learning={},
            runtime_architecture={},
            source_hygiene={},
            prediction_gate={},
        )

        self.assertEqual(payload["decision"], "demo-observation-blocked-execution-locked")
        self.assertFalse(payload["readyForHumanDemoObservation"])
        self.assertIn("clearance-evidence-not-pass", payload["observationBlockers"])
        self.assertIn("premarket-risk-brief-missing", payload["observationBlockers"])
        self.assertFalse(payload["readyForExecution"])


if __name__ == "__main__":
    unittest.main()
