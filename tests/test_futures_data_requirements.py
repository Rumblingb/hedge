import unittest

from scripts.futures_data_requirements import VAULT, build_requirements, default_markdown_path, render_markdown


class FuturesDataRequirementsTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^futures-data-requirements-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "passCount": 0,
            "blockedCount": 0,
            "requirements": [],
        })

        self.assertIn("# Futures Data Requirements - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_requirements_block_demo_when_current_parity_and_depth_missing(self):
        payload = build_requirements(
            external_audit={
                "nqLocalParity": {"ok": False, "overlapRows": 0, "reason": "date-range-mismatch-or-no-overlap"},
                "nqSourceParity": {"ok": True, "checks": [{"datasetId": "nq_futures_1m", "ok": True}]},
            },
            session_audit={"sessionCount": 4, "decision": "research-only-insufficient-history-for-oos"},
            data_freshness={"verdict": "STALE", "action": "block_all_trades"},
            live_readiness={"blockers": ["walk-forward gate is not deployable"]},
        )

        by_id = {item["id"]: item for item in payload["requirements"]}

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertEqual(payload["decision"], "research-only-data-requirements-not-cleared")
        self.assertIn("futures-execution-grade-realtime", payload["blockedRequirementIds"])
        self.assertIn("nq-source-build-parity", payload["passedRequirementIds"])
        self.assertFalse(payload["brokerL1BarsProofPassed"])
        self.assertFalse(payload["executionGradeRealtimeProofPassed"])
        self.assertEqual(by_id["nq-current-internal-local-parity"]["status"], "blocked")
        self.assertEqual(by_id["topstep-current-market-data-bars"]["status"], "blocked")
        self.assertEqual(by_id["nq-source-build-parity"]["status"], "pass")
        self.assertEqual(by_id["nq-current-local-or-broker-parity"]["status"], "blocked")
        self.assertEqual(by_id["nq-historical-session-oos-depth"]["status"], "blocked")
        self.assertEqual(by_id["nq-current-session-depth-for-demo"]["status"], "blocked")
        self.assertEqual(by_id["futures-execution-grade-realtime"]["status"], "blocked")

    def test_requirements_can_clear_research_data_without_approving_demo(self):
        payload = build_requirements(
            external_audit={
                "nqLocalParity": {"ok": True, "overlapRows": 500},
                "nqSourceParity": {"ok": True, "checks": []},
            },
            session_audit={"sessionCount": 65, "decision": "research-only-session-smoke-ready"},
            data_freshness={"verdict": "PASS", "action": "allow_trades"},
            live_readiness={"blockers": []},
            current_data_parity={
                "decision": "research-only-current-local-parity-ready",
                "cleanLocalResearchPairCount": 1,
                "bestCurrentLocalResearchPair": {"pairId": "nq-5m-60d-vs-all-6markets-5m-60d"},
                "brokerParityChecked": True,
            },
            historical_coverage={
                "decision": "research-only-historical-nq-source-ready",
                "bestHistoricalOosCandidate": {
                    "datasetId": "seagate_nq_15m",
                    "sessionCount": 70,
                    "usableForHistoricalOosResearch": True,
                    "preferredForPromotionReview": True,
                    "sourceParity": {"ok": True},
                },
            },
            historical_replay={
                "decision": "research-only-historical-session-replay-watch",
                "oosStats": {"trades": 28, "netR": 4.9, "profitFactor": 1.4},
            },
            historical_walkforward={
                "decision": "research-only-historical-session-walkforward-watch",
                "foldCount": 7,
                "positiveFoldShare": 0.71,
            },
            historical_cost_stress={
                "decision": "research-only-historical-session-cost-stress-watch",
                "survivingCaseCount": 4,
                "caseCount": 4,
            },
            topstep_market_data_smoke={
                "status": "BARS_OK",
                "brokerCurrentBarsProofPassed": True,
                "symbols": {"NQ": {"status": "BARS_OK"}, "MNQ": {"status": "BARS_OK"}},
                "brokerTouchMode": "read-only-market-data",
            },
            topstep_broker_local_bar_parity={
                "status": "PASS",
                "brokerParityChecked": True,
                "brokerParityPassed": True,
            },
            topstep_readonly_bar_archive={
                "status": "PASS",
                "nqArchiveRthSessionCount": 65,
                "nqArchiveSessionCount": 65,
                "brokerBarArchiveReadyForResearchDepth": True,
                "brokerTouchMode": "read-only-market-data",
            },
            topstep_realtime_proof={
                "status": "PASS",
                "readyForExecutionDataProof": True,
                "writesRealtimeQuoteState": False,
                "symbols": {"NQ": {"quotes": 2}, "MNQ": {"quotes": 2}},
            },
        )

        by_id = {item["id"]: item for item in payload["requirements"]}
        self.assertEqual(payload["blockedCount"], 0)
        self.assertEqual(payload["decision"], "research-only-data-requirements-cleared")
        self.assertEqual(payload["blockedRequirementIds"], [])
        self.assertTrue(payload["brokerL1BarsProofPassed"])
        self.assertTrue(payload["topstepRealtimeProofPassed"])
        self.assertTrue(payload["executionGradeRealtimeProofPassed"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(by_id["nq-current-internal-local-parity"]["status"], "pass")
        self.assertEqual(by_id["topstep-current-market-data-bars"]["status"], "pass")
        self.assertEqual(by_id["topstep-readonly-bar-archive"]["status"], "pass")
        self.assertEqual(by_id["nq-current-local-or-broker-parity"]["status"], "pass")
        self.assertFalse(payload["readyForDemoExpansion"])

    def test_historical_oos_can_pass_while_current_demo_depth_stays_blocked(self):
        payload = build_requirements(
            external_audit={
                "nqLocalParity": {"ok": False, "overlapRows": 0, "reason": "date-range-mismatch-or-no-overlap"},
                "nqSourceParity": {"ok": True, "checks": []},
            },
            session_audit={"sessionCount": 4, "decision": "research-only-insufficient-history-for-oos"},
            data_freshness={"verdict": "STALE", "action": "block_all_trades"},
            live_readiness={"blockers": []},
            current_data_parity={
                "decision": "research-only-current-local-parity-ready",
                "cleanLocalResearchPairCount": 1,
                "bestCurrentLocalResearchPair": {"pairId": "nq-5m-60d-vs-all-6markets-5m-60d"},
                "brokerParityChecked": False,
            },
            historical_coverage={
                "decision": "research-only-historical-nq-source-ready",
                "bestHistoricalOosCandidate": {
                    "datasetId": "seagate_nq_15m",
                    "sessionCount": 70,
                    "usableForHistoricalOosResearch": True,
                    "preferredForPromotionReview": True,
                    "sourceParity": {"ok": True},
                },
            },
            historical_replay={
                "decision": "research-only-historical-session-replay-watch",
                "oosStats": {"trades": 28, "netR": 4.9, "profitFactor": 1.4},
            },
            historical_walkforward={
                "decision": "research-only-historical-session-walkforward-watch",
                "foldCount": 7,
                "positiveFoldShare": 0.71,
            },
            historical_cost_stress={
                "decision": "research-only-historical-session-cost-stress-watch",
                "survivingCaseCount": 4,
                "caseCount": 4,
            },
        )

        by_id = {item["id"]: item for item in payload["requirements"]}

        self.assertEqual(by_id["nq-historical-session-oos-depth"]["status"], "pass")
        self.assertEqual(by_id["topstep-current-market-data-bars"]["status"], "blocked")
        self.assertEqual(by_id["nq-current-session-depth-for-demo"]["status"], "blocked")
        self.assertEqual(by_id["nq-current-local-or-broker-parity"]["status"], "blocked")
        self.assertEqual(by_id["futures-execution-grade-realtime"]["status"], "blocked")
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])

    def test_top_level_summary_distinguishes_broker_l1_from_execution_grade_realtime(self):
        payload = build_requirements(
            external_audit={
                "nqLocalParity": {"ok": True, "overlapRows": 500},
                "nqSourceParity": {"ok": True, "checks": []},
            },
            session_audit={"sessionCount": 4, "decision": "research-only-insufficient-history-for-oos"},
            data_freshness={"verdict": "STALE", "action": "block_all_trades"},
            live_readiness={"blockers": []},
            current_data_parity={
                "decision": "research-only-current-local-parity-ready",
                "cleanLocalResearchPairCount": 1,
                "bestCurrentLocalResearchPair": {"pairId": "nq-1m-5d-vs-all-6markets-1m-5d"},
            },
            topstep_market_data_smoke={
                "status": "BARS_OK",
                "brokerCurrentBarsProofPassed": True,
                "symbols": {"NQ": {"status": "BARS_OK"}, "MNQ": {"status": "BARS_OK"}},
                "brokerTouchMode": "read-only-market-data",
            },
            topstep_broker_local_bar_parity={
                "status": "PASS",
                "brokerParityChecked": True,
                "brokerParityPassed": True,
            },
            topstep_realtime_proof={
                "status": "PASS",
                "readyForExecutionDataProof": True,
                "writesRealtimeQuoteState": False,
                "symbols": {"NQ": {"quotes": 2}, "MNQ": {"quotes": 2}},
            },
        )

        self.assertTrue(payload["brokerL1BarsProofPassed"])
        self.assertTrue(payload["topstepRealtimeProofPassed"])
        self.assertFalse(payload["executionGradeRealtimeProofPassed"])
        self.assertIn("futures-execution-grade-realtime", payload["blockedRequirementIds"])
        self.assertFalse(payload["readyForExecution"])

    def test_topstep_direct_archive_can_replace_stale_yahoo_overlap_for_current_source(self):
        payload = build_requirements(
            external_audit={
                "nqLocalParity": {"ok": False, "overlapRows": 0, "reason": "date-range-mismatch-or-no-overlap"},
                "nqSourceParity": {"ok": True, "checks": []},
            },
            session_audit={"sessionCount": 1, "decision": "research-only-insufficient-history-for-oos"},
            data_freshness={"verdict": "STALE", "action": "block_all_trades"},
            live_readiness={"blockers": []},
            current_data_parity={
                "decision": "research-only-current-local-parity-ready",
                "cleanLocalResearchPairCount": 1,
                "bestCurrentLocalResearchPair": {"pairId": "nq-1m-5d-vs-all-6markets-1m-5d"},
            },
            topstep_market_data_smoke={
                "status": "BARS_OK",
                "brokerCurrentBarsProofPassed": True,
                "symbols": {"NQ": {"status": "BARS_OK"}, "MNQ": {"status": "BARS_OK"}},
                "brokerTouchMode": "read-only-market-data",
            },
            topstep_broker_local_bar_parity={
                "status": "BLOCKED",
                "brokerParityChecked": True,
                "brokerParityPassed": False,
            },
            topstep_readonly_bar_archive={
                "status": "PASS",
                "nqArchiveRthSessionCount": 1,
                "nqArchiveSessionCount": 1,
                "brokerBarArchiveReadyForResearchDepth": False,
                "brokerTouchMode": "read-only-market-data",
                "symbols": {"NQ": {"rowCount": 464}},
            },
        )

        by_id = {item["id"]: item for item in payload["requirements"]}

        self.assertEqual(by_id["nq-current-local-or-broker-parity"]["status"], "pass")
        self.assertTrue(by_id["nq-current-local-or-broker-parity"]["current"]["topstepDirectBrokerSourceOk"])
        self.assertEqual(by_id["nq-current-session-depth-for-demo"]["status"], "blocked")
        self.assertIn("nq-current-session-depth-for-demo", payload["blockedRequirementIds"])
        self.assertIn("futures-execution-grade-realtime", payload["blockedRequirementIds"])

    def test_topstep_archive_can_satisfy_current_bars_when_smoke_is_safety_blocked(self):
        payload = build_requirements(
            external_audit={
                "nqLocalParity": {"ok": False, "overlapRows": 0, "reason": "date-range-mismatch-or-no-overlap"},
                "nqSourceParity": {"ok": True, "checks": []},
            },
            session_audit={"sessionCount": 3, "decision": "research-only-insufficient-history-for-oos"},
            data_freshness={"verdict": "PASS", "action": "allow_trades"},
            live_readiness={"blockers": []},
            current_data_parity={
                "decision": "research-only-current-local-parity-ready",
                "cleanLocalResearchPairCount": 1,
                "bestCurrentLocalResearchPair": {"pairId": "nq-1m-5d-vs-all-6markets-1m-5d"},
            },
            topstep_market_data_smoke={
                "status": "BLOCKED_BY_SAFETY_ENV",
                "brokerCurrentBarsProofPassed": False,
            },
            topstep_readonly_bar_archive={
                "status": "PASS",
                "nqArchiveRthSessionCount": 3,
                "nqArchiveSessionCount": 3,
                "brokerBarArchiveReadyForResearchDepth": False,
                "brokerTouchMode": "read-only-market-data",
                "symbols": {"NQ": {"rowCount": 1440}, "MNQ": {"rowCount": 1440}},
            },
            topstep_realtime_proof={
                "status": "PASS",
                "readyForExecutionDataProof": True,
                "symbols": {"NQ": {"quotes": 100}, "MNQ": {"quotes": 100}},
            },
        )

        by_id = {item["id"]: item for item in payload["requirements"]}

        self.assertEqual(by_id["topstep-current-market-data-bars"]["status"], "pass")
        self.assertEqual(
            by_id["topstep-current-market-data-bars"]["current"]["proofSource"],
            "topstep-readonly-bar-archive",
        )
        self.assertEqual(by_id["nq-current-local-or-broker-parity"]["status"], "pass")
        self.assertEqual(by_id["nq-current-session-depth-for-demo"]["status"], "blocked")
        self.assertNotIn("topstep-current-market-data-bars", payload["blockedRequirementIds"])
        self.assertIn("nq-current-session-depth-for-demo", payload["blockedRequirementIds"])


if __name__ == "__main__":
    unittest.main()
