import unittest

from scripts.verify_execution_quarantine import build_report, source_check


class VerifyExecutionQuarantineTest(unittest.TestCase):
    def test_report_is_research_only_and_passes_current_quarantine_checks(self):
        report = build_report()

        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["allChecksPassed"])
        self.assertFalse(report["writesOrders"])
        self.assertFalse(report["touchesBroker"])
        self.assertFalse(report["movesFunds"])
        self.assertFalse(report["readyForExecution"])
        self.assertIn("scripts/trade_journal.py", report["readOnlyBrokerObserverPaths"])
        self.assertIn("src/live/demoExecution.ts", report["checkedPaths"])

    def test_source_check_detects_forbidden_order_patterns(self):
        check = source_check(
            check_id="synthetic",
            relative="scripts/position_sizing_engine.py",
            required=["OUTPUT_NAME"],
            forbidden=[r"OUTPUT_NAME"],
        )

        self.assertFalse(check.passed)
        self.assertIn("forbidden", check.evidence)


if __name__ == "__main__":
    unittest.main()
