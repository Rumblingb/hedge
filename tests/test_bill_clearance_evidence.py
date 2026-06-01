import unittest

from scripts.bill_clearance_evidence import LOCKED_ENV_FLAGS, default_commands, render_markdown, tail_text


class BillClearanceEvidenceTest(unittest.TestCase):
    def test_default_commands_are_safe_control_plane_checks(self):
        commands = default_commands(include_slow_tests=True)
        command_text = [" ".join(item.command) for item in commands]

        self.assertIn("npm run --silent typecheck", command_text)
        self.assertIn("npm run --silent test", command_text)
        self.assertIn(
            ".venv/bin/python -m unittest tests.test_bill_open_session_data_proof tests.test_bill_source_hygiene_plan tests.test_bill_source_packet_review tests.test_bill_next_research_actions tests.test_bill_goal_completion_audit tests.test_codex_automation_audit tests.test_bill_clearance_evidence -v",
            command_text,
        )
        self.assertIn("npm run --silent bill:verify-master-bridge-firewall", command_text)
        self.assertIn("npm run --silent bill:verify-prediction-funding-firewall", command_text)
        self.assertIn("npm run --silent bill:verify-execution-quarantine", command_text)
        self.assertIn("npm run --silent bill:source-intake-manifest", command_text)
        self.assertIn("npm run --silent bill:source-hygiene-plan", command_text)
        self.assertIn("npm run --silent bill:source-packet-review", command_text)
        self.assertIn("npm run --silent bill:stale-strategy-claim-guard", command_text)
        self.assertIn("npm run --silent bill:open-session-data-proof -- --run-data-only", command_text)
        self.assertIn("npm run --silent bill:next-research-actions", command_text)
        self.assertIn("npm run --silent bill:codex-automation-audit", command_text)
        self.assertIn("npm run --silent bill:goal-completion-audit", command_text)
        self.assertFalse(any("execute" in text and "verify" not in text for text in command_text))
        live = next(item for item in commands if item.id == "live-readiness-gate")
        self.assertIn(2, live.expectedReturnCodes)

    def test_skip_slow_tests_removes_full_suite_only(self):
        command_text = [" ".join(item.command) for item in default_commands(include_slow_tests=False)]

        self.assertNotIn("npm run --silent test", command_text)
        self.assertIn("npm run --silent typecheck", command_text)
        self.assertIn("npm run --silent bill:open-session-data-proof -- --run-data-only", command_text)

    def test_tail_text_keeps_suffix(self):
        self.assertEqual(tail_text("abcdef", 3), "def")

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
            "hardRules": ["Passing clearance evidence does not approve trading."],
        })

        self.assertIn("Ready for execution: `False`", markdown)
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION: `false`", markdown)
        self.assertIn("RH_TOPSTEP_READ_ONLY: `true`", markdown)
        self.assertIn("RH_LIVE_EXECUTION_ENABLED: `false`", markdown)
        self.assertIn("source tree has uncommitted source changes", markdown)


if __name__ == "__main__":
    unittest.main()
