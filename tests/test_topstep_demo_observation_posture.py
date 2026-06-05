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
            topstep_learning={
                "decision": "demo-learning-visible-execution-locked",
                "learningStatus": "blocked-from-promotion",
                "issueCount": 2,
                "issues": [
                    {"id": "intended-vs-reconciled-side-mismatch"},
                    {"id": "operator-pnl-claim-needs-broker-proof"},
                ],
                "brokerReconciliation": {
                    "totalMatchedSize": 15,
                    "estimatedPnlDollars": 1650.0,
                    "tradeEvidenceSource": "trade-journal",
                },
                "operatorReportedPnl": {
                    "claims": [
                        {
                            "reportedNetUpDollars": 3000.0,
                            "reportedLosingDayDollars": -400.0,
                            "reportedLosingDayLabel": "Friday",
                        }
                    ],
                    "promotionUse": "context-only-until-broker-reconciled",
                },
            },
            runtime_architecture={"decision": "runtime-architecture-visible-execution-locked"},
            source_hygiene={"sourceHygieneCleared": False, "sourceCleanBlockers": ["dirty source"]},
            prediction_gate={"decision": "research-only-paper-promotion-blocked"},
        )

        self.assertEqual(payload["decision"], "demo-observation-ready-execution-locked")
        self.assertTrue(payload["readyForHumanDemoObservation"])
        self.assertTrue(payload["readyForReadOnlyProofWindow"])
        self.assertFalse(payload["readyForAlgoDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertEqual(payload["operatorDemoContext"]["reportedPnlDollars"], 3000.0)
        self.assertEqual(payload["operatorDemoContext"]["reportedLosingDayDollars"], -400.0)
        self.assertEqual(payload["operatorDemoContext"]["reportedLosingDayLabel"], "Friday")
        self.assertFalse(payload["operatorDemoContext"]["brokerProof"])
        self.assertEqual(payload["operatorDemoContext"]["promotionUse"], "context-only-until-broker-reconciled")
        self.assertEqual(payload["learningSummary"]["issueCount"], 2)
        self.assertEqual(payload["learningSummary"]["matchedTradeSize"], 15)
        self.assertEqual(payload["learningSummary"]["estimatedPnlDollars"], 1650.0)
        self.assertIn("operator-pnl-claim-needs-broker-proof", payload["learningSummary"]["issueIds"])
        self.assertIn("futures-demo-not-cleared", payload["algoExpansionBlockers"])
        self.assertIn("daily-plan", payload["premarketGate"]["hardRiskKinds"])
        self.assertEqual(payload["authorityBoundaries"]["agentsMayRouteOrders"], False)
        self.assertEqual(payload["aiScientistFit"]["fit"], "research-loop-only")
        self.assertFalse(payload["sourceAndPromotion"]["sourceHygieneCleared"])
        self.assertFalse(payload["sourceAndPromotion"]["canonicalSourceClean"])
        self.assertEqual(payload["sourceAndPromotion"]["sourceBlockerCount"], 1)

        markdown = render_markdown(payload)
        self.assertIn("Topstep Demo Observation Posture", markdown)
        self.assertIn("operator claims as context only", markdown)
        self.assertIn("Daily Learning Summary", markdown)
        self.assertIn("reportedLosingDayDollars", markdown)
        self.assertIn("eodDreaming", markdown)

    def test_canonical_source_clean_does_not_clear_sibling_source_blocker(self):
        payload = build_posture(
            goal={"blockedIds": ["source-hygiene-not-cleared"]},
            clearance={"status": "PASS", "allCommandsPassed": True},
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
            session_clearance={"machineChecksPassed": True, "readyForReadOnlyProofWindow": True},
            premarket={"command": "premarket-risk-brief"},
            topstep_learning={"decision": "demo-learning-visible-execution-locked"},
            runtime_architecture={"decision": "runtime-architecture-visible-execution-locked"},
            source_hygiene={
                "sourceClean": True,
                "sourceHygieneCleared": False,
                "sourceCleanBlockers": ["1 dirty sibling worktree(s) remain quarantine/selective-intake only"],
            },
            prediction_gate={"decision": "research-only-paper-promotion-blocked"},
        )

        self.assertTrue(payload["sourceAndPromotion"]["canonicalSourceClean"])
        self.assertFalse(payload["sourceAndPromotion"]["sourceHygieneCleared"])
        self.assertEqual(payload["sourceAndPromotion"]["sourceBlockerCount"], 1)
        self.assertFalse(payload["readyForAlgoDemoExpansion"])

    def test_source_hygiene_clears_when_goal_blocker_and_source_blockers_are_gone(self):
        payload = build_posture(
            goal={"blockedIds": ["futures-demo-not-cleared", "prediction-paper-not-cleared"]},
            clearance={"status": "PASS", "allCommandsPassed": True},
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
            session_clearance={"machineChecksPassed": True, "readyForReadOnlyProofWindow": True},
            premarket={"command": "premarket-risk-brief"},
            topstep_learning={"decision": "demo-learning-visible-execution-locked"},
            runtime_architecture={"decision": "runtime-architecture-visible-execution-locked"},
            source_hygiene={
                "sourceClean": True,
                "sourceHygieneCleared": False,
                "sourceCleanBlockers": [],
            },
            prediction_gate={"decision": "research-only-paper-promotion-blocked"},
        )

        self.assertTrue(payload["sourceAndPromotion"]["canonicalSourceClean"])
        self.assertTrue(payload["sourceAndPromotion"]["sourceHygieneCleared"])
        self.assertEqual(payload["sourceAndPromotion"]["sourceBlockerCount"], 0)
        self.assertNotIn("source-hygiene-not-cleared", payload["sourceAndPromotion"]["goalBlockedIds"])

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
