import unittest

from scripts.founder_quant_cto_metaprompt import build_metaprompt, render_markdown


class FounderQuantCtoMetapromptTest(unittest.TestCase):
    def test_metaprompt_is_ambitious_but_execution_locked(self):
        payload = build_metaprompt(
            goal={
                "blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"],
                "promptUncoveredIds": ["source-hygiene-not-faked"],
            },
            topstep_clearance={
                "operatorConfirmationRequired": True,
                "machineChecksPassed": True,
                "readyForReadOnlyProofWindow": False,
            },
            source_hygiene={"sourceHygieneCleared": False, "reviewBacklogCount": 7, "dirtyStatusCount": 23},
            prediction_gate={"readyForPaper": False, "blockedIds": ["forward-public-clob-capture"]},
            feeds={
                "summary": {
                    "wiredResearchFeeds": ["topstepx-projectx", "finnhub", "fred", "polygon"],
                    "optionalFutureResearch": ["databento"],
                }
            },
            strategy_framework={
                "decision": "research-only-strategy-framework-recovery-blocked",
                "walkforwardMatrix": {"status": "reject", "totalWindowsEvaluated": 24},
                "strategyFactory": {"walkforwardDeployable": False},
                "futuresNoEdgeMemory": {"matrixRejectionRecorded": True},
            },
        )

        self.assertEqual(payload["decision"], "active-founder-operating-prompt-execution-locked")
        self.assertIn("compounding capital", payload["primeDirective"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["safetyLocks"]["BILL_ENABLE_FUTURES_DEMO_EXECUTION"], "false")

        by_id = {row["id"]: row for row in payload["blockerQueue"]}
        self.assertEqual(by_id["topstep-session-safety"]["status"], "blocked")
        self.assertEqual(by_id["source-hygiene"]["status"], "blocked")
        self.assertEqual(by_id["prediction-paper"]["status"], "blocked")
        self.assertEqual(by_id["feed-posture"]["status"], "research-only")
        self.assertIn("databento", by_id["feed-posture"]["optionalFutureResearch"])
        self.assertIn("old Hermes/Codex note", payload["staleOverrideRule"])
        self.assertEqual("L0_RESEARCH_CONTROL_PLANE", payload["capitalDoctrine"]["currentMode"])
        self.assertEqual("ZERO_NEW_RISK", payload["capitalDoctrine"]["capitalAtRiskPermission"])
        self.assertEqual("blocked", payload["capitalDoctrine"]["sequence"][0]["status"])
        self.assertEqual("real-oos-validation-working-strategies-not-deployable", payload["strategyTruth"]["decision"])
        self.assertEqual(12, payload["strategyTruth"]["latestOperatorHandoff"]["afterScore"])
        self.assertEqual("reject", payload["strategyTruth"]["currentFramework"]["matrixStatus"])
        self.assertFalse(payload["strategyTruth"]["currentFramework"]["factoryDeployable"])
        self.assertTrue(any(item["id"] == "source-hygiene-not-cleared" for item in payload["killSwitches"]))
        self.assertIn("One-variable tests only", " ".join(payload["agentOperatingCommandments"]))
        self.assertIn("25-year OOS score drop", " ".join(payload["agentOperatingCommandments"]))
        self.assertIn("operatingFocus", payload)
        self.assertIn("one-week Topstep 100K demo observation", payload["operatingFocus"]["currentWeekMission"])
        self.assertIn("realized, broker-reconciled payouts", " ".join(payload["operatingFocus"]["highestProbabilityPath"]))
        focus_by_id = {row["id"]: row for row in payload["operatingFocus"]["activeResearchLanes"]}
        self.assertEqual("blocked", focus_by_id["futures-topstep-demo-observation"]["status"])
        self.assertEqual("blocked", focus_by_id["source-and-agent-coordination"]["status"])
        self.assertIn("Codex owns code", " ".join(payload["operatingFocus"]["agentPartnershipProtocol"]))
        self.assertIn("EOD", " ".join(payload["operatingFocus"]["dailyOperatingLoop"]))
        self.assertEqual(
            "two-lane-contract-active-execution-locked",
            payload["laneOperatingContract"]["decision"],
        )
        contract_by_id = {row["id"]: row for row in payload["laneOperatingContract"]["lanes"]}
        self.assertIn("Command Center UI/API", contract_by_id["command-lane"]["scope"])
        self.assertIn(
            "no command-center, goal-gate, broker, cron, or route-approval edits",
            contract_by_id["research-lane"]["forbidden"],
        )
        self.assertIn("futures-demo-not-cleared", contract_by_id["command-lane"]["currentBlockers"])
        self.assertIn("Every claim must name the artifact or test that proves it.", payload["laneOperatingContract"]["proofStandard"])

    def test_source_hygiene_queue_points_to_sibling_intake_when_canonical_source_is_clean(self):
        payload = build_metaprompt(
            goal={"blockedIds": ["source-hygiene-not-cleared"]},
            topstep_clearance={"operatorConfirmationRequired": False},
            source_hygiene={
                "sourceHygieneCleared": False,
                "sourceClean": True,
                "reviewBacklogCount": 0,
                "dirtyStatusCount": 0,
            },
            prediction_gate={"readyForPaper": False, "blockedIds": []},
            feeds={"summary": {"wiredResearchFeeds": ["topstepx-projectx"], "optionalFutureResearch": []}},
            strategy_framework={"walkforwardMatrix": {"status": "reject", "totalWindowsEvaluated": 24}},
        )

        by_id = {row["id"]: row for row in payload["blockerQueue"]}
        self.assertEqual("blocked", by_id["source-hygiene"]["status"])
        self.assertIn("Canonical source is clean", by_id["source-hygiene"]["why"])
        self.assertIn("sibling-worktree-intake", by_id["source-hygiene"]["nextCommand"])
        self.assertTrue(by_id["source-hygiene"]["evidence"]["siblingOnly"])
        self.assertEqual(0, by_id["source-hygiene"]["evidence"]["dirtyStatusCount"])
        self.assertEqual(0, by_id["source-hygiene"]["evidence"]["reviewBacklogCount"])

    def test_source_hygiene_queue_clears_when_goal_blocker_is_gone(self):
        payload = build_metaprompt(
            goal={"blockedIds": ["futures-demo-not-cleared", "prediction-paper-not-cleared"]},
            topstep_clearance={"operatorConfirmationRequired": False},
            source_hygiene={
                "sourceHygieneCleared": False,
                "sourceClean": True,
                "reviewBacklogCount": 0,
                "dirtyStatusCount": 0,
            },
            prediction_gate={"readyForPaper": False, "blockedIds": ["forward-public-clob-capture"]},
            feeds={"summary": {"wiredResearchFeeds": ["topstepx-projectx"], "optionalFutureResearch": []}},
            strategy_framework={"walkforwardMatrix": {"status": "reject", "totalWindowsEvaluated": 24}},
        )

        by_id = {row["id"]: row for row in payload["blockerQueue"]}
        self.assertEqual("clear", by_id["source-hygiene"]["status"])
        self.assertIn("Source hygiene is clear", by_id["source-hygiene"]["why"])
        self.assertFalse(by_id["source-hygiene"]["evidence"]["goalBlocked"])
        focus_by_id = {row["id"]: row for row in payload["operatingFocus"]["activeResearchLanes"]}
        self.assertEqual("clear", focus_by_id["source-and-agent-coordination"]["status"])

    def test_render_markdown_surfaces_stale_override_and_commands(self):
        payload = build_metaprompt(
            goal={"blockedIds": []},
            topstep_clearance={"operatorConfirmationRequired": True},
            source_hygiene={"sourceHygieneCleared": False},
            prediction_gate={"readyForPaper": False, "blockedIds": []},
            feeds={"summary": {"wiredResearchFeeds": ["topstepx-projectx"], "optionalFutureResearch": []}},
            strategy_framework={"walkforwardMatrix": {"status": "reject", "totalWindowsEvaluated": 24}},
        )

        markdown = render_markdown(payload)

        self.assertIn("Founder Quant CTO Metaprompt", markdown)
        self.assertIn("topstep-session-safety-clearance", markdown)
        self.assertIn("Stale Override Rule", markdown)
        self.assertIn("Capital Doctrine", markdown)
        self.assertIn("Kill Switches", markdown)
        self.assertIn("Strategy Truth", markdown)
        self.assertIn("Operating Focus", markdown)
        self.assertIn("Agent Partnership Protocol", markdown)
        self.assertIn("Daily Operating Loop", markdown)
        self.assertIn("Lane Operating Contract", markdown)
        self.assertIn("command-lane", markdown)
        self.assertIn("research-lane", markdown)
        self.assertIn("Score: `78`", markdown)
        self.assertIn("`12` real OOS", markdown)
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION", markdown)


if __name__ == "__main__":
    unittest.main()
