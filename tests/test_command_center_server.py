import time
import unittest
import threading
import urllib.error
import urllib.request
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import command_center_server as server


class CommandCenterServerTests(unittest.TestCase):
    def test_command_center_server_is_threaded(self):
        self.assertTrue(issubclass(server.CommandCenterHTTPServer, ThreadingHTTPServer))
        self.assertTrue(server.CommandCenterHTTPServer.daemon_threads)

    def test_api_handler_returns_json_error_when_endpoint_raises(self):
        httpd = server.CommandCenterHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_address[1]

        try:
            with patch("command_center_server.get_full_state", side_effect=RuntimeError("boom")):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/full", timeout=2)
                try:
                    body = ctx.exception.read().decode()
                finally:
                    ctx.exception.close()
        finally:
            httpd.shutdown()
            thread.join(timeout=2)
            httpd.server_close()

        self.assertEqual(500, ctx.exception.code)
        self.assertIn("command-center-handler-exception", body)
        self.assertIn("\"executionLocked\": true", body)

    def test_daily_control_decision_cannot_be_armed_when_control_lines_block(self):
        daily = "\n".join([
            "**Decision:** Demo routing is armed; verify broker and daily plan before any order.",
            "",
            "BILL_ROUTE_APPROVAL: BLOCKED",
            "",
            "BROKER_RECONCILIATION: UNKNOWN",
        ])
        hub = "**Mode:** research / shadow\n\n**Execution:** locked"

        with patch("command_center_server.daily_plan_path", return_value="/tmp/daily.md"), \
                patch("command_center_server.load_text", side_effect=[daily, hub]):
            payload = server.parse_daily_control()

        self.assertEqual("No new Bill/Hermes orders approved.", payload["decision"])
        self.assertEqual("Demo routing is armed; verify broker and daily plan before any order.", payload["rawDecision"])
        self.assertEqual("BLOCKED", payload["routeApproval"])
        self.assertEqual("UNKNOWN", payload["brokerReconciliation"])

    def test_daily_control_fails_closed_when_topstep_session_safety_is_unconfirmed(self):
        daily = "\n".join([
            "**Decision:** Demo routing is armed by env and daily controls.",
            "",
            "BILL_ROUTE_APPROVAL: APPROVED",
            "",
            "BROKER_RECONCILIATION: GREEN",
        ])
        hub = "**Mode:** research / shadow\n\n**Execution:** locked"
        safety = {
            "pauseBrokerTouchingProofs": True,
            "topstepMultipleSessionsDetected": True,
            "operatorConfirmedTopstepWarningCleared": False,
            "reason": "operator confirmation required",
        }

        with patch("command_center_server.daily_plan_path", return_value="/tmp/daily.md"), \
                patch("command_center_server.load_text", side_effect=[daily, hub]), \
                patch("command_center_server.state_json", return_value=(safety, "/tmp/safety.json")):
            payload = server.parse_daily_control()

        self.assertEqual("BLOCKED", payload["routeApproval"])
        self.assertEqual("APPROVED", payload["rawRouteApproval"])
        self.assertTrue(payload["sessionSafetyBlocked"])
        self.assertEqual("No new Bill/Hermes orders approved.", payload["decision"])

    def test_fund_ladder_does_not_label_nq_as_live(self):
        payload = server.get_fund_ladder()
        nq = next(row for row in payload["instruments"] if row["symbol"] == "NQ")

        self.assertEqual("demo", nq["stage"])
        self.assertNotIn("NQ live", payload["note"])
        self.assertIn("demo-gated", payload["research_scoreboard"]["confirmed_structural"][0])

    def test_execution_plane_marks_old_submissions_as_history(self):
        now = 1_800_000_000

        def fake_state_json(name):
            if name == "topstep-demo-submission.latest.json":
                return {"submitted": True, "ts": "2026-06-11T17:30:29+00:00", "signal": "short@test"}, "/tmp/sub.json"
            return {}, "/tmp/state.json"

        def fake_state_mtime(name):
            if name == "topstep-demo-submission.latest.json":
                return now - 7200, "/tmp/sub.json"
            return None, "/tmp/state.json"

        with patch("command_center_server.time.time", return_value=now), \
                patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.state_mtime", side_effect=fake_state_mtime), \
                patch("command_center_server.load_json", return_value={}):
            payload = server.get_execution_plane()

        self.assertTrue(payload["last_submission"]["submitted"])
        self.assertTrue(payload["last_submission"]["stale"])
        self.assertEqual("stale-history", payload["last_submission"]["status"])
        self.assertEqual(7200, payload["last_submission"]["age_s"])
        self.assertTrue(payload["master_signal"]["stale"])

    def test_execution_plane_surfaces_bounded_testbed_challenge_cycle(self):
        def fake_state_json(name):
            payloads = {
                "topstep-broker-reconciliation.latest.json": {"account_id": 23536817, "broker_flat": True},
                "trading-day-cycle.premarket.latest.json": {
                    "status": "READY",
                    "context": {"lane": {"balance": 47482.94}},
                },
                "trading-day-cycle.market.latest.json": {
                    "status": "PASS",
                    "steps": [
                        {"id": "red-folder-calendar-refresh", "stdoutTail": '{"events": []}'},
                        {
                            "id": "testbed-b-challenge-canary",
                            "stdoutTail": '{"status":"WAIT","reason":"NQ ORB canary window is 09:48-11:30 ET"}',
                        },
                    ],
                },
                "topstep-realtime-proof.latest.json": {
                    "status": "PASS",
                    "readyForExecutionDataProof": True,
                    "symbols": {"NQ": {"lastQuoteSample": {"bestAsk": 30000.25}}},
                },
            }
            return payloads.get(name, {}), "/tmp/state.json"

        policy = {
            "account_name": "50KTC-V2-DLL-507159-71363980",
            "risk_budget_usd": 1000,
            "gross_target_goal_usd": 1500,
            "target_rr": 1.5,
            "max_micros": 50,
            "max_orders_per_trading_day": 1,
            "window": "09:48-11:30 America/New_York",
            "simulated_only": True,
            "live_money_allowed": False,
        }
        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.state_mtime", return_value=(1_800_000_000, "/tmp/state.json")), \
                patch("command_center_server.time.time", return_value=1_800_000_010), \
                patch("command_center_server.load_json", side_effect=lambda path: policy if path.endswith("testbed-b-demo-challenge.json") else {}):
            payload = server.get_execution_plane()

        cycle = payload["challenge_cycle"]
        self.assertEqual("READY", cycle["premarket_status"])
        self.assertEqual(1000, cycle["risk_budget_usd"])
        self.assertEqual(1.5, cycle["target_rr"])
        self.assertIn("NQ ORB canary window", cycle["market_read"])
        self.assertTrue(cycle["demo_only"])
        self.assertFalse(cycle["live_money_allowed"])
        self.assertTrue(cycle["practice_only_or_reset_required"])

    def test_founder_daily_brief_surfaces_safe_daily_loops(self):
        payloads = {
            "premarket-risk-brief.latest.json": {
                "decision": "NO_TRADE_ALGO",
                "operatorRead": "No deterministic routing.",
                "sizingPosture": {"algoMaxContracts": 0},
                "macro": {"nextThreeDays": [{"event": "NFP/Jobs"}]},
                "risks": [
                    {"severity": "hard", "kind": "daily-plan"},
                    {"severity": "hard", "kind": "source-hygiene"},
                    {"severity": "watch", "kind": "prediction-news-rss"},
                ],
            },
            "codex-automation-audit.latest.json": {
                "automations": [
                    {
                        "id": "bill-premarket-risk-brief",
                        "status": "ACTIVE",
                        "active": True,
                        "forbidsExecution": True,
                        "hasSafeLocks": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                    {
                        "id": "bill-eod-dreaming-synthesis",
                        "status": "ACTIVE",
                        "active": True,
                        "forbidsExecution": True,
                        "hasSafeLocks": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                    {
                        "id": "bill-prediction-forward-clob-capture",
                        "status": "ACTIVE",
                        "active": True,
                        "forbidsExecution": True,
                        "hasSafeLocks": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                ],
            },
            "free-data-feed-audit.latest.json": {
                "decision": "research-feeds-visible-execution-locked",
                "preferredFuturesDataPath": "topstepx-projectx",
                "readyForExecution": False,
                "executionAuthority": False,
                "summary": {
                    "wiredResearchFeeds": ["topstepx-projectx", "finnhub"],
                    "configuredButNotNative": ["alpaca-paper", "nous"],
                },
            },
            "topstep-demo-observation-posture.latest.json": {
                "decision": "demo-observation-ready-execution-locked",
                "readyForHumanDemoObservation": True,
                "readyForAlgoDemoExpansion": False,
            },
            "topstep-daily-learning.latest.json": {
                "decision": "demo-learning-visible-execution-locked",
                "learningStatus": "blocked-from-promotion",
                "issueCount": 2,
                "issues": [
                    {"id": "intended-vs-reconciled-side-mismatch"},
                    {"id": "reconciled-size-exceeds-current-max-contracts"},
                ],
                "brokerReconciliation": {
                    "totalMatchedSize": 15,
                    "estimatedPnlDollars": 1650.0,
                },
            },
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.parse_daily_control", return_value={
                    "routeApproval": "BLOCKED",
                    "brokerReconciliation": "UNKNOWN",
                    "decision": "No new Bill/Hermes orders approved.",
                }), \
                patch("command_center_server.freshness_for_state", return_value={
                    "status": "fresh",
                    "ageSeconds": 10,
                    "staleAfterSeconds": 21600,
                }), \
                patch("command_center_server.get_goal_audit", return_value={
                    "blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"],
                }), \
                patch("command_center_server.get_blocker_actions", return_value={
                    "priority": [
                        {
                            "id": "source-hygiene",
                            "title": "Reduce source hygiene backlog",
                            "safe": True,
                            "command": "npm run --silent bill:source-hygiene-plan",
                        }
                    ],
                }):
            payload = server.get_founder_daily_brief()

        self.assertEqual("daily-brief-visible-execution-locked", payload["decision"])
        self.assertEqual("NO_TRADE_ALGO", payload["premarket"]["decision"])
        self.assertEqual(0, payload["premarket"]["algoMaxContracts"])
        self.assertEqual(2, payload["premarket"]["hardRiskCount"])
        self.assertTrue(payload["loopSafe"])
        self.assertEqual("ACTIVE", payload["loops"][1]["status"])
        self.assertEqual("EOD dreaming synthesis", payload["loops"][1]["label"])
        self.assertEqual("topstepx-projectx", payload["feeds"]["preferredFuturesDataPath"])
        self.assertFalse(payload["feeds"]["executionAuthority"])
        self.assertTrue(payload["demoObservation"]["readyForHumanDemoObservation"])
        self.assertFalse(payload["demoObservation"]["readyForAlgoDemoExpansion"])
        self.assertEqual(2, payload["demoObservation"]["learningIssueCount"])
        self.assertEqual(15, payload["demoObservation"]["matchedTradeSize"])
        self.assertIn("intended-vs-reconciled-side-mismatch", payload["demoObservation"]["learningIssues"])
        self.assertEqual("source-hygiene", payload["nextSafeAction"]["id"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])

    def test_founder_metaprompt_is_coordination_only(self):
        payloads = {
            "founder-quant-cto-metaprompt.latest.json": {
                "decision": "active-founder-operating-prompt-execution-locked",
                "role": "founder quant strategist PM CTO",
                "primeDirective": "Preserve capital and remove blockers.",
                "safetyLocks": {
                    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                    "RH_TOPSTEP_READ_ONLY": "true",
                    "RH_LIVE_EXECUTION_ENABLED": "false",
                },
                "staleOverrideRule": "Old OCO/demo routing claims are stale.",
                "blockerQueue": [
                    {
                        "id": "topstep-session-safety",
                        "status": "blocked",
                        "why": "warning active",
                        "nextCommand": "npm run --silent bill:topstep-session-safety-clearance",
                    }
                ],
                "operatingFocus": {
                    "currentWeekMission": "Run one-week Topstep observation.",
                    "activeResearchLanes": [
                        {"id": "futures-topstep-demo-observation", "status": "blocked", "oneVariable": "data depth"}
                    ],
                },
                "laneOperatingContract": {
                    "decision": "two-lane-contract-active-execution-locked",
                    "lanes": [
                        {"id": "command-lane", "owner": "live Codex command thread", "status": "active"}
                    ],
                    "proofStandard": ["Every claim must name the artifact or test that proves it."],
                },
                "compoundingPath": ["Prove one Topstep account first."],
                "completionStandard": ["goal audit has zero blockers"],
            }
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json):
            payload = server.get_founder_metaprompt()

        self.assertEqual("active-founder-operating-prompt-execution-locked", payload["decision"])
        self.assertEqual("founder quant strategist PM CTO", payload["role"])
        self.assertEqual("blocked", payload["blockerQueue"][0]["status"])
        self.assertIn("stale", payload["staleOverrideRule"])
        self.assertIn("capitalDoctrine", payload)
        self.assertIn("killSwitches", payload)
        self.assertEqual("Run one-week Topstep observation.", payload["operatingFocus"]["currentWeekMission"])
        self.assertEqual("futures-topstep-demo-observation", payload["operatingFocus"]["activeResearchLanes"][0]["id"])
        self.assertEqual("two-lane-contract-active-execution-locked", payload["laneOperatingContract"]["decision"])
        self.assertEqual("command-lane", payload["laneOperatingContract"]["lanes"][0]["id"])
        self.assertIn("agentOperatingCommandments", payload)
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])
        self.assertFalse(payload["readyForExecution"])

    def test_monday_readiness_plane_surfaces_tracks_without_clearing_execution(self):
        jobs = {
            "jobs": [
                {
                    "name": "session-shadow-premarket",
                    "enabled": True,
                    "state": "scheduled",
                    "next_run_at": "2026-06-08T13:25:00+01:00",
                },
                {
                    "name": "session-shadow-postmarket",
                    "enabled": True,
                    "state": "scheduled",
                    "next_run_at": "2026-06-08T20:00:00+01:00",
                },
            ]
        }

        def fake_exists(path):
            return (
                path.endswith("scripts/session_shadow_premarket.py")
                or path.endswith("scripts/session_shadow_postmarket.py")
                or path.endswith("scripts/session_shadow_trade_logger.py")
                or path.endswith("src/signals/multitfEntry.ts")
            )

        with patch("command_center_server.load_json", return_value=jobs), \
                patch("command_center_server.os.path.exists", side_effect=fake_exists), \
                patch("command_center_server.load_text", return_value="RESEARCH ONLY; not in execution pipeline"), \
                patch("command_center_server.get_goal_audit", return_value={
                    "blockedIds": ["futures-demo-not-cleared", "prediction-paper-not-cleared"],
                    "readyForExecution": False,
                    "writesOrders": False,
                    "touchesBroker": False,
                }), \
                patch("command_center_server.get_topstep_data_plane", return_value={
                    "nextOpenSessionProofWindow": {"label": "Monday 14:30 BST"},
                }):
            payload = server.get_monday_readiness_plane()

        by_id = {track["id"]: track for track in payload["tracks"]}
        self.assertEqual("monday-readiness-visible-execution-locked", payload["decision"])
        self.assertEqual("ready", by_id["session-shadow-loop"]["status"])
        self.assertEqual("blocked", by_id["bridge-hardening-verification"]["status"])
        self.assertEqual("research-only-ready", by_id["multi-tf-entry-module"]["status"])
        self.assertEqual(2, payload["readyTrackCount"])
        self.assertFalse(by_id["multi-tf-entry-module"]["evidence"]["executionAttached"])
        self.assertIn("futures-demo-not-cleared", payload["blockers"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])

    def test_monday_readiness_can_clear_presentation_without_clearing_trading(self):
        jobs = {"jobs": [
            {"name": "session-shadow-premarket", "enabled": True, "state": "scheduled"},
            {"name": "session-shadow-postmarket", "enabled": True, "state": "scheduled"},
        ]}

        with patch("command_center_server.load_json", return_value=jobs), \
                patch("command_center_server.os.path.exists", return_value=True), \
                patch("command_center_server.load_text", return_value="RESEARCH ONLY execution pipeline CANONICAL_JOURNAL_PATH upsert_canonical_journal observationOnly brokerProof\n{}"), \
                patch("command_center_server.get_goal_audit", return_value={
                    "blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"],
                    "readyForExecution": False, "writesOrders": False, "touchesBroker": False,
                }), \
                patch("command_center_server.get_topstep_data_plane", return_value={
                    "sessionSafety": {"pauseBrokerTouchingProofs": True, "reason": "operator login yield"},
                }), \
                patch("command_center_server.get_founder_metaprompt", return_value={
                    "decision": "active-founder-operating-prompt-execution-locked",
                    "freshness": {"status": "fresh"},
                    "presentationDemoContract": {"rule": "separate", "walkthrough": ["Gates", "Edges", "Ops", "Trade"]},
                }), \
                patch("command_center_server.get_live_readiness_gate", return_value={
                    "passCount": 19, "totalCount": 21, "failedChecks": [{"id": "source-clean"}],
                    "readyForDemoExpansion": False,
                }), \
                patch("command_center_server.get_signal_quality_plane", return_value={
                    "safeVisible": True, "rating": 7.45, "blockers": ["missing inputs: arbitration"],
                }), \
                patch("command_center_server.get_blocker_actions", return_value={
                    "priority": [{"id": "topstep-archive-depth"}],
                    "capitalCockpit": {"killSwitches": [{"id": "topstep-session-safety"}]},
                }), \
                patch("command_center_server.parse_daily_control", return_value={
                    "routeApproval": "BLOCKED", "decision": "No new Bill/Hermes orders approved.",
                }), \
                patch("command_center_server.get_n8n_status", return_value={
                    "running": True, "workflowHealth": "degraded",
                }), \
                patch("command_center_server.get_process_info", return_value={"running": True, "count": 12}), \
                patch("command_center_server.freshness_for_state", return_value={"status": "fresh"}), \
                patch("command_center_server.state_json", return_value=({}, "/tmp/state")):
            payload = server.get_monday_readiness_plane()

        self.assertTrue(payload["readyForPresentationDemo"])
        self.assertEqual("presentation-demo-ready-execution-locked", payload["presentationDecision"])
        self.assertEqual(["n8n-control-health"], [item["id"] for item in payload["presentationWarnings"]])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])
        self.assertTrue(payload["tradeClearance"]["topstepProofsHeldBySessionSafety"])
        self.assertTrue(all(step["status"] == "held-by-session-safety" for step in payload["tracks"][1]["evidence"]["readOnlySteps"][:3]))

    def test_monday_readiness_accepts_founder_armed_testbed_demo_posture(self):
        jobs = {"jobs": [
            {"name": "session-shadow-premarket", "enabled": True, "state": "scheduled"},
            {"name": "session-shadow-postmarket", "enabled": True, "state": "scheduled"},
        ]}

        with patch("command_center_server.load_json", return_value=jobs), \
                patch("command_center_server.os.path.exists", return_value=True), \
                patch("command_center_server.load_text", return_value="RESEARCH ONLY execution pipeline CANONICAL_JOURNAL_PATH upsert_canonical_journal observationOnly brokerProof\n{}"), \
                patch("command_center_server.get_goal_audit", return_value={
                    "blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"],
                    "readyForExecution": False, "writesOrders": False, "touchesBroker": False,
                }), \
                patch("command_center_server.get_topstep_data_plane", return_value={
                    "sessionSafety": {"pauseBrokerTouchingProofs": True, "reason": "operator login yield"},
                }), \
                patch("command_center_server.get_founder_metaprompt", return_value={
                    "decision": "active-founder-operating-prompt-execution-locked",
                    "freshness": {"status": "fresh"},
                    "presentationDemoContract": {"rule": "separate", "walkthrough": ["Gates", "Edges", "Ops", "Trade"]},
                }), \
                patch("command_center_server.get_live_readiness_gate", return_value={
                    "passCount": 19, "totalCount": 21, "failedChecks": [{"id": "source-clean"}],
                    "readyForDemoExpansion": False,
                }), \
                patch("command_center_server.get_signal_quality_plane", return_value={
                    "safeVisible": True, "rating": 7.45, "blockers": ["missing inputs: arbitration"],
                }), \
                patch("command_center_server.get_blocker_actions", return_value={
                    "priority": [{"id": "topstep-archive-depth"}],
                    "capitalCockpit": {"killSwitches": [{"id": "topstep-session-safety"}]},
                }), \
                patch("command_center_server.parse_daily_control", return_value={
                    "routeApproval": "APPROVED",
                    "brokerReconciliation": "GREEN",
                    "decision": "Demo routing is armed by env and daily controls; deterministic broker/firewall checks still decide each order.",
                }), \
                patch("command_center_server.get_n8n_status", return_value={
                    "running": True, "workflowHealth": "healthy",
                }), \
                patch("command_center_server.get_process_info", return_value={"running": True, "count": 12}), \
                patch("command_center_server.freshness_for_state", return_value={"status": "fresh"}), \
                patch("command_center_server.state_json", return_value=({}, "/tmp/state")):
            payload = server.get_monday_readiness_plane()

        lock_check = next(item for item in payload["presentationChecks"] if item["id"] == "execution-lock-visible")
        self.assertTrue(lock_check["passed"])
        self.assertIn("testbed-B", lock_check["summary"])
        self.assertTrue(payload["readyForPresentationDemo"])
        self.assertFalse(payload["readyForExecution"])

    def test_monday_readiness_rejects_approved_route_without_green_reconciliation(self):
        with patch("command_center_server.load_json", return_value={"jobs": []}), \
                patch("command_center_server.os.path.exists", return_value=True), \
                patch("command_center_server.load_text", return_value="{}"), \
                patch("command_center_server.get_goal_audit", return_value={
                    "readyForExecution": False, "writesOrders": False, "touchesBroker": False,
                }), \
                patch("command_center_server.get_topstep_data_plane", return_value={}), \
                patch("command_center_server.get_founder_metaprompt", return_value={}), \
                patch("command_center_server.get_live_readiness_gate", return_value={}), \
                patch("command_center_server.get_signal_quality_plane", return_value={}), \
                patch("command_center_server.get_blocker_actions", return_value={}), \
                patch("command_center_server.parse_daily_control", return_value={
                    "routeApproval": "APPROVED",
                    "brokerReconciliation": "UNKNOWN",
                    "decision": "Demo routing is armed by env and daily controls.",
                }), \
                patch("command_center_server.get_n8n_status", return_value={"running": True}), \
                patch("command_center_server.get_process_info", return_value={"running": True, "count": 1}), \
                patch("command_center_server.freshness_for_state", return_value={"status": "fresh"}), \
                patch("command_center_server.state_json", return_value=({}, "/tmp/state")):
            payload = server.get_monday_readiness_plane()

        lock_check = next(item for item in payload["presentationChecks"] if item["id"] == "execution-lock-visible")
        self.assertFalse(lock_check["passed"])
        self.assertFalse(payload["readyForPresentationDemo"])

    def test_lane_coordination_plane_divides_command_and_research_work(self):
        payloads = {
            "bill-next-research-actions.latest.json": {},
            "ai-scientist-data-access-audit.latest.json": {
                "decision": "research-only-ai-scientist-data-access-incomplete",
                "visibleGoldWalkforwardCount": 3,
                "goldWalkforwardCount": 9,
                "featureGaps": [{"id": "one-minute-entry-data"}],
            },
            "current-alpha-watch.latest.json": {
                "nextOneVariableTest": {
                    "id": "fabervaale-orb-broker-grade-5m-depth",
                    "oneVariable": "data source/depth",
                    "command": "npm run --silent bill:futures-broker-parity-plan",
                },
            },
            "bill-runtime-architecture-audit.latest.json": {"decision": "runtime-visible"},
            "stale-strategy-claim-guard.latest.json": {"findingCount": 1},
            "bill-source-intake-manifest.latest.json": {"reviewBacklog": 5},
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.get_goal_audit", return_value={
                    "blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"],
                }), \
                patch("command_center_server.get_blocker_actions", return_value={
                    "priority": [{
                        "id": "source-hygiene",
                        "title": "Reduce source hygiene backlog",
                        "command": "npm run --silent bill:source-hygiene-plan",
                    }],
                }), \
                patch("command_center_server.get_strategy_test_framework_plane", return_value={
                    "decision": "research-only-strategy-framework-recovery-blocked",
                    "oneVariableResearch": {"resultSummary": {"nextFollowUp": {"oneVariable": "entry timing"}}},
                }), \
                patch("command_center_server.os.path.exists", return_value=True):
            payload = server.get_lane_coordination_plane()

        lanes = {lane["id"]: lane for lane in payload["lanes"]}
        self.assertEqual("lane-coordination-visible-execution-locked", payload["decision"])
        self.assertEqual("active-blocked", lanes["command-lane"]["status"])
        self.assertEqual("research-only-active", lanes["research-lane"]["status"])
        self.assertEqual("source-hygiene", lanes["command-lane"]["nextAction"]["id"])
        self.assertEqual("fabervaale-orb-broker-grade-5m-depth", lanes["research-lane"]["nextAction"]["id"])
        self.assertIn("one-minute-entry-data", lanes["research-lane"]["evidence"]["featureGapIds"])
        self.assertIn("futures-demo-not-cleared", payload["blockers"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])

    def test_lane_coordination_plane_handles_missing_state_artifacts(self):
        def fake_state_json(name):
            return None, "/tmp/missing-state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.get_goal_audit", return_value={"blockedIds": []}), \
                patch("command_center_server.get_blocker_actions", return_value={}), \
                patch("command_center_server.get_strategy_test_framework_plane", return_value={}), \
                patch("command_center_server.os.path.exists", return_value=False):
            payload = server.get_lane_coordination_plane()

        lanes = {lane["id"]: lane for lane in payload["lanes"]}
        self.assertEqual("lane-coordination-visible-execution-locked", payload["decision"])
        self.assertEqual("review-goal-blockers", lanes["command-lane"]["nextAction"]["id"])
        self.assertEqual("ai-scientist-1m-entry-data", lanes["research-lane"]["nextAction"]["id"])
        self.assertEqual(
            "npm run --silent bill:ai-scientist-data-access-audit",
            lanes["research-lane"]["nextAction"]["command"],
        )
        self.assertEqual([], lanes["research-lane"]["evidence"]["featureGapIds"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])

    def test_strategy_test_framework_plane_is_research_only(self):
        payloads = {
            "strategy-test-framework-status.latest.json": {
                "decision": "research-only-strategy-framework-recovery-blocked",
                "blockedIds": ["walkforward-matrix-stale", "strategy-factory-not-deployable"],
                "blockedCount": 2,
                "operatorRead": "Research only.",
                "walkforwardMatrix": {
                    "status": "reject",
                    "ageHours": 84.2,
                    "csvPath": "data/free/ALL-6MARKETS-60m-60d-normalized.csv",
                    "totalWindowsEvaluated": 24,
                    "maxWindowsEvaluated": 6,
                    "bestConfigId": "fixed-20d-5d",
                    "commonFailureModes": ["stitched-oos-net-negative"],
                },
                "strategyFactory": {"walkforwardDeployable": False, "decision": "research-only"},
                "oneVariableResearch": {
                    "present": True,
                    "decision": "research-only-one-variable-queue",
                    "resultSummary": {
                        "bestObserved": {
                            "experimentId": "ny-morning-only",
                            "baselineId": "orb-breakout-15m",
                            "oosTradeCount": 50,
                            "oosNetPoints": 713.25,
                            "oosProfitFactor": 1.46,
                            "blockers": ["walkforward-oos-profit-factor-too-low"],
                        },
                        "nextFollowUp": {
                            "oneVariable": "walkforward PF/cost stress detail only",
                            "researchOnly": True,
                            "readyForExecution": False,
                        },
                    },
                },
                "strategyPlaybook": {"decision": "research-only", "ageHours": 12.0, "strategyCount": 5},
                "nextCommands": [
                    {
                        "id": "registration-and-matrix-smoke",
                        "command": "npm run --silent test -- tests/walkforwardMatrix.test.ts tests/strategyRegistrationGuard.test.ts",
                        "why": "smoke first",
                        "touchesBroker": False,
                        "writesOrders": False,
                    }
                ],
                "staleThreadRule": "Old demo routing claims are stale.",
            }
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json):
            payload = server.get_strategy_test_framework_plane()

        self.assertEqual(payload["decision"], "research-only-strategy-framework-recovery-blocked")
        self.assertEqual(2, payload["blockedCount"])
        self.assertEqual("reject", payload["walkforwardMatrix"]["status"])
        self.assertEqual(24, payload["walkforwardMatrix"]["totalWindowsEvaluated"])
        self.assertFalse(payload["strategyFactory"]["walkforwardDeployable"])
        self.assertEqual(
            "orb-breakout-15m",
            payload["oneVariableResearch"]["resultSummary"]["bestObserved"]["baselineId"],
        )
        self.assertEqual(
            "walkforward PF/cost stress detail only",
            payload["oneVariableResearch"]["resultSummary"]["nextFollowUp"]["oneVariable"],
        )
        self.assertEqual("registration-and-matrix-smoke", payload["nextCommands"][0]["id"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])

    def test_data_master_plane_is_read_only_catalog_truth(self):
        payloads = {
            "bill-data-master.latest.json": {
                "datasetCount": 229,
                "tierCounts": {
                    "gold-walkforward": 9,
                    "quarantine-review": 6,
                    "silver-research": 102,
                },
                "outputCsv": "/tmp/bill-data-master.csv",
                "topDatasets": [
                    {
                        "path": "data/free/NQ-1m-3yr.csv",
                        "rows": 1048575,
                        "trustTier": "gold-walkforward",
                    }
                ],
                "hardRules": [
                    "This catalog is data inventory only; it does not approve strategy promotion or execution."
                ],
            }
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.os.path.exists", return_value=True), \
                patch("command_center_server.freshness_for_state", return_value={"status": "fresh", "ageSeconds": 12}):
            payload = server.get_data_master_plane()

        self.assertEqual("data-master-visible-execution-locked", payload["decision"])
        self.assertEqual(229, payload["datasetCount"])
        self.assertEqual(9, payload["goldWalkforwardCount"])
        self.assertEqual(6, payload["quarantineReviewCount"])
        self.assertTrue(payload["csvExists"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])

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
        cockpit = payload["capitalCockpit"]
        self.assertEqual("L0_RESEARCH_CONTROL_PLANE", cockpit["mode"])
        self.assertEqual("ZERO_NEW_RISK", cockpit["capitalAtRisk"])
        self.assertEqual("prediction-paper-gate", cockpit["killSwitches"][2]["id"])
        self.assertEqual("armed", cockpit["killSwitches"][2]["status"])
        self.assertEqual("paper fills first", cockpit["allocationLadder"][2]["budgetRule"])

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
        self.assertIn("bill:topstep-session-safety-clearance", payload["priority"][0]["command"])
        archive = next(item for item in payload["priority"] if item["id"] == "topstep-archive-depth")
        self.assertEqual("paused", archive["status"])
        self.assertFalse(archive["safe"])
        self.assertIn("Paused by Topstep session safety", archive["why"])
        topstep_switch = next(item for item in payload["capitalCockpit"]["killSwitches"] if item["id"] == "topstep-session-safety")
        self.assertEqual("armed", topstep_switch["status"])

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
            "topstep-session-safety-clearance.latest.json": {
                "decision": "operator-confirmation-required",
                "machineChecksPassed": True,
                "operatorConfirmationRequired": True,
                "readyForReadOnlyProofWindow": False,
                "blockers": ["operator-confirms-topstep-warning-cleared"],
            },
            "futures-broker-parity-plan.latest.json": {
                "nextOpenSessionProofWindow": {
                    "recommendedProofStartUtc": "2026-06-07T22:05:00+00:00",
                    "reason": "next Sunday 18:00 ET Globex open after Friday close",
                    "commandsAreDataOnly": True,
                }
            },
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.age_for_state", return_value=10):
            payload = server.get_topstep_data_plane()

        self.assertTrue(payload["sessionSafety"]["pauseBrokerTouchingProofs"])
        self.assertEqual("multiple sessions", payload["sessionSafety"]["reason"])
        self.assertTrue(payload["sessionSafetyClearance"]["machineChecksPassed"])
        self.assertTrue(payload["sessionSafetyClearance"]["operatorConfirmationRequired"])
        self.assertFalse(payload["sessionSafetyClearance"]["readyForReadOnlyProofWindow"])
        self.assertEqual(20, payload["archiveMinimumSessions"])
        self.assertEqual(
            "2026-06-07T22:05:00+00:00",
            payload["nextOpenSessionProofWindow"]["recommendedProofStartUtc"],
        )
        self.assertTrue(payload["nextOpenSessionProofWindow"]["commandsAreDataOnly"])
        self.assertIn("topstep-session-safety-paused", payload["blockers"])

    def test_full_state_surfaces_topstep_demo_observation_aliases(self):
        demo = {
            "readyForHumanDemoObservation": True,
            "readyForAlgoDemoExpansion": False,
            "learningIssueCount": 2,
        }

        mocks = [
            ("get_system", {}),
            ("get_process_info", {}),
            ("get_bridge_status", {}),
            ("get_control_plane", {}),
            ("parse_daily_control", {}),
            ("get_market_data_plane", {}),
            ("get_data_master_plane", {}),
            ("get_topstep_data_plane", {"demoObservation": demo}),
            ("get_risk_plane", {}),
            ("get_signal_quality_plane", {}),
            ("get_prediction_paper_plane", {}),
            ("get_goal_audit", {}),
            ("get_founder_operating_state", {}),
            ("get_agent_governance", {}),
            ("get_institutional_benchmark", {}),
            ("get_blocker_actions", {}),
            ("get_founder_daily_brief", {}),
            ("get_founder_metaprompt", {}),
            ("get_strategy_test_framework_plane", {}),
            ("get_trade_performance", {}),
            ("get_signal_state", {}),
            ("get_recent_cron_output", {}),
            ("load_json", {}),
        ]
        with ExitStack() as stack:
            for name, value in mocks:
                stack.enter_context(patch(f"command_center_server.{name}", return_value=value))
            payload = server.get_full_state()

        self.assertEqual(demo, payload["topstepData"]["demoObservation"])
        self.assertEqual(demo, payload["topstepDemoObservation"])
        self.assertEqual(demo, payload["topstep_demo_observation"])

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
            "worktree-consolidation.latest.json": {
                "canonicalSource": {"dirtyFiles": 91},
                "dirtySiblingWorktrees": {"count": 1},
                "sourceCleanBlockers": ["canonical source root has 91 dirty files"],
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
        self.assertFalse(payload["source"]["canonicalSourceClean"])
        self.assertEqual(91, payload["source"]["canonicalDirtyFiles"])
        self.assertEqual(1, payload["source"]["siblingQuarantineCount"])
        self.assertIn("canonical source root", payload["source"]["sourceCleanBlockers"][0])
        self.assertTrue(payload["source"]["sourceIntakeVisible"])
        self.assertFalse(payload["source"]["readyForExecution"])

    def test_blocker_actions_distinguish_clean_canonical_source_from_sibling_quarantine(self):
        payloads = {
            "bill-goal-completion-audit.latest.json": {
                "blockedIds": ["source-hygiene-not-cleared"],
            },
            "bill-source-intake-manifest.latest.json": {
                "sourceClean": True,
                "dirtyStatusCount": 0,
            },
            "worktree-consolidation.latest.json": {
                "canonicalSource": {"dirtyFiles": 0},
                "sourceCleanBlockers": ["1 dirty sibling worktree(s) remain quarantine/selective-intake only"],
            },
            "bill-source-hygiene-plan.latest.json": {},
            "prediction-event-paper-promotion-gate.latest.json": {},
            "bill-runtime-architecture-audit.latest.json": {},
            "futures-data-requirements.latest.json": {},
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.freshness_for_state", return_value={"status": "fresh", "ageSeconds": 10}):
            payload = server.get_blocker_actions()

        source_action = next(item for item in payload["priority"] if item["id"] == "source-hygiene")
        self.assertEqual("review", source_action["status"])
        self.assertEqual("Resolve sibling source quarantine", source_action["title"])
        self.assertEqual("npm run --silent bill:sibling-worktree-intake", source_action["command"])
        self.assertIn("Canonical source clean", source_action["why"])

    def test_blocker_actions_show_source_hygiene_pass_after_clean_sibling_intake(self):
        payloads = {
            "bill-goal-completion-audit.latest.json": {
                "blockedIds": ["futures-demo-not-cleared", "prediction-paper-not-cleared"],
            },
            "bill-source-intake-manifest.latest.json": {
                "sourceClean": True,
                "dirtyStatusCount": 0,
            },
            "worktree-consolidation.latest.json": {
                "canonicalSource": {"dirtyFiles": 0},
                "sourceCleanBlockers": [],
            },
            "bill-source-hygiene-plan.latest.json": {},
            "prediction-event-paper-promotion-gate.latest.json": {},
            "bill-runtime-architecture-audit.latest.json": {},
            "futures-data-requirements.latest.json": {},
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.freshness_for_state", return_value={"status": "fresh", "ageSeconds": 10}):
            payload = server.get_blocker_actions()

        source_action = next(item for item in payload["priority"] if item["id"] == "source-hygiene")
        self.assertEqual("pass", source_action["status"])
        self.assertEqual("Confirm source hygiene stays clean", source_action["title"])
        self.assertIn("sibling quarantine clear", source_action["why"])

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

    def test_founder_operating_state_keeps_source_gate_blocked_when_goal_blocker_remains(self):
        with patch("command_center_server.parse_daily_control", return_value={
            "routeApproval": "BLOCKED",
            "brokerReconciliation": "UNKNOWN",
        }), patch("command_center_server.get_topstep_data_plane", return_value={
            "readyForExecutionData": True,
            "brokerFlat": True,
            "openPositions": 0,
            "archiveRthSessions": 3,
            "blockers": [],
        }), patch("command_center_server.get_market_data_plane", return_value={
            "readyForExecutionData": True,
            "source": "topstep_realtime",
        }), patch("command_center_server.get_risk_plane", return_value={
            "liveReadiness": {"deployableNow": False, "status": "blocked"},
            "source": {
                "canonicalSourceClean": True,
                "canonicalDirtyFiles": 0,
                "executionLiveDirtyCount": 0,
                "siblingQuarantineCount": 1,
            },
            "topstep": {"brokerFlat": True, "openPositions": 0},
        }), patch("command_center_server.get_goal_audit", return_value={
            "blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"],
        }), patch("command_center_server.get_blocker_actions", return_value={"priority": []}):
            payload = server.get_founder_operating_state()

        by_gate = {gate["id"]: gate for gate in payload["gates"]}
        self.assertEqual("blocked", by_gate["source-hygiene"]["status"])
        self.assertIn("canonical clean", by_gate["source-hygiene"]["evidence"])
        self.assertIn("goal blocker remains", by_gate["source-hygiene"]["evidence"])
        self.assertIn("source-hygiene", payload["blockingGateIds"])
        self.assertEqual("BLOCKED", payload["tradePermission"])

    def test_founder_operating_state_surfaces_ranked_blocker_burndown(self):
        with patch("command_center_server.parse_daily_control", return_value={
            "routeApproval": "BLOCKED",
            "brokerReconciliation": "UNKNOWN",
        }), patch("command_center_server.get_topstep_data_plane", return_value={
            "readyForExecutionData": False,
            "brokerFlat": True,
            "openPositions": 0,
            "archiveRthSessions": 3,
            "blockers": ["topstep-readonly-archive-depth-thin"],
        }), patch("command_center_server.get_market_data_plane", return_value={
            "readyForExecutionData": False,
            "source": "topstep_realtime",
        }), patch("command_center_server.get_risk_plane", return_value={
            "liveReadiness": {"deployableNow": False, "status": "yellow"},
            "source": {"canonicalSourceClean": True, "executionLiveDirtyCount": 0, "siblingQuarantineCount": 1},
            "topstep": {"brokerFlat": True, "openPositions": 0},
        }), patch("command_center_server.get_goal_audit", return_value={
            "blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"],
        }), patch("command_center_server.get_blocker_actions", return_value={
            "priority": [
                {
                    "id": "topstep-archive-depth",
                    "title": "Accumulate TopstepX read-only archive depth",
                    "lane": "futures",
                    "status": "blocked",
                    "safe": True,
                    "command": "npm run --silent bill:topstep-market-data-smoke",
                    "why": "3 RTH sessions captured.",
                },
                {
                    "id": "source-hygiene",
                    "title": "Resolve sibling source quarantine",
                    "lane": "source-hygiene",
                    "status": "review",
                    "safe": True,
                    "command": "npm run --silent bill:sibling-worktree-intake",
                    "why": "Canonical source clean; sibling remains quarantined.",
                },
            ],
        }):
            payload = server.get_founder_operating_state()

        self.assertEqual(2, len(payload["blockerBurnDown"]))
        self.assertEqual(1, payload["blockerBurnDown"][0]["rank"])
        self.assertEqual("topstep-archive-depth", payload["blockerBurnDown"][0]["id"])
        self.assertEqual("npm run --silent bill:topstep-market-data-smoke", payload["blockerBurnDown"][0]["command"])
        self.assertTrue(payload["blockerBurnDown"][0]["safe"])
        self.assertEqual(2, payload["blockerBurnDown"][1]["rank"])

    def test_institutional_benchmark_blocks_source_hygiene_until_goal_clears(self):
        with patch("command_center_server.get_control_plane", return_value={
            "researchOnly": True,
            "writesOrders": False,
            "movesFunds": False,
        }), patch("command_center_server.get_market_data_plane", return_value={
            "readyForExecutionData": True,
            "quote": {"source": "topstep_realtime"},
            "freshness": {"verdict": "PASS"},
            "topstep": {"readyForFiveMinuteResearch": True, "currentBarsProofPassed": True, "brokerParityPassed": True, "archiveRthSessions": 3},
        }), patch("command_center_server.get_risk_plane", return_value={
            "source": {
                "canonicalSourceClean": True,
                "executionLiveDirtyCount": 0,
                "siblingQuarantineCount": 1,
            },
            "topstep": {"brokerFlat": True},
            "liveReadiness": {"deployableNow": False, "status": "yellow", "survivabilityScore": 78},
        }), patch("command_center_server.get_goal_audit", return_value={
            "blockedIds": ["source-hygiene-not-cleared"],
        }), patch("command_center_server.get_n8n_status", return_value={
            "source": "postgres",
            "running": True,
            "activeCount": 9,
            "workflowCount": 40,
        }), patch("command_center_server.parse_daily_control", return_value={
            "routeApproval": "BLOCKED",
            "brokerReconciliation": "UNKNOWN",
        }):
            payload = server.get_institutional_benchmark()

        by_id = {item["id"]: item for item in payload["items"]}
        self.assertEqual("blocked", by_id["source-hygiene"]["status"])
        self.assertIn("goalBlocked=True", by_id["source-hygiene"]["evidence"])
        self.assertEqual(payload["score"], payload["passCount"])
        self.assertEqual(payload["score"], payload["passed"])
        self.assertEqual(3, payload["blockedCount"])
        self.assertEqual(3, payload["blockerCount"])
        self.assertEqual(1, payload["reviewCount"])
        self.assertEqual(4, payload["openIssueCount"])
        self.assertEqual(
            ["human-approval", "model-validation", "source-hygiene"],
            [item["id"] for item in payload["blockers"]],
        )
        self.assertEqual({"pass": 5, "blocked": 3, "review": 1}, payload["statusCounts"])

    def test_institutional_benchmark_accepts_topstep_broker_grade_data_proof_without_route_permission(self):
        with patch("command_center_server.get_control_plane", return_value={
            "researchOnly": True,
            "writesOrders": False,
            "movesFunds": False,
        }), patch("command_center_server.get_market_data_plane", return_value={
            "readyForExecutionData": False,
            "brokerGradeDataProofPassed": True,
            "brokerGradeDataProofSource": "topstepx_projectx",
            "topstepRealtimeProofPassed": True,
            "topstepExecutionGradeRealtimeProofPassed": True,
            "freshness": {"verdict": "STALE"},
            "topstep": {"readyForFiveMinuteResearch": True, "currentBarsProofPassed": True, "brokerParityPassed": True, "archiveRthSessions": 3},
        }), patch("command_center_server.get_risk_plane", return_value={
            "source": {
                "canonicalSourceClean": False,
                "executionLiveDirtyCount": 0,
                "siblingQuarantineCount": 1,
            },
            "topstep": {"brokerFlat": True},
            "liveReadiness": {"deployableNow": False, "status": "yellow", "survivabilityScore": 78},
        }), patch("command_center_server.get_goal_audit", return_value={
            "blockedIds": ["source-hygiene-not-cleared"],
        }), patch("command_center_server.get_n8n_status", return_value={
            "source": "postgres",
            "running": True,
            "activeCount": 9,
            "workflowCount": 40,
        }), patch("command_center_server.parse_daily_control", return_value={
            "routeApproval": "BLOCKED",
            "brokerReconciliation": "UNKNOWN",
        }):
            payload = server.get_institutional_benchmark()

        by_id = {item["id"]: item for item in payload["items"]}
        self.assertEqual("pass", by_id["market-data-provenance"]["status"])
        self.assertIn("topstepx_projectx", by_id["market-data-provenance"]["evidence"])
        self.assertEqual("blocked", by_id["human-approval"]["status"])
        self.assertIn("human-approval", [item["id"] for item in payload["blockers"]])

    def test_institutional_benchmark_uses_strategy_framework_before_stale_live_readiness(self):
        with patch("command_center_server.get_control_plane", return_value={
            "researchOnly": True,
            "writesOrders": False,
            "movesFunds": False,
        }), patch("command_center_server.get_market_data_plane", return_value={
            "readyForExecutionData": True,
            "quote": {"source": "topstep_realtime"},
            "freshness": {"verdict": "PASS"},
            "topstep": {"readyForFiveMinuteResearch": True, "currentBarsProofPassed": True, "brokerParityPassed": True, "archiveRthSessions": 3},
        }), patch("command_center_server.get_risk_plane", return_value={
            "source": {"canonicalSourceClean": True, "executionLiveDirtyCount": 0},
            "topstep": {"brokerFlat": True},
            "liveReadiness": {"deployableNow": True, "status": "green", "survivabilityScore": 99},
        }), patch("command_center_server.get_goal_audit", return_value={
            "blockedIds": [],
        }), patch("command_center_server.get_n8n_status", return_value={
            "source": "postgres",
            "running": True,
            "activeCount": 9,
            "workflowCount": 40,
        }), patch("command_center_server.parse_daily_control", return_value={
            "routeApproval": "BLOCKED",
            "brokerReconciliation": "UNKNOWN",
        }), patch("command_center_server.state_json", side_effect=lambda name: ({
            "strategy-test-framework-status.latest.json": {
                "decision": "research-only-strategy-framework-recovery-blocked",
                "blockedIds": ["walkforward-matrix-not-robust"],
                "walkforwardMatrix": {"status": "reject"},
                "strategyFactory": {"status": "blocked", "walkforwardDeployable": False},
                "oneVariableResearch": {
                    "resultSummary": {
                        "bestObserved": {"researchCandidate": False}
                    }
                },
            },
            "live-readiness.latest.json": {"final": {"report": {"deployableNow": True}}},
        }.get(name, {}), "/tmp/state")):
            payload = server.get_institutional_benchmark()

        model = next(item for item in payload["items"] if item["id"] == "model-validation")
        self.assertEqual("blocked", model["status"])
        self.assertIn("framework=research-only-strategy-framework-recovery-blocked", model["evidence"])
        self.assertIn("matrix=reject", model["evidence"])
        self.assertNotIn("survivability=99", model["evidence"])

    def test_market_data_plane_marks_alpaca_as_sandbox_not_futures_truth(self):
        payloads = {
            "realtime-data-preflight.latest.json": {"readyForExecutionData": True, "decision": "execution-data-ready"},
            "realtime-quote.latest.json": {"source": "topstep_realtime", "execution_grade": True},
            "data-freshness-gate.latest.json": {"verdict": "PASS"},
            "databento-realtime-smoke.latest.json": {"status": "NO_QUOTES"},
            "free-data-feed-audit.latest.json": {
                "providers": [
                    {
                        "id": "alpaca-paper",
                        "mode": "wired-research",
                        "configured": True,
                        "wired": True,
                        "role": "Equities/options/crypto paper and research sandbox; not Topstep futures broker truth.",
                        "command": "bill:positioning-status / bill:dealer-gamma-status",
                    }
                ]
            },
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.state_mtime", return_value=(time.time(), "/tmp/state")), \
                patch("command_center_server.get_topstep_data_plane", return_value={
                    "status": "PASS",
                    "currentBarsProofPassed": True,
                    "brokerParityPassed": False,
                    "topstepRealtimeProofPassed": True,
                    "executionGradeRealtimeProofPassed": True,
                    "readyForFiveMinuteResearch": True,
                }):
            payload = server.get_market_data_plane()

        self.assertEqual("topstepx_projectx", payload["preferredSource"])
        self.assertTrue(payload["brokerGradeDataProofPassed"])
        self.assertEqual("read-only-current-bars-and-realtime-proof", payload["brokerGradeDataProofMode"])
        self.assertEqual("optional-secondary-depth-research", payload["databentoRole"])
        self.assertEqual("wired-research", payload["alpacaSandbox"]["status"])
        self.assertTrue(payload["alpacaSandbox"]["configured"])
        self.assertTrue(payload["alpacaSandbox"]["wired"])
        self.assertIn("Equities/options/crypto", payload["alpacaSandbox"]["role"])
        self.assertFalse(payload["alpacaSandbox"]["executionAuthority"])
        self.assertIn("TopstepX/ProjectX", payload["recommendedPath"])
        self.assertIn("Alpaca", payload["recommendedPath"])

    def test_market_data_plane_blocks_execution_when_canonical_quote_is_stale(self):
        payloads = {
            "realtime-data-preflight.latest.json": {"readyForExecutionData": True, "decision": "execution-data-ready", "blockers": []},
            "realtime-quote.latest.json": {"source": "topstep_realtime", "execution_grade": True},
            "data-freshness-gate.latest.json": {
                "verdict": "PASS",
                "action": "allow_trades",
                "checks": [{"symbol": "nq", "max_age": 60}],
            },
            "databento-realtime-smoke.latest.json": {"status": "NO_QUOTES"},
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.state_mtime", return_value=(time.time() - 125, "/tmp/state")), \
                patch("command_center_server.get_topstep_data_plane", return_value={
                    "status": "PASS",
                    "currentBarsProofPassed": True,
                    "brokerParityPassed": True,
                    "topstepRealtimeProofPassed": True,
                    "executionGradeRealtimeProofPassed": True,
                    "readyForFiveMinuteResearch": True,
                }):
            payload = server.get_market_data_plane()

        self.assertFalse(payload["readyForExecutionData"])
        self.assertTrue(payload["executionGrade"])
        self.assertFalse(payload["quoteFresh"])
        self.assertFalse(payload["freshEnoughForExecution"])
        self.assertEqual("block-execution-data", payload["decision"])
        self.assertEqual("STALE", payload["freshnessVerdict"])
        self.assertEqual("block_all_trades", payload["freshness"]["action"])
        self.assertIn("canonical realtime quote is stale", payload["blockers"][0])
        self.assertTrue(payload["brokerGradeDataProofPassed"])

    def test_n8n_status_surfaces_self_heal_errors_as_monitoring_health(self):
        payloads = {
            "bill-runtime-architecture-audit.latest.json": {
                "n8n": {
                    "source": "postgres",
                    "path": "postgres://localhost:5432/n8n",
                    "workflowCount": 40,
                    "activeCount": 32,
                    "billWorkflowCount": 16,
                    "activeBillWorkflowCount": 9,
                },
                "warnings": ["active-bill-related-n8n-workflow-present-review-before-use"],
            },
            "n8n-self-heal.json": {
                "workflows_healthy": False,
                "errors": ["6 workflow errors in last hour"],
            },
        }

        def fake_state_json(name):
            return payloads.get(name, {}), "/tmp/state"

        with patch("command_center_server.state_json", side_effect=fake_state_json), \
                patch("command_center_server.freshness_for_state", return_value={
                    "status": "fresh", "ageSeconds": 1, "staleAfterSeconds": 600,
                }), \
                patch("command_center_server.http_json", side_effect=[
                    (True, {"status": "ok"}),
                    (False, {}),
                ]):
            payload = server.get_n8n_status()

        self.assertTrue(payload["running"])
        self.assertEqual("errors", payload["workflowHealth"])
        self.assertEqual(["6 workflow errors in last hour"], payload["workflowErrors"])
        self.assertFalse(payload["executionAuthority"])
        self.assertIn("monitoring/automation health", payload["operatorRead"])

    def test_n8n_status_does_not_surface_stale_workflow_errors_as_current(self):
        payloads = {
            "bill-runtime-architecture-audit.latest.json": {"n8n": {}},
            "n8n-self-heal.json": {
                "workflows_healthy": False,
                "errors": ["13 workflow errors in last hour"],
            },
        }

        with patch("command_center_server.state_json", side_effect=lambda name: (payloads.get(name, {}), "/tmp/state")), \
                patch("command_center_server.freshness_for_state", return_value={
                    "status": "stale", "ageSeconds": 86400, "staleAfterSeconds": 600,
                }), \
                patch("command_center_server.http_json", side_effect=[(True, {"status": "ok"}), (False, {})]):
            payload = server.get_n8n_status()

        self.assertEqual("stale", payload["workflowHealth"])
        self.assertNotIn("13 workflow errors", payload["workflowErrors"][0])


if __name__ == "__main__":
    unittest.main()
