import unittest

from scripts.bill_execution_intake_manifest import HERMES, build_manifest, default_markdown_path, parse_git_status, render_markdown


class BillExecutionIntakeManifestTest(unittest.TestCase):
    def test_manifest_maps_firewalled_files_but_keeps_execution_locked(self):
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "categories": {"execution-live": 3},
                    "executionLiveFiles": [
                        "scripts/master_bridge.py",
                        "scripts/fund-and-trade.ts",
                        "scripts/pm_arb_scanner.py",
                    ],
                },
            },
            clearance={
                "status": "PASS",
                "results": [
                    {"id": "verify-master-bridge-firewall", "passed": True},
                    {"id": "verify-prediction-funding-firewall", "passed": True},
                    {"id": "verify-60m-bridge-firewall", "passed": True},
                    {"id": "verify-topstep-demo-bridge-firewall", "passed": True},
                    {"id": "verify-signal-router-firewall", "passed": True},
                    {"id": "verify-execution-quarantine", "passed": True},
                ],
            },
            git_status=parse_git_status(
                " M scripts/master_bridge.py\n"
                " M scripts/fund-and-trade.ts\n"
                " M scripts/pm_arb_scanner.py\n"
            ),
            diff_stats={
                "scripts/master_bridge.py": {"addedLines": 12, "deletedLines": 3},
                "scripts/fund-and-trade.ts": {"addedLines": 2, "deletedLines": 1},
            },
            cron_jobs=[
                {
                    "id": "cron-1",
                    "name": "master-strategy-bridge",
                    "script": "master_bridge.py",
                    "enabled": True,
                    "state": "scheduled",
                    "no_agent": True,
                    "last_status": "ok",
                },
                {
                    "id": "cron-2",
                    "name": "paused-pm-scanner",
                    "script": "pm_arb_scanner.py",
                    "enabled": True,
                    "state": "paused",
                    "no_agent": True,
                    "last_status": "ok",
                },
            ],
            generated_at="2026-05-30T00:00:00+00:00",
        )

        by_path = {item["relativePath"]: item for item in payload["items"]}
        self.assertEqual(by_path["scripts/master_bridge.py"]["classification"], "firewall-covered-still-quarantined")
        self.assertEqual(by_path["scripts/fund-and-trade.ts"]["classification"], "firewall-covered-still-quarantined")
        self.assertEqual(by_path["scripts/pm_arb_scanner.py"]["classification"], "firewall-covered-still-quarantined")
        self.assertNotIn("scripts/pm_arb_scanner.py", payload["uncoveredExecutionPaths"])
        self.assertEqual(payload["dirtyExecutionFileCount"], 3)
        self.assertEqual(payload["canonicalExecutionLiveDirtyCount"], 3)
        self.assertEqual(payload["executionAdjacentFileCount"], 3)
        self.assertEqual(payload["activeCronReferenceCount"], 1)
        self.assertEqual(payload["activeCronReferencePaths"], ["scripts/master_bridge.py"])
        self.assertEqual(len(payload["activeCronDiffReview"]), 1)
        self.assertEqual(payload["activeCronDiffReview"][0]["relativePath"], "scripts/master_bridge.py")
        self.assertEqual(payload["activeCronDiffReview"][0]["diffStats"]["addedLines"], 12)
        self.assertFalse(payload["activeCronDiffReview"][0]["safeAutomaticAction"])
        self.assertFalse(payload["activeCronDiffReview"][0]["readyForExecution"])
        self.assertEqual(by_path["scripts/master_bridge.py"]["activeCronReferenceCount"], 1)
        self.assertEqual(by_path["scripts/master_bridge.py"]["activeCronReferences"][0]["name"], "master-strategy-bridge")
        self.assertFalse(by_path["scripts/pm_arb_scanner.py"]["activeCronReferences"])
        self.assertTrue(payload["executionLocked"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])
        self.assertFalse(payload["readyForExecution"])
        self.assertIn("npm run --silent bill:verify-master-bridge-firewall", payload["nextCommands"])
        self.assertIn(
            "npm run --silent bill:clearance-evidence",
            payload["validationCommandSets"]["executionFirewallEvidence"],
        )
        self.assertIn("npm run --silent bill:verify-execution-quarantine", payload["validationCommandSets"]["firewallEvidence"])
        self.assertIn("npm run --silent bill:cron-state-validator", payload["validationCommandSets"]["activeCronReferenceReview"])
        self.assertIn(
            "npm run --silent bill:clearance-evidence",
            payload["validationCommandSets"]["executionVisibilityRefresh"],
        )

    def test_manifest_marks_failed_firewall_as_blocked(self):
        payload = build_manifest(
            worktree={"canonicalSource": {"executionLiveFiles": ["scripts/60m_exec_bridge.py"]}},
            clearance={"status": "BLOCKED", "results": [{"id": "verify-60m-bridge-firewall", "passed": False}]},
            git_status={"scripts/60m_exec_bridge.py": "M"},
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["items"][0]["classification"], "firewall-missing-or-failed")
        self.assertFalse(payload["allFirewallCommandsPassed"])

    def test_manifest_ignores_self_reviewed_read_only_manifest_paths(self):
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "categories": {"execution-live": 1},
                    "executionLiveFiles": [
                        "scripts/bill_execution_intake_manifest.py",
                        "tests/test_bill_execution_intake_manifest.py",
                    ],
                },
            },
            clearance={"status": "PASS", "results": []},
            git_status=parse_git_status(
                "?? scripts/bill_execution_intake_manifest.py\n"
                "?? tests/test_bill_execution_intake_manifest.py\n"
            ),
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["uncoveredExecutionPaths"], [])
        self.assertEqual(payload["executionAdjacentFileCount"], 0)

    def test_read_only_topstep_market_data_proofs_are_not_uncovered_execution_routes(self):
        payload = build_manifest(
            worktree={"canonicalSource": {"executionLiveFiles": []}},
            clearance={"status": "PASS", "results": []},
            git_status=parse_git_status(
                "?? scripts/topstep_market_data_smoke.py\n"
                "?? scripts/topstep_readonly_bar_archive.py\n"
                "?? scripts/topstep_broker_local_bar_parity.py\n"
                "?? scripts/topstep_realtime_proof.py\n"
                "?? scripts/topstepx_dashboard_screen_proof.py\n"
            ),
            generated_at="2026-06-02T00:00:00+00:00",
        )

        by_path = {item["relativePath"]: item for item in payload["items"]}
        self.assertEqual(
            by_path["scripts/topstep_market_data_smoke.py"]["classification"],
            "read-only-broker-evidence-review",
        )
        self.assertEqual(
            by_path["scripts/topstep_readonly_bar_archive.py"]["classification"],
            "read-only-broker-evidence-review",
        )
        self.assertEqual(
            by_path["scripts/topstep_broker_local_bar_parity.py"]["classification"],
            "read-only-broker-evidence-review",
        )
        self.assertEqual(
            by_path["scripts/topstep_realtime_proof.py"]["classification"],
            "read-only-broker-evidence-review",
        )
        self.assertEqual(
            by_path["scripts/topstepx_dashboard_screen_proof.py"]["classification"],
            "read-only-broker-evidence-review",
        )
        self.assertEqual(payload["uncoveredExecutionPaths"], [])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["movesFunds"])

    def test_read_only_topstep_daily_learning_is_not_an_uncovered_route(self):
        payload = build_manifest(
            worktree={"canonicalSource": {"executionLiveFiles": []}},
            clearance={"status": "PASS", "results": []},
            git_status=parse_git_status("M  scripts/topstep_daily_learning.py\n"),
            generated_at="2026-06-02T00:00:00+00:00",
        )

        item = payload["items"][0]
        self.assertEqual(item["relativePath"], "scripts/topstep_daily_learning.py")
        self.assertEqual(item["classification"], "read-only-broker-evidence-review")
        self.assertEqual(payload["uncoveredExecutionPaths"], [])
        self.assertFalse(item["writesOrders"])
        self.assertFalse(item["touchesBroker"])

    def test_cron_verifier_wrappers_are_reviewed_but_not_uncovered_routes(self):
        payload = build_manifest(
            worktree={"canonicalSource": {"executionLiveFiles": []}},
            clearance={"status": "PASS", "results": []},
            git_status=parse_git_status(
                "?? scripts/cron_verify_execution_quarantine.sh\n"
                "?? scripts/cron_verify_master_bridge.sh\n"
                "?? scripts/cron_verify_no_execution.sh\n"
                "?? scripts/cron_verify_topstep_demo.sh\n"
            ),
            cron_jobs=[
                {
                    "id": "cron-verify",
                    "name": "verify-execution-quarantine",
                    "script": "/Users/brain/hedge/scripts/cron_verify_execution_quarantine.sh",
                    "enabled": True,
                    "state": "scheduled",
                    "no_agent": True,
                    "last_status": "ok",
                },
            ],
            generated_at="2026-06-04T00:00:00+00:00",
        )

        by_path = {item["relativePath"]: item for item in payload["items"]}
        for rel in [
            "scripts/cron_verify_execution_quarantine.sh",
            "scripts/cron_verify_master_bridge.sh",
            "scripts/cron_verify_no_execution.sh",
            "scripts/cron_verify_topstep_demo.sh",
        ]:
            self.assertEqual(by_path[rel]["classification"], "execution-verifier-wrapper-review")
            self.assertFalse(by_path[rel]["readyForExecution"])
            self.assertFalse(by_path[rel]["writesOrders"])
            self.assertFalse(by_path[rel]["touchesBroker"])
        self.assertEqual(payload["uncoveredExecutionPaths"], [])
        self.assertEqual(payload["activeCronReferencePaths"], ["scripts/cron_verify_execution_quarantine.sh"])

    def test_read_only_control_posture_scripts_are_not_uncovered_routes(self):
        payload = build_manifest(
            worktree={"canonicalSource": {"executionLiveFiles": []}},
            clearance={"status": "PASS", "results": []},
            git_status=parse_git_status(
                "?? scripts/topstep_demo_observation_posture.py\n"
                "?? scripts/topstep_session_safety_clearance.py\n"
            ),
            generated_at="2026-06-04T00:00:00+00:00",
        )

        by_path = {item["relativePath"]: item for item in payload["items"]}
        for rel in [
            "scripts/topstep_demo_observation_posture.py",
            "scripts/topstep_session_safety_clearance.py",
        ]:
            self.assertEqual(by_path[rel]["classification"], "read-only-control-evidence-review")
            self.assertNotIn(rel, payload["uncoveredExecutionPaths"])
            self.assertFalse(by_path[rel]["readyForExecution"])
            self.assertFalse(by_path[rel]["writesOrders"])
            self.assertFalse(by_path[rel]["touchesBroker"])

    def test_dom_edge_bridge_is_research_shadow_not_manual_route(self):
        payload = build_manifest(
            worktree={"canonicalSource": {"executionLiveFiles": []}},
            clearance={"status": "PASS", "results": []},
            git_status=parse_git_status("M  scripts/dom_edge_bridge.py\n"),
            generated_at="2026-06-04T00:00:00+00:00",
        )

        item = payload["items"][0]
        self.assertEqual(item["relativePath"], "scripts/dom_edge_bridge.py")
        self.assertEqual(item["classification"], "research-shadow-bridge-review")
        self.assertEqual(payload["uncoveredExecutionPaths"], [])
        self.assertFalse(item["readyForExecution"])
        self.assertFalse(item["writesOrders"])
        self.assertFalse(item["touchesBroker"])

    def test_prediction_execution_gates_are_covered_by_prediction_firewall(self):
        payload = build_manifest(
            worktree={"canonicalSource": {"executionLiveFiles": []}},
            clearance={
                "status": "PASS",
                "results": [{"id": "verify-prediction-funding-firewall", "passed": True}],
            },
            git_status=parse_git_status(
                "M  src/prediction/execution/authorization.ts\n"
                "M  src/prediction/execution/liveGate.ts\n"
            ),
            generated_at="2026-06-02T00:00:00+00:00",
        )

        by_path = {item["relativePath"]: item for item in payload["items"]}
        for rel in [
            "src/prediction/execution/authorization.ts",
            "src/prediction/execution/liveGate.ts",
        ]:
            self.assertEqual(by_path[rel]["classification"], "firewall-covered-still-quarantined")
            self.assertEqual(by_path[rel]["firewallId"], "verify-prediction-funding-firewall")
            self.assertTrue(by_path[rel]["firewallPassed"])
        self.assertEqual(payload["uncoveredExecutionPaths"], [])

    def test_topstep_compliance_policy_file_is_covered_by_execution_quarantine(self):
        payload = build_manifest(
            worktree={"canonicalSource": {"executionLiveFiles": []}},
            clearance={
                "status": "PASS",
                "results": [{"id": "verify-execution-quarantine", "passed": True}],
            },
            git_status=parse_git_status("M  src/risk/topstepCompliance.ts\n"),
            generated_at="2026-06-02T00:00:00+00:00",
        )

        item = payload["items"][0]
        self.assertEqual(item["relativePath"], "src/risk/topstepCompliance.ts")
        self.assertEqual(item["classification"], "firewall-covered-still-quarantined")
        self.assertEqual(item["firewallId"], "verify-execution-quarantine")
        self.assertTrue(item["firewallPassed"])
        self.assertEqual(payload["uncoveredExecutionPaths"], [])

    def test_projectx_adapter_is_covered_by_execution_quarantine(self):
        payload = build_manifest(
            worktree={"canonicalSource": {"executionLiveFiles": []}},
            clearance={
                "status": "PASS",
                "results": [{"id": "verify-execution-quarantine", "passed": True}],
            },
            git_status=parse_git_status("M  src/adapters/projectx/projectxAdapter.ts\n"),
            generated_at="2026-06-03T00:00:00+00:00",
        )

        item = payload["items"][0]
        self.assertEqual(item["relativePath"], "src/adapters/projectx/projectxAdapter.ts")
        self.assertEqual(item["classification"], "firewall-covered-still-quarantined")
        self.assertEqual(item["firewallId"], "verify-execution-quarantine")
        self.assertTrue(item["firewallPassed"])
        self.assertEqual(payload["uncoveredExecutionPaths"], [])

    def test_markdown_never_approves_routing(self):
        payload = {
            "decision": "execution-intake-visible-execution-locked",
            "executionLocked": True,
            "dirtyExecutionFileCount": 1,
            "activeCronReferenceCount": 1,
            "activeCronReferencePaths": ["scripts/master_bridge.py"],
            "activeCronDiffReview": [
                {
                    "relativePath": "scripts/master_bridge.py",
                    "gitStatus": "M",
                    "classification": "firewall-covered-still-quarantined",
                    "firewallId": "verify-master-bridge-firewall",
                    "firewallPassed": True,
                    "diffStats": {"addedLines": 12, "deletedLines": 3},
                    "operatorAction": "Manual operator review required.",
                    "safeAutomaticAction": False,
                    "activeCronReferences": [
                        {
                            "id": "cron-1",
                            "name": "master-strategy-bridge",
                            "enabled": True,
                            "state": "scheduled",
                            "safeAutomaticAction": False,
                        }
                    ],
                }
            ],
            "firewallEvidenceStatus": "PASS",
            "allFirewallCommandsPassed": True,
            "classificationCounts": {"firewall-covered-still-quarantined": 1},
            "uncoveredExecutionPaths": [],
            "nextCommands": ["npm run --silent bill:execution-intake-manifest"],
            "validationCommandSets": {
                "firewallEvidence": ["npm run --silent bill:verify-master-bridge-firewall"],
                "executionVisibilityRefresh": ["npm run --silent bill:execution-intake-manifest"],
                "operatorRead": "review only",
            },
            "items": [
                {
                    "relativePath": "scripts/master_bridge.py",
                    "gitStatus": "M",
                    "classification": "firewall-covered-still-quarantined",
                    "firewallId": "verify-master-bridge-firewall",
                    "firewallPassed": True,
                    "readyForExecution": False,
                    "activeCronReferenceCount": 1,
                    "activeCronReferences": [
                        {
                            "id": "cron-1",
                            "name": "master-strategy-bridge",
                            "enabled": True,
                            "noAgent": True,
                            "lastStatus": "ok",
                        }
                    ],
                }
            ],
            "hardRules": ["Firewall-covered does not mean source-clean or execution-approved."],
        }

        markdown = render_markdown(payload)

        self.assertIn("does not approve routing, sizing, funding, orders, or broker access", markdown)
        self.assertIn("Active cron references to dirty execution files", markdown)
        self.assertIn("Active Cron Diff Review", markdown)
        self.assertIn("Diff stats", markdown)
        self.assertIn("master-strategy-bridge", markdown)
        self.assertIn("## Next Commands", markdown)
        self.assertIn("## Validation Command Sets", markdown)
        self.assertIn("Firewall-covered does not mean source-clean or execution-approved.", markdown)

    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^bill-execution-intake-manifest-\d{4}-\d{2}-\d{2}\.md$")


if __name__ == "__main__":
    unittest.main()
