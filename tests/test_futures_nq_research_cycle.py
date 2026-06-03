import unittest

from scripts.futures_nq_research_cycle import (
    HERMES,
    build_cycle,
    command_text,
    default_markdown_path,
    planned_steps,
    render_markdown,
)


class FuturesNqResearchCycleTest(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^futures-nq-research-cycle-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T08:21:22+00:00",
            "historical": {},
            "current": {},
            "steps": [],
            "blockers": [],
            "limitations": [],
        })

        self.assertIn("# Futures NQ Research Cycle - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_dry_run_cycle_is_locked_and_surfaces_current_blockers(self):
        payload = build_cycle(
            coverage={
                "decision": "research-only-historical-nq-source-ready",
                "blockers": ["no-seagate-nq-source-overlaps-current-local-csv-bars"],
                "usableHistoricalOosCount": 3,
                "preferredPromotionDepthCount": 1,
                "currentLocalCsvParityCheckedCount": 3,
                "currentLocalCsvParityClearedCount": 0,
                "bestHistoricalOosCandidate": {
                    "datasetId": "seagate_nq_15m",
                    "currentLocalCsvParity": {
                        "checked": True,
                        "ok": False,
                        "overlapRows": 0,
                        "reason": "no-overlapping-bars-with-current-local-csv",
                        "featureRange": {"min": "2025-06-30", "max": "2025-10-10", "rows": 6739},
                        "localCsvRange": {"min": "2026-03-19", "max": "2026-05-29", "rows": 4535},
                    },
                },
            },
            replay={"decision": "research-only-historical-session-replay-watch", "tradeCount": 70},
            walkforward={
                "decision": "research-only-historical-session-walkforward-watch",
                "foldCount": 7,
                "positiveFoldShare": 0.714286,
                "worstFoldNetR": -2.115559,
            },
            cost_stress={
                "decision": "research-only-historical-session-cost-stress-watch",
                "survivingCaseCount": 4,
                "caseCount": 4,
            },
            current_parity={
                "decision": "research-only-current-local-parity-ready",
                "cleanLocalResearchPairCount": 1,
                "brokerParityChecked": False,
            },
            session_structure={"decision": "research-only-insufficient-history-for-oos", "sessionCount": 4},
            data_requirements={"decision": "research-only-data-requirements-not-cleared", "blockedCount": 3},
            broker_parity_plan={
                "decision": "research-only-futures-broker-parity-not-cleared",
                "missingProofs": ["broker-reconciled-current-nq-bars"],
            },
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "obsidian": {"dailyRouteApproval": "BLOCKED"},
                "gates": {"realtimeDataReady": False, "realtimeDataDecision": "block-execution-data"},
            },
            local_5m_replay={
                "decision": "research-only-historical-session-replay-watch",
                "tradeCount": 34,
                "oosStats": {"trades": 14, "netR": 4.036832, "profitFactor": 3.20896},
            },
            local_5m_walkforward={
                "decision": "research-only-historical-session-walkforward-blocked",
                "foldCount": 3,
                "positiveFoldShare": 1.0,
                "worstFoldNetR": 2.053774,
                "blockers": ["too-few-complete-walkforward-folds", "too-few-trades-for-walkforward-folds"],
            },
            local_5m_cost_stress={
                "decision": "research-only-historical-session-cost-stress-watch",
                "survivingCaseCount": 4,
            },
        )

        self.assertEqual(payload["decision"], "research-only-futures-cycle-dry-run-ready")
        self.assertEqual(payload["mode"], "dry-run")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertEqual(payload["historical"]["bestCandidate"], "seagate_nq_15m")
        self.assertEqual(payload["historical"]["currentLocalCsvParityCheckedCount"], 3)
        self.assertEqual(payload["historical"]["currentLocalCsvParityClearedCount"], 0)
        self.assertFalse(payload["historical"]["currentParitySummary"]["cleared"])
        self.assertEqual(payload["historical"]["currentParitySummary"]["overlapRows"], 0)
        self.assertIn("research/OOS only", payload["historical"]["currentParitySummary"]["operatorRead"])
        local_5m = payload["historical"]["local5mOneVariable"]
        self.assertEqual(local_5m["tradeCount"], 34)
        self.assertEqual(local_5m["oosStats"]["netR"], 4.036832)
        self.assertEqual(local_5m["foldCount"], 3)
        self.assertIn("too-few-complete-walkforward-folds", local_5m["walkforwardBlockers"])
        self.assertFalse(local_5m["readyForDemoExpansion"])
        self.assertTrue(local_5m["researchOnly"])
        self.assertIn("blocked by walk-forward depth", local_5m["promotionRead"])
        self.assertIn("historical-current-local-csv-parity-not-cleared", payload["blockers"])
        self.assertIn("futures-data-requirements-not-cleared", payload["blockers"])
        self.assertIn("futures-broker-parity-proof-missing", payload["blockers"])
        self.assertIn("broker-parity-not-checked", payload["blockers"])
        self.assertIn("execution-grade-realtime-not-cleared", payload["blockers"])
        self.assertIn("daily-route-approval-not-allow", payload["blockers"])
        self.assertIn("dry-run-only; pass --run-local-research to refresh local futures evidence", payload["blockers"])
        self.assertTrue(all(step["status"] == "skipped-dry-run" for step in payload["steps"]))
        self.assertEqual(payload["safeEnv"]["BILL_ENABLE_FUTURES_DEMO_EXECUTION"], "false")
        self.assertEqual(payload["safeEnv"]["RH_TOPSTEP_READ_ONLY"], "true")
        self.assertEqual(payload["safeEnv"]["RH_LIVE_EXECUTION_ENABLED"], "false")

    def test_run_local_research_still_blocked_when_realtime_or_broker_missing(self):
        payload = build_cycle(
            coverage={"bestHistoricalOosCandidate": {"datasetId": "seagate_nq_15m"}},
            replay={},
            walkforward={},
            cost_stress={},
            current_parity={"brokerParityChecked": False},
            session_structure={},
            data_requirements={"decision": "research-only-data-requirements-cleared", "blockedCount": 0},
            broker_parity_plan={"decision": "research-only-futures-broker-parity-proof-plan-clear"},
            handoff={
                "obsidian": {"dailyRouteApproval": "BLOCKED"},
                "gates": {"realtimeDataReady": False},
            },
            run_local_research=True,
            ran_steps=[{"id": "check-current-local-parity", "status": "pass", "command": "npm run ..."}],
        )

        self.assertEqual(payload["decision"], "research-only-futures-cycle-ran-still-blocked")
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertIn("broker-parity-not-checked", payload["blockers"])
        self.assertIn("execution-grade-realtime-not-cleared", payload["blockers"])
        self.assertIn("daily-route-approval-not-allow", payload["blockers"])

    def test_topstep_broker_local_parity_clears_broker_specific_blockers(self):
        payload = build_cycle(
            coverage={"bestHistoricalOosCandidate": {"datasetId": "seagate_nq_15m"}},
            replay={},
            walkforward={},
            cost_stress={},
            current_parity={"brokerParityChecked": False},
            session_structure={},
            data_requirements={"decision": "research-only-data-requirements-not-cleared", "blockedCount": 2},
            broker_parity_plan={
                "decision": "research-only-futures-broker-parity-not-cleared",
                "missingProofs": [
                    "current-session-depth-from-broker-relevant-source",
                    "open-session-execution-grade-realtime-proof",
                ],
                "current": {
                    "topstepCurrentBarsProofPassed": True,
                    "topstepBrokerLocalBarParityPassed": True,
                },
            },
            handoff={
                "obsidian": {"dailyRouteApproval": "BLOCKED"},
                "gates": {"realtimeDataReady": False},
            },
            run_local_research=True,
        )

        self.assertNotIn("futures-broker-parity-proof-missing", payload["blockers"])
        self.assertNotIn("broker-parity-not-checked", payload["blockers"])
        self.assertTrue(payload["current"]["brokerParityCheckedFromTopstepPlan"])
        self.assertTrue(payload["current"]["topstepCurrentBarsProofPassed"])
        self.assertTrue(payload["current"]["topstepBrokerLocalBarParityPassed"])
        self.assertIn("futures-data-requirements-not-cleared", payload["blockers"])
        self.assertIn("execution-grade-realtime-not-cleared", payload["blockers"])
        self.assertIn("daily-route-approval-not-allow", payload["blockers"])

    def test_topstep_realtime_proof_clears_stale_execution_grade_blocker(self):
        payload = build_cycle(
            coverage={"bestHistoricalOosCandidate": {"datasetId": "seagate_nq_15m"}},
            replay={},
            walkforward={},
            cost_stress={},
            current_parity={"brokerParityChecked": False},
            session_structure={},
            data_requirements={
                "decision": "research-only-data-requirements-not-cleared",
                "blockedCount": 1,
                "executionGradeRealtimeProofPassed": True,
            },
            broker_parity_plan={
                "decision": "research-only-futures-broker-parity-not-cleared",
                "missingProofs": ["current-session-depth-from-broker-relevant-source"],
                "current": {
                    "topstepCurrentBarsProofPassed": True,
                    "topstepBrokerLocalBarParityPassed": True,
                    "topstepRealtimeReadyForExecutionDataProof": True,
                },
            },
            handoff={
                "obsidian": {"dailyRouteApproval": "BLOCKED"},
                "gates": {"realtimeDataReady": False},
            },
            run_local_research=True,
        )

        self.assertNotIn("execution-grade-realtime-not-cleared", payload["blockers"])
        self.assertIn("futures-data-requirements-not-cleared", payload["blockers"])
        self.assertIn("daily-route-approval-not-allow", payload["blockers"])
        self.assertTrue(payload["current"]["topstepRealtimeProofPassed"])

    def test_planned_steps_are_research_commands(self):
        steps = planned_steps()
        ids = [step["id"] for step in steps]
        self.assertIn("audit-historical-coverage", ids)
        self.assertIn("refresh-broker-parity-plan", ids)
        self.assertEqual(
            next(step for step in steps if step["id"] == "refresh-clearance-evidence")["command"],
            "npm run --silent bill:clearance-evidence-fast",
        )
        self.assertIn("sync-obsidian-memory", ids)
        self.assertTrue(all(not step["writesOrders"] for step in steps))
        self.assertTrue(all(not step["touchesBroker"] for step in steps))
        command = command_text(["npm", "run", "--silent", "bill:futures-nq-research-cycle"])
        self.assertEqual(command, "npm run --silent bill:futures-nq-research-cycle")


if __name__ == "__main__":
    unittest.main()
