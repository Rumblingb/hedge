import unittest

from scripts.verify_no_execution_enabled_processes import ProcessRow, classify, redact_command


class VerifyNoExecutionProcessesTest(unittest.TestCase):
    def test_flags_execution_enabled_strategy_runner(self):
        report = classify([
            ProcessRow(
                pid=123,
                command=(
                    "node src/engine/strategyEngineRunner.ts "
                    "BILL_ENABLE_FUTURES_DEMO_EXECUTION=true RH_TOPSTEP_READ_ONLY=false"
                ),
            )
        ])
        self.assertFalse(report["ok"])
        self.assertEqual(report["unsafeCount"], 1)
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION=true", report["unsafe"][0]["unsafeReasons"])

    def test_safe_read_only_runner_is_reported_but_not_failed(self):
        report = classify([
            ProcessRow(
                pid=456,
                command=(
                    "python scripts/master_bridge.py "
                    "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false "
                    "RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false"
                ),
            )
        ])
        self.assertTrue(report["ok"])
        self.assertEqual(report["candidateCount"], 1)
        self.assertEqual(report["unsafeCount"], 0)
        self.assertIn("RH_TOPSTEP_READ_ONLY=true", report["candidates"][0]["safeEvidence"])

    def test_ignores_unrelated_processes_with_unsafe_env(self):
        report = classify([
            ProcessRow(
                pid=789,
                command="zsh BILL_ENABLE_FUTURES_DEMO_EXECUTION=true RH_TOPSTEP_READ_ONLY=false",
            )
        ])
        self.assertTrue(report["ok"])
        self.assertEqual(report["candidateCount"], 0)

    def test_candidate_command_tail_redacts_unrelated_api_keys(self):
        report = classify([
            ProcessRow(
                pid=321,
                command=(
                    "ANTHROPIC_API_KEY=sk-ant-secretvalue123456789 "
                    "BILL_CLOUD_API_KEY=nvapi-secretvalue123456789 "
                    "python scripts/master_bridge.py "
                    "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false "
                    "RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false"
                ),
            )
        ])

        tail = report["candidates"][0]["commandTail"]
        self.assertIn("ANTHROPIC_API_KEY=<redacted>", tail)
        self.assertIn("BILL_CLOUD_API_KEY=<redacted>", tail)
        self.assertNotIn("sk-ant-secretvalue", tail)
        self.assertNotIn("nvapi-secretvalue", tail)
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION=false", tail)
        self.assertIn("RH_TOPSTEP_READ_ONLY=true", tail)

    def test_redact_command_preserves_unsafe_execution_markers(self):
        redacted = redact_command(
            "API_TOKEN=abc123secret python scripts/topstep_demo_bridge.py "
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=true RH_TOPSTEP_READ_ONLY=false"
        )

        self.assertIn("API_TOKEN=<redacted>", redacted)
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION=true", redacted)
        self.assertIn("RH_TOPSTEP_READ_ONLY=false", redacted)


if __name__ == "__main__":
    unittest.main()
