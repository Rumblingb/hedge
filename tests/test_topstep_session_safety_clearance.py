import unittest

from scripts.topstep_session_safety_clearance import build_clearance


class TopstepSessionSafetyClearanceTests(unittest.TestCase):
    def test_clearance_requires_operator_confirmation_even_when_machine_checks_pass(self):
        payload = build_clearance(
            session_safety={
                "pauseBrokerTouchingProofs": True,
                "reason": "multiple sessions",
                "safeUntil": "operator-confirms-topstep-session-warning-cleared",
            },
            automation_audit={
                "activeBillAutomationCount": 3,
                "blockers": [],
                "automations": [
                    {
                        "billRelated": True,
                        "active": True,
                        "forbidsExecution": True,
                        "hasSafeLocks": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    }
                ],
            },
            cron_validator={
                "blockingIssueCount": 0,
                "activeTopstepBrokerSessionCronRefs": 0,
                "activeTradingAgentBacked": 0,
            },
            no_execution_processes={
                "ok": True,
                "candidateCount": 0,
                "unsafeCount": 0,
            },
        )

        self.assertEqual("operator-confirmation-required", payload["decision"])
        self.assertTrue(payload["machineChecksPassed"])
        self.assertTrue(payload["operatorConfirmationRequired"])
        self.assertFalse(payload["readyForReadOnlyProofWindow"])
        self.assertFalse(payload["mayOpenBrokerSession"])
        self.assertIn("operator-confirms-topstep-warning-cleared", payload["blockers"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])

    def test_clearance_blocks_on_unsafe_processes(self):
        payload = build_clearance(
            session_safety={"pauseBrokerTouchingProofs": False, "operatorConfirmedTopstepWarningCleared": True},
            automation_audit={"blockers": [], "automations": []},
            cron_validator={"blockingIssueCount": 0, "activeTopstepBrokerSessionCronRefs": 0, "activeTradingAgentBacked": 0},
            no_execution_processes={"ok": False, "candidateCount": 1, "unsafeCount": 1},
        )

        self.assertFalse(payload["machineChecksPassed"])
        self.assertFalse(payload["readyForReadOnlyProofWindow"])
        self.assertIn("no-execution-processes", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
