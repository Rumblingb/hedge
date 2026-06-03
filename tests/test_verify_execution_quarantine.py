import unittest
from pathlib import Path

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
        self.assertIn("src/adapters/projectx/projectxAdapter.ts", report["checkedPaths"])
        by_id = {check["id"]: check for check in report["checks"]}
        self.assertTrue(by_id["projectx-adapter-demo-only-guards-before-broker-write"]["passed"])
        self.assertTrue(by_id["strategy-runner-reboot-fail-closed"]["passed"])
        self.assertTrue(by_id["command-center-reboot-fail-closed"]["passed"])
        self.assertIn("ops/mac-mini/bin/bill-strategy-engine-runner", report["checkedPaths"])
        self.assertIn("ops/mac-mini/bin/bill-command-center", report["checkedPaths"])

    def test_source_check_detects_forbidden_order_patterns(self):
        check = source_check(
            check_id="synthetic",
            relative="scripts/position_sizing_engine.py",
            required=["OUTPUT_NAME"],
            forbidden=[r"OUTPUT_NAME"],
        )

        self.assertFalse(check.passed)
        self.assertIn("forbidden", check.evidence)

    def test_strategy_runner_forces_execution_locks_after_env_load(self):
        wrapper = Path("ops/mac-mini/bin/bill-strategy-engine-runner").read_text()
        template = Path("ops/mac-mini/launchd/com.agentpay.bill.strategy-engine-runner.plist.template").read_text()

        env_load_pos = wrapper.index("load_bill_env")
        futures_lock_pos = wrapper.index("export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false")
        readonly_lock_pos = wrapper.index("export RH_TOPSTEP_READ_ONLY=true")
        live_lock_pos = wrapper.index("export RH_LIVE_EXECUTION_ENABLED=false")
        exec_pos = wrapper.index('exec "$(bill_tsx)" src/engine/strategyEngineRunner.ts')

        self.assertLess(env_load_pos, futures_lock_pos)
        self.assertLess(futures_lock_pos, readonly_lock_pos)
        self.assertLess(readonly_lock_pos, live_lock_pos)
        self.assertLess(live_lock_pos, exec_pos)
        self.assertIn("<key>BILL_ENABLE_FUTURES_DEMO_EXECUTION</key>", template)
        self.assertIn("<key>RH_TOPSTEP_READ_ONLY</key>", template)
        self.assertIn("<key>RH_LIVE_EXECUTION_ENABLED</key>", template)

    def test_command_center_forces_execution_locks_after_env_load(self):
        wrapper = Path("ops/mac-mini/bin/bill-command-center").read_text()
        template = Path("ops/mac-mini/launchd/com.agentpay.bill.command-center.plist.template").read_text()
        installer = Path("ops/mac-mini/bin/bill-install-launchd").read_text()

        env_load_pos = wrapper.index("load_bill_env")
        futures_lock_pos = wrapper.index("export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false")
        readonly_lock_pos = wrapper.index("export RH_TOPSTEP_READ_ONLY=true")
        live_lock_pos = wrapper.index("export RH_LIVE_EXECUTION_ENABLED=false")
        exec_pos = wrapper.index("exec python3 command_center_server.py")

        self.assertLess(env_load_pos, futures_lock_pos)
        self.assertLess(futures_lock_pos, readonly_lock_pos)
        self.assertLess(readonly_lock_pos, live_lock_pos)
        self.assertLess(live_lock_pos, exec_pos)
        self.assertIn("<key>RunAtLoad</key>", template)
        self.assertIn("<key>KeepAlive</key>", template)
        self.assertIn("<key>BILL_ENABLE_FUTURES_DEMO_EXECUTION</key>", template)
        self.assertIn("<key>RH_TOPSTEP_READ_ONLY</key>", template)
        self.assertIn("<key>RH_LIVE_EXECUTION_ENABLED</key>", template)
        self.assertIn("com.agentpay.bill.command-center", installer)


if __name__ == "__main__":
    unittest.main()
