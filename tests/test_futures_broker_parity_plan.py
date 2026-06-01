import unittest
from datetime import datetime, timezone

from scripts.futures_broker_parity_plan import (
    HERMES,
    build_plan,
    default_daily_plan_path,
    default_markdown_path,
    next_globex_open,
    render_markdown,
)


class FuturesBrokerParityPlanTests(unittest.TestCase):
    def test_default_paths_use_current_utc_date(self):
        daily = default_daily_plan_path()
        markdown = default_markdown_path()

        self.assertEqual(daily.parent, HERMES / "daily")
        self.assertRegex(daily.name, r"^\d{4}-\d{2}-\d{2}-bill-trading-plan\.md$")
        self.assertEqual(markdown.parent, HERMES)
        self.assertRegex(markdown.name, r"^futures-broker-parity-plan-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "missingProofs": [],
            "readyForExecution": False,
            "readyForDemoExpansion": False,
            "nextOpenSessionProofWindow": {},
            "current": {},
            "proofSequence": [],
            "promotionRules": [],
        })

        self.assertIn("# Futures Broker Parity Plan - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_current_blockers_become_safe_missing_proofs(self):
        payload = build_plan(
            futures_data_requirements={
                "requirements": [
                    {"id": "nq-current-local-or-broker-parity", "status": "blocked"},
                    {"id": "nq-current-session-depth-for-demo", "status": "blocked"},
                    {"id": "futures-execution-grade-realtime", "status": "blocked"},
                ]
            },
            current_data_parity={
                "decision": "research-only-current-local-parity-ready",
                "brokerParityChecked": False,
            },
            realtime_preflight={
                "decision": "block-execution-data",
                "readyForExecutionData": False,
                "runtime": {
                    "cronWrapper": {
                        "usesVenvPython": True,
                        "forcesFuturesDemoDisabled": True,
                        "forcesTopstepReadOnly": True,
                        "forcesLiveExecutionDisabled": True,
                    }
                },
                "dataSources": {
                    "databentoLive": {
                        "safeDataOnlyCommand": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false .venv/bin/python scripts/realtime_data_bridge.py --quiet"
                    }
                },
            },
            databento_smoke={"status": "NO_QUOTES_MARKET_CLOSED", "readyForExecutionDataProof": False},
            topstep_monitor={
                "status": "OK",
                "broker_reconciliation": {"broker_flat": True, "open_positions": 0},
            },
            daily_plan_text="BILL_ROUTE_APPROVAL: BLOCKED\n",
        )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["decision"], "research-only-futures-broker-parity-not-cleared")
        self.assertIn("broker-reconciled-current-nq-bars", payload["missingProofs"])
        self.assertIn("current-session-depth-from-broker-relevant-source", payload["missingProofs"])
        self.assertIn("open-session-execution-grade-realtime-proof", payload["missingProofs"])
        commands = " ".join(command for step in payload["proofSequence"] for command in step["commands"])
        self.assertIn("RH_TOPSTEP_READ_ONLY=true", commands)
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION=false", commands)
        self.assertIn("RH_LIVE_EXECUTION_ENABLED=false", commands)
        self.assertIn("nextOpenSessionProofWindow", payload)
        self.assertTrue(payload["nextOpenSessionProofWindow"]["commandsAreDataOnly"])
        self.assertIn("openSessionDataOnlyProof", payload["validationCommandSets"])
        self.assertIn("readOnlyBrokerReconciliation", payload["validationCommandSets"])
        self.assertIn(
            "npm run --silent bill:databento-realtime-smoke -- --timeout-sec 20",
            payload["validationCommandSets"]["openSessionDataOnlyProof"],
        )

    def test_missing_route_lock_is_a_blocker(self):
        payload = build_plan(
            futures_data_requirements={"requirements": []},
            current_data_parity={"decision": "research-only-current-local-parity-ready", "brokerParityChecked": True},
            realtime_preflight={
                "readyForExecutionData": True,
                "runtime": {
                    "cronWrapper": {
                        "usesVenvPython": True,
                        "forcesFuturesDemoDisabled": True,
                        "forcesTopstepReadOnly": True,
                        "forcesLiveExecutionDisabled": True,
                    }
                },
            },
            databento_smoke={"readyForExecutionDataProof": True},
            topstep_monitor={"broker_reconciliation": {"broker_flat": True, "open_positions": 0}},
            daily_plan_text="",
        )

        self.assertIn("daily-plan-route-lock-not-confirmed", payload["missingProofs"])
        self.assertFalse(payload["readyForDemoExpansion"])

    def test_next_globex_open_schedules_sunday_from_saturday(self):
        payload = next_globex_open(datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc))

        self.assertFalse(payload["session"]["likelyOpen"])
        self.assertEqual(payload["session"]["reason"], "Saturday Globex closure")
        self.assertEqual(payload["nextOpenUtc"], "2026-05-31T22:00:00+00:00")
        self.assertEqual(payload["recommendedProofStartUtc"], "2026-05-31T22:05:00+00:00")


if __name__ == "__main__":
    unittest.main()
