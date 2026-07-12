from unittest import mock
import unittest

from scripts.bill_clearance_evidence import LOCKED_ENV_FLAGS, build_report, default_commands, render_markdown, summarize_prop_firm_payout_plan, tail_text


class BillClearanceEvidenceTest(unittest.TestCase):
    def test_default_commands_are_safe_control_plane_checks(self):
        commands = default_commands(include_slow_tests=True)
        command_text = [" ".join(item.command) for item in commands]

        self.assertIn("npm run --silent typecheck", command_text)
        self.assertIn("npm run --silent test", command_text)
        self.assertIn(
            ".venv/bin/python -m unittest tests.test_bill_open_session_data_proof tests.test_bill_source_hygiene_plan tests.test_bill_source_packet_review tests.test_bill_next_research_actions tests.test_bill_goal_completion_audit tests.test_codex_automation_audit tests.test_bill_clearance_evidence tests.test_verify_no_execution_processes -v",
            command_text,
        )
        self.assertIn("npm run --silent bill:verify-master-bridge-firewall", command_text)
        self.assertIn("npm run --silent bill:verify-prediction-funding-firewall", command_text)
        self.assertIn("npm run --silent bill:verify-no-execution-processes", command_text)
        self.assertIn("npm run --silent bill:verify-execution-quarantine", command_text)
        self.assertIn("npm run --silent bill:source-intake-manifest", command_text)
        self.assertIn("npm run --silent bill:source-hygiene-plan", command_text)
        self.assertIn("npm run --silent bill:source-packet-review", command_text)
        self.assertIn("npm run --silent bill:stale-strategy-claim-guard", command_text)
        self.assertIn("npm run --silent bill:open-session-data-proof -- --run-data-only", command_text)
        self.assertIn("npm run --silent bill:futures-data-quality", command_text)
        self.assertIn("npm run --silent bill:prop-firm-payout-plan", command_text)
        self.assertIn("npm run --silent bill:next-research-actions", command_text)
        self.assertIn("npm run --silent bill:codex-automation-audit", command_text)
        self.assertIn("npm run --silent bill:goal-completion-audit", command_text)
        self.assertFalse(any("execute" in text and "verify" not in text for text in command_text))
        live = next(item for item in commands if item.id == "live-readiness-gate")
        self.assertIn(2, live.expectedReturnCodes)
        full_suite = next(item for item in commands if item.id == "test")
        self.assertGreaterEqual(full_suite.timeoutSec, 300)

    def test_skip_slow_tests_removes_full_suite_only(self):
        command_text = [" ".join(item.command) for item in default_commands(include_slow_tests=False)]

        self.assertNotIn("npm run --silent test", command_text)
        self.assertIn("npm run --silent typecheck", command_text)
        self.assertIn("npm run --silent bill:open-session-data-proof -- --run-data-only", command_text)

    def test_build_report_progress_can_skip_slow_suite(self):
        with mock.patch("scripts.bill_clearance_evidence.run_command") as run:
            run.side_effect = lambda spec: {
                "id": spec.id,
                "lane": spec.lane,
                "commandText": " ".join(spec.command),
                "durationSec": 0.01,
                "passed": True,
            }

            payload = build_report(include_slow_tests=False, progress=True)

        ids = [item["id"] for item in payload["results"]]
        self.assertNotIn("test", ids)
        self.assertIn("typecheck", ids)
        self.assertEqual(payload["status"], "PASS")
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["envFlags"], LOCKED_ENV_FLAGS)

    def test_tail_text_keeps_suffix(self):
        self.assertEqual(tail_text("abcdef", 3), "def")

    def test_summarize_prop_firm_payout_plan_requires_current_50k_policy(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text("""{
              "command": "prop-firm-payout-plan",
              "account": {
                "accountSize": "50K",
                "xfaStandardMaxPayoutCap": 2000,
                "xfaConsistencyMaxPayoutCap": 3000
              },
              "posture": "needs-evidence",
              "candidateCount": 12,
              "blockers": ["no-payout-builder-candidate"],
              "challengePath": {"preferredFundedPath": "xfa-standard"},
              "riskModes": {
                "challenge": {"executionInstrument": "MNQ"},
                "funded": {"executionInstrument": "MNQ"}
              }
            }""")

            summary = summarize_prop_firm_payout_plan(path)

        self.assertTrue(summary["currentPolicy"])
        self.assertEqual(summary["candidateCount"], 12)
        self.assertEqual(summary["challengeInstrument"], "MNQ")

    def test_summarize_prop_firm_payout_plan_flags_stale_policy(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text("""{
              "command": "prop-firm-payout-plan",
              "account": {
                "accountSize": "50K",
                "xfaStandardMaxPayoutCap": 5000,
                "xfaConsistencyMaxPayoutCap": 6000
              },
              "challengePath": {"preferredFundedPath": "xfa-consistency"},
              "riskModes": {
                "challenge": {"executionInstrument": "NQ"},
                "funded": {"executionInstrument": "MNQ"}
              }
            }""")

            summary = summarize_prop_firm_payout_plan(path)

        self.assertFalse(summary["currentPolicy"])
        self.assertEqual(summary["account"]["standardPayoutCap"], 5000)

    def test_render_markdown_preserves_locked_state(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-30T00:00:00+00:00",
            "status": "PASS",
            "readyForExecution": False,
            "envFlags": LOCKED_ENV_FLAGS,
            "results": [{
                "lane": "governance-risk",
                "commandText": "npm run --silent typecheck",
                "passed": True,
                "durationSec": 1.0,
            }],
            "liveReadiness": {
                "readyForLive": False,
                "readyForDemoExpansion": False,
                "blockers": ["source tree has uncommitted source changes"],
            },
            "propFirmPayoutPlan": {
                "currentPolicy": True,
                "posture": "needs-evidence",
                "candidateCount": 12,
                "blockers": ["no-payout-builder-candidate"],
                "challengeInstrument": "MNQ",
                "fundedInstrument": "MNQ",
                "preferredFundedPath": "xfa-standard",
            },
            "hardRules": ["Passing clearance evidence does not approve trading."],
        })

        self.assertIn("Ready for execution: `False`", markdown)
        self.assertIn("Current policy: `True`", markdown)
        self.assertIn("Challenge instrument: `MNQ`", markdown)
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION: `false`", markdown)
        self.assertIn("RH_TOPSTEP_READ_ONLY: `true`", markdown)
        self.assertIn("RH_LIVE_EXECUTION_ENABLED: `false`", markdown)
        self.assertIn("source tree has uncommitted source changes", markdown)


if __name__ == "__main__":
    unittest.main()
