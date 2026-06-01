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
