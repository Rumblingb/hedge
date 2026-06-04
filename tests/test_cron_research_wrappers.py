import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = [
    ROOT / "scripts/cron_brain_tick.sh",
    ROOT / "scripts/cron_verify_execution_quarantine.sh",
    ROOT / "scripts/cron_verify_master_bridge.sh",
    ROOT / "scripts/cron_verify_no_execution.sh",
    ROOT / "scripts/cron_verify_topstep_demo.sh",
]


class CronResearchWrappersTest(unittest.TestCase):
    def test_cron_wrappers_keep_execution_locks(self):
        for path in WRAPPERS:
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertIn("set -euo pipefail", text)
                self.assertIn("export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false", text)
                self.assertIn("export RH_TOPSTEP_READ_ONLY=true", text)
                self.assertIn("export RH_LIVE_EXECUTION_ENABLED=false", text)
                self.assertIn("export PREDICTION_LIVE_EXECUTION_ENABLED=false", text)
                self.assertNotIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION=true", text)
                self.assertNotIn("RH_LIVE_EXECUTION_ENABLED=true", text)

    def test_cron_wrappers_do_not_route_orders_or_move_funds(self):
        forbidden = [
            "place_order",
            "submit_order",
            "send_order",
            "route_order",
            "withdraw",
            "deposit",
            "transfer_funds",
            "BILL_ROUTE_APPROVAL=APPROVED",
        ]
        for path in WRAPPERS:
            text = path.read_text().lower()
            with self.subTest(path=path.name):
                for term in forbidden:
                    self.assertNotIn(term.lower(), text)


if __name__ == "__main__":
    unittest.main()
