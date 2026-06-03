import unittest
from unittest.mock import patch

import command_center_server as server


class CommandCenterServerTests(unittest.TestCase):
    def test_source_clearance_runway_is_review_only_and_actionable(self):
        payload = server.get_source_clearance_runway({
            "decision": "source-hygiene-plan-research-only-execution-locked",
            "dirtyStatusCount": 12,
            "automaticCleanupAllowed": False,
            "safeAutoStage": False,
            "hardRules": ["No automatic staging, deletion, moves, or reverts."],
            "bundles": [
                {
                    "id": "execution-live-quarantine",
                    "title": "Execution/live quarantine",
                    "count": 3,
                    "writesOrders": False,
                    "touchesBroker": False,
                    "movesFunds": False,
                    "commands": ["npm run --silent bill:verify-execution-quarantine"],
                    "samplePaths": ["scripts/master_bridge.py"],
                    "blockers": ["execution remains locked"],
                }
            ],
        })

        self.assertEqual("source-hygiene-plan-research-only-execution-locked", payload["decision"])
        self.assertEqual(12, payload["dirtyStatusCount"])
        self.assertFalse(payload["automaticCleanupAllowed"])
        self.assertFalse(payload["safeAutoStage"])
        self.assertEqual(1, len(payload["runway"]))
        lane = payload["runway"][0]
        self.assertEqual("execution-live-quarantine", lane["id"])
        self.assertTrue(lane["safe"])
        self.assertEqual("npm run --silent bill:verify-execution-quarantine", lane["firstCommand"])
        self.assertIn("no auto staging", lane["clearanceRule"])

    def test_source_clearance_runway_prefers_canonical_tickets(self):
        payload = server.get_source_clearance_runway({
            "decision": "source-hygiene-plan-research-only-execution-locked",
            "dirtyStatusCount": 9,
            "sourceClearanceRunway": [
                {
                    "bundleId": "validated-research-scaffold",
                    "title": "Validated research scaffold",
                    "count": 4,
                    "decision": "manual-review-only",
                    "firstEvidenceCommand": "npm run --silent bill:source-packet-review",
                    "samplePaths": ["scripts/bill_source_hygiene_plan.py"],
                    "blockers": ["operator approval required before staging"],
                    "clearanceRule": "Review evidence and paths manually; no auto staging, cleanup, deletion, funding, routing, or broker writes.",
                    "writesOrders": False,
                    "touchesBroker": False,
                    "movesFunds": False,
                },
                {
                    "bundleId": "obsidian-ops-docs",
                    "title": "Obsidian and ops docs",
                    "count": 2,
                    "decision": "manual-review-only",
                    "firstEvidenceCommand": "npm run --silent bill:obsidian-sync",
                    "samplePaths": ["ops/n8n/bill-trading-day-premarket.workflow.json"],
                    "blockers": ["Obsidian memory is not broker truth"],
                    "clearanceRule": "Review evidence and paths manually; no auto staging, cleanup, deletion, funding, routing, or broker writes.",
                    "writesOrders": False,
                    "touchesBroker": False,
                    "movesFunds": False,
                }
            ],
            "bundles": [
                {
                    "id": "legacy-bundle",
                    "commands": ["legacy-command"],
                }
            ],
        })

        lane = payload["runway"][0]
        self.assertEqual("validated-research-scaffold", lane["id"])
        self.assertEqual("manual-review-only", lane["status"])
        self.assertEqual("npm run --silent bill:source-packet-review", lane["firstCommand"])
        self.assertIn("broker writes", lane["clearanceRule"])
        self.assertEqual("obsidian-ops-docs", payload["runway"][1]["id"])
        self.assertEqual("npm run --silent bill:obsidian-sync", payload["runway"][1]["firstCommand"])

    def test_blocker_actions_surface_prediction_gate_freshness(self):
        payloads = {
            "bill-goal-completion-audit.latest.json": {
                "decision": "continue-research-only-locked",
                "blockedIds": ["prediction-paper-not-cleared"],
            },
            "bill-source-hygiene-plan.latest.json": {"bundles": []},
            "bill-runtime-architecture-audit.latest.json": {"warnings": []},
            "bill-next-research-actions.latest.json": {"nextActions": []},
            "futures-data-requirements.latest.json": {"readyForDemoExpansion": False},
            "prediction-event-paper-promotion-gate.latest.json": {
                "readyForPaper": False,
                "blockedIds": ["forward-public-clob-capture", "manual-review-watch"],
            },
            "bill-fund-os-completion-audit.latest.json": {},
            "current-alpha-watch.latest.json": {},
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.get_topstep_data_plane", return_value={"blockers": [], "safeCommands": []}), \
                patch("command_center_server.freshness_for_state", return_value={
                    "status": "stale",
                    "ageSeconds": 86400,
                    "staleAfterSeconds": 21600,
                }):
            payload = server.get_blocker_actions()

        action = next(item for item in payload["priority"] if item["id"] == "prediction-paper-promotion")
        self.assertEqual("blocked", action["status"])
        self.assertEqual("npm run --silent bill:prediction-event-paper-promotion-gate", action["command"])
        self.assertEqual("npm run --silent bill:prediction-evidence-triage", action["nextCommand"])
        self.assertEqual("stale", action["freshness"]["status"])
        self.assertIn("Gate stale", action["why"])
        self.assertIn("forward-public-clob-capture", action["why"])

    def test_blocker_actions_prioritize_topstep_session_safety_pause(self):
        payloads = {
            "bill-goal-completion-audit.latest.json": {"decision": "continue-research-only-locked", "blockedIds": []},
            "bill-source-hygiene-plan.latest.json": {"bundles": []},
            "bill-runtime-architecture-audit.latest.json": {"warnings": []},
            "bill-next-research-actions.latest.json": {"nextActions": []},
            "futures-data-requirements.latest.json": {"readyForDemoExpansion": False},
            "prediction-event-paper-promotion-gate.latest.json": {"readyForPaper": False, "blockedIds": []},
            "bill-fund-os-completion-audit.latest.json": {},
            "current-alpha-watch.latest.json": {},
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.get_topstep_data_plane", return_value={
                    "blockers": ["topstep-readonly-archive-depth-thin", "topstep-session-safety-paused"],
                    "safeCommands": ["smoke", "archive"],
                    "archiveRthSessions": 2,
                    "sessionSafety": {
                        "pauseBrokerTouchingProofs": True,
                        "reason": "multiple sessions",
                    },
                }), \
                patch("command_center_server.freshness_for_state", return_value={
                    "status": "fresh",
                    "ageSeconds": 1,
                    "staleAfterSeconds": 21600,
                }):
            payload = server.get_blocker_actions()

        self.assertEqual("topstep-session-safety", payload["priority"][0]["id"])
        archive = next(item for item in payload["priority"] if item["id"] == "topstep-archive-depth")
        self.assertEqual("paused", archive["status"])
        self.assertFalse(archive["safe"])
        self.assertIn("Paused by Topstep session safety", archive["why"])

    def test_topstep_data_plane_surfaces_session_safety_pause(self):
        payloads = {
            "topstep-market-data-smoke.latest.json": {"brokerCurrentBarsProofPassed": True},
            "topstep-readonly-bar-archive.latest.json": {
                "status": "PASS",
                "nqArchiveRthSessionCount": 2,
                "minimumSessionsForResearch": 20,
                "symbols": {"NQ": {"rowCount": 1000}},
            },
            "topstep-broker-local-bar-parity.latest.json": {"brokerParityChecked": True, "brokerParityPassed": True},
            "topstep-realtime-proof.latest.json": {"status": "PASS", "readyForExecutionDataProof": True},
            "futures-data-requirements.latest.json": {"executionGradeRealtimeProofPassed": False},
            "topstep-100k-monitor.latest.json": {"broker_reconciliation": {"broker_flat": True, "open_positions": 0}},
            "topstepx-dashboard-screen-proof.latest.json": {},
            "topstep-session-safety.latest.json": {
                "pauseBrokerTouchingProofs": True,
                "reason": "multiple sessions",
                "safeUntil": "operator-confirms-topstep-session-warning-cleared",
            },
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.age_for_state", return_value=10):
            payload = server.get_topstep_data_plane()

        self.assertTrue(payload["sessionSafety"]["pauseBrokerTouchingProofs"])
        self.assertEqual("multiple sessions", payload["sessionSafety"]["reason"])
        self.assertIn("topstep-session-safety-paused", payload["blockers"])

    def test_goal_audit_endpoint_payload_is_read_only_completion_state(self):
        payloads = {
            "bill-goal-completion-audit.latest.json": {
                "decision": "continue-research-only-locked",
                "passCount": 25,
                "checkCount": 28,
                "blockedCount": 3,
                "blockedIds": [
                    "futures-demo-not-cleared",
                    "prediction-paper-not-cleared",
                    "source-hygiene-not-cleared",
                ],
                "promptUncoveredIds": ["source-hygiene-not-faked"],
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
            },
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json):
            payload = server.get_goal_audit()

        self.assertEqual("continue-research-only-locked", payload["decision"])
        self.assertEqual(25, payload["passCount"])
        self.assertEqual(28, payload["checkCount"])
        self.assertEqual(3, payload["blockedCount"])
        self.assertIn("source-hygiene-not-cleared", payload["blockedIds"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForLive"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])

    def test_risk_plane_exposes_source_hygiene_trajectory_counts(self):
        payloads = {
            "topstep-100k-monitor.latest.json": {},
            "bill-goal-completion-audit.latest.json": {},
            "bill-source-intake-manifest.latest.json": {
                "decision": "source-intake-visible-execution-locked",
                "classificationCounts": {
                    "requires-review": 74,
                    "validated-research-scaffold": 71,
                    "quarantine-execution-live": 17,
                },
                "reviewBacklogCount": 84,
                "sourceClean": False,
                "sourceIntakeVisible": True,
                "executionLiveDirtyCount": 38,
                "readyForExecution": False,
            },
            "bill-execution-intake-manifest.latest.json": {},
            "live-readiness.latest.json": {},
            "cron-state-validator.latest.json": {},
            "codex-automation-audit.latest.json": {},
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json):
            payload = server.get_risk_plane()

        self.assertEqual("source-intake-visible-execution-locked", payload["source"]["decision"])
        self.assertEqual(84, payload["source"]["reviewBacklogCount"])
        self.assertEqual(74, payload["source"]["classificationCounts"]["requires-review"])
        self.assertEqual(71, payload["source"]["classificationCounts"]["validated-research-scaffold"])
        self.assertEqual(17, payload["source"]["classificationCounts"]["quarantine-execution-live"])
        self.assertFalse(payload["source"]["sourceClean"])
        self.assertTrue(payload["source"]["sourceIntakeVisible"])
        self.assertFalse(payload["source"]["readyForExecution"])

    def test_signal_quality_plane_is_advisory_and_visible(self):
        payloads = {
            "signal-quality-advisor.latest.json": {
                "command": "signal-quality-advisor",
                "decision": "advisory-only; cannot approve, size, or route trades",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
                "overallRating": 6.9,
                "scoreParts": {"freshness": 10, "shadowSignalIntegrity": 7},
                "blockers": [],
                "warnings": ["proxy shadow input cannot confirm execution: dom_proxy"],
                "shadowSignalRows": [
                    {"name": "dom_proxy", "tradableSignal": False, "promotedForExecution": False},
                    {"name": "rolling_window", "tradableSignal": False, "promotedForExecution": False},
                ],
                "staleShadowSourceRows": [{"name": "rolling_window"}],
            },
            "signal-source-truth-audit.latest.json": {
                "command": "signal-source-truth-audit",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
                "issueCount": 2,
                "issues": [{"issue": "canonical-legacy-state-divergence"}],
            },
            "arbitration.latest.json": {
                "decision": "NO_TRADE",
                "direction": "FLAT",
                "conviction": "LOW",
                "active_signals": 0,
                "total_signals": 12,
                "weighted_dir": 0,
            },
            "brain-state.latest.json": {
                "fused_direction": 0.08,
                "active_signals": 21,
                "top_signals": ["ichimoku", "multitf_confirmation", "dom"],
                "readyForExecution": False,
            },
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.freshness_for_state", return_value={
                    "status": "fresh",
                    "ageSeconds": 12,
                    "staleAfterSeconds": 7200,
                }):
            payload = server.get_signal_quality_plane()

        self.assertTrue(payload["safeVisible"])
        self.assertEqual(6.9, payload["rating"])
        self.assertEqual(0, len(payload["blockers"]))
        self.assertEqual(1, payload["warningCount"])
        self.assertEqual(2, payload["shadowSignalCount"])
        self.assertEqual(1, payload["staleShadowSignalCount"])
        self.assertEqual(2, payload["sourceTruthIssueCount"])
        self.assertEqual(0, payload["promotedSourceIssueCount"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertEqual("NO_TRADE", payload["arbitration"]["decision"])

    def test_signal_quality_plane_blocks_visibility_on_promoted_research_source(self):
        payloads = {
            "signal-quality-advisor.latest.json": {
                "command": "signal-quality-advisor",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "overallRating": 8,
                "blockers": [],
                "warnings": [],
            },
            "signal-source-truth-audit.latest.json": {
                "command": "signal-source-truth-audit",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
                "issueCount": 1,
                "issues": [{"issue": "research-or-advisory-source-promoted"}],
            },
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.freshness_for_state", return_value={}):
            payload = server.get_signal_quality_plane()

        self.assertFalse(payload["safeVisible"])
        self.assertEqual(1, payload["promotedSourceIssueCount"])
        self.assertFalse(payload["readyForExecution"])

    def test_prediction_paper_plane_exposes_research_only_subblockers(self):
        payloads = {
            "prediction-event-paper-promotion-gate.latest.json": {
                "decision": "research-only-paper-promotion-blocked",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForPaper": False,
                "readyForPaperReview": False,
                "passCount": 1,
                "blockedCount": 2,
                "blockedIds": ["forward-public-clob-capture", "post-spread-clob-edge"],
                "operatorRead": "Forward CLOB capture can justify continued research only.",
                "nextAction": "Continue forward public CLOB capture.",
                "checklist": [
                    {
                        "id": "forward-public-clob-capture",
                        "status": "blocked",
                        "blocker": "no no-lookahead repriced complete event window exists yet",
                        "requirement": "Forward capture must include public CLOB quotes.",
                        "evidence": {"fillableLiveBookCount": 2},
                    },
                    {
                        "id": "research-safety-locks",
                        "status": "pass",
                    },
                ],
            },
            "prediction-evidence-triage.latest.json": {
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "nextTests": [
                    {
                        "id": "prediction-forward-event-clob-capture",
                        "track": "prediction-markets",
                        "oneVariable": "forward public CLOB capture window",
                        "commandHint": "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900",
                        "blockedBy": ["event-market-mapping-not-token-specific"],
                        "promotionRule": "research data only",
                    }
                ],
                "eventForwardCapture": {
                    "cycleDecision": "research-only-capture-cycle-dry-run-ready",
                    "forwardCaptureRequired": True,
                    "standingRecorderCommand": "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900",
                    "reviewLeadRecorderCommand": "npm run --silent bill:polymarket-clob-recorder -- --token-id 123",
                    "publicCaptureReviewLeadCount": 4,
                    "eventLagResearchWatchReady": False,
                    "eventLagReplayWatchReady": False,
                },
            },
            "prediction-event-capture-cycle.latest.json": {
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "completeWindowCount": 0,
                "repricedWindowCount": 0,
                "latestRecorder": {
                    "liveQualityDiagnostics": {"fillableLiveBookCount": 2},
                },
            },
            "prediction-event-lag-manual-review.latest.json": {
                "decision": "research-only-manual-review-no-paper",
                "decisionCounts": {"keep-research": 3},
                "forwardCaptureEvidencePresent": False,
                "blockers": ["no-window-clears-manual-review-for-paper-discussion"],
            },
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.freshness_for_state", return_value={
                    "status": "fresh",
                    "ageSeconds": 10,
                    "staleAfterSeconds": 21600,
                }):
            payload = server.get_prediction_paper_plane()

        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])
        self.assertTrue(payload["safetyOk"])
        self.assertEqual(2, payload["blockedCount"])
        self.assertEqual("forward-public-clob-capture", payload["rankedBlockers"][0]["id"])
        self.assertEqual("prediction-forward-event-clob-capture", payload["nextTest"]["id"])
        self.assertIn("polymarket-clob-recorder", payload["nextTest"]["commandHint"])
        self.assertEqual(2, payload["forwardCapture"]["fillableLiveBookCount"])
        self.assertEqual(0, payload["forwardCapture"]["completeWindowCount"])
        self.assertEqual("research-only-manual-review-no-paper", payload["manualReview"]["decision"])

    def test_founder_operating_state_blocks_trade_even_when_data_is_ready(self):
        with patch("command_center_server.parse_daily_control", return_value={
            "routeApproval": "BLOCKED",
            "brokerReconciliation": "UNKNOWN",
        }), patch("command_center_server.get_topstep_data_plane", return_value={
            "readyForExecutionData": True,
            "brokerFlat": True,
            "openPositions": 0,
            "archiveRthSessions": 1,
            "blockers": ["topstep-readonly-archive-depth-thin"],
        }), patch("command_center_server.get_market_data_plane", return_value={
            "readyForExecutionData": True,
            "source": "topstep_realtime",
        }), patch("command_center_server.get_risk_plane", return_value={
            "liveReadiness": {"deployableNow": False, "status": "blocked"},
            "source": {"readyForExecution": False, "executionLiveDirtyCount": 38},
            "topstep": {"brokerFlat": True, "openPositions": 0},
        }), patch("command_center_server.get_goal_audit", return_value={
            "blockedIds": [
                "futures-demo-not-cleared",
                "prediction-paper-not-cleared",
                "source-hygiene-not-cleared",
            ],
        }), patch("command_center_server.get_blocker_actions", return_value={
            "priority": [
                {
                    "id": "source-hygiene",
                    "title": "Reduce source hygiene backlog",
                    "safe": True,
                    "command": "npm run --silent bill:source-hygiene-plan",
                }
            ],
        }):
            payload = server.get_founder_operating_state()

        self.assertEqual("BLOCKED", payload["tradePermission"])
        self.assertEqual("ALLOWED", payload["researchPermission"])
        self.assertIn("daily-route", payload["blockingGateIds"])
        self.assertIn("model-validation", payload["blockingGateIds"])
        self.assertIn("source-hygiene", payload["blockingGateIds"])
        self.assertEqual("source-hygiene", payload["nextSafeAction"]["id"])
        by_gate = {gate["id"]: gate for gate in payload["gates"]}
        self.assertEqual("pass", by_gate["execution-data"]["status"])
        self.assertEqual("blocked", by_gate["daily-route"]["status"])
        self.assertIn("not sufficient", payload["operatorRead"])

    def test_market_data_plane_marks_alpaca_as_sandbox_not_futures_truth(self):
        payloads = {
            "realtime-data-preflight.latest.json": {"readyForExecutionData": True, "decision": "execution-data-ready"},
            "realtime-quote.latest.json": {"source": "topstep_realtime", "execution_grade": True},
            "data-freshness-gate.latest.json": {"verdict": "PASS"},
            "databento-realtime-smoke.latest.json": {"status": "NO_QUOTES"},
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.state_mtime", return_value=(None, "/tmp/state")), \
                patch("command_center_server.get_topstep_data_plane", return_value={
                    "status": "PASS",
                    "currentBarsProofPassed": True,
                    "brokerParityPassed": True,
                    "readyForFiveMinuteResearch": True,
                }):
            payload = server.get_market_data_plane()

        self.assertEqual("topstepx_projectx", payload["preferredSource"])
        self.assertEqual("optional-secondary-depth-research", payload["databentoRole"])
        self.assertEqual("available-via-plugin-manifest", payload["alpacaSandbox"]["status"])
        self.assertEqual("equities-options-crypto-research-and-paper-sandbox", payload["alpacaSandbox"]["role"])
        self.assertFalse(payload["alpacaSandbox"]["executionAuthority"])
        self.assertIn("TopstepX/ProjectX", payload["recommendedPath"])
        self.assertIn("Alpaca", payload["recommendedPath"])


if __name__ == "__main__":
    unittest.main()
