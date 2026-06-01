import argparse
import unittest
from unittest.mock import patch

from scripts import bill_open_session_data_proof as proof


class BillOpenSessionDataProofTest(unittest.TestCase):
    def test_dry_run_keeps_execution_locked_and_skips_broker(self):
        with patch.object(proof, "summarize_state", return_value={
            "nextOpenSessionProofWindow": {
                "nextOpenUtc": "2026-05-31T22:00:00+00:00",
                "recommendedProofStartUtc": "2026-05-31T22:05:00+00:00",
                "recommendedProofEndUtc": "2026-05-31T22:35:00+00:00",
            },
            "databentoStatus": "NO_QUOTES_MARKET_CLOSED",
        }):
            payload = proof.build_payload(argparse.Namespace(run_data_only=False, timeout_sec=1.0))

        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["decision"], "data-only-proof-visible-execution-locked")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForLive"])
        self.assertFalse(payload["brokerReadOnlyStepIncluded"])
        self.assertEqual(payload["safeEnv"]["BILL_ENABLE_FUTURES_DEMO_EXECUTION"], "false")
        self.assertEqual(payload["safeEnv"]["RH_TOPSTEP_READ_ONLY"], "true")
        self.assertEqual(payload["safeEnv"]["RH_LIVE_EXECUTION_ENABLED"], "false")
        self.assertEqual(payload["executedSteps"], [])
        self.assertTrue(payload["allCommandsPassed"])
        self.assertFalse(payload["executionGradeDataProofPassed"])
        self.assertEqual(payload["nextOpenUtc"], "2026-05-31T22:00:00+00:00")
        self.assertEqual(payload["recommendedProofStartUtc"], "2026-05-31T22:05:00+00:00")
        self.assertEqual(payload["recommendedProofEndUtc"], "2026-05-31T22:35:00+00:00")
        self.assertTrue(any(
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false" in command
            and "RH_TOPSTEP_READ_ONLY=true" in command
            and "RH_LIVE_EXECUTION_ENABLED=false" in command
            and "npm run --silent bill:databento-realtime-smoke -- --timeout-sec 1.0" in command
            for command in payload["commands"]
        ))
        self.assertTrue(any(
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false" in command
            and "RH_TOPSTEP_READ_ONLY=true" in command
            and "RH_LIVE_EXECUTION_ENABLED=false" in command
            and "npm run --silent bill:databento-orderflow-feature-smoke -- --timeout-sec 1.0" in command
            for command in payload["commands"]
        ))
        self.assertIn(
            "BILL_DATABENTO_DATASET=GLBX.MDP3 BILL_DATABENTO_REALTIME_ENABLED=true BILL_DATABENTO_SCHEMA=mbp-1 BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false RH_TOPSTEP_READ_ONLY=true .venv/bin/python scripts/realtime_data_bridge.py --quiet --databento-only",
            payload["commands"],
        )
        self.assertIn("Databento smoke ran while CME Globex was closed; use the next open-session proof window.", payload["risks"])
        self.assertIn(
            "Databento order-flow feature smoke has not proved depth/imbalance features for DOM-proxy replacement.",
            payload["risks"],
        )
        self.assertEqual(
            payload["plannedStepIds"],
            [step["id"] for step in payload["plannedSteps"]],
        )
        self.assertIn("databento-open-session-smoke", [step["id"] for step in payload["plannedSteps"]])
        self.assertIn("databento-orderflow-feature-smoke", [step["id"] for step in payload["plannedSteps"]])
        self.assertIn("databento-open-session-bridge-write", [step["id"] for step in payload["plannedSteps"]])
        feature_step = next(step for step in payload["plannedSteps"] if step["id"] == "databento-orderflow-feature-smoke")
        self.assertTrue(feature_step["required"])
        self.assertIn("bill:databento-orderflow-feature-smoke", feature_step["command"])
        bridge_step = next(step for step in payload["plannedSteps"] if step["id"] == "databento-open-session-bridge-write")
        self.assertEqual(bridge_step["env"]["BILL_DATABENTO_REALTIME_ENABLED"], "true")
        self.assertEqual(bridge_step["env"]["BILL_ENABLE_FUTURES_DEMO_EXECUTION"], "false")
        self.assertEqual(bridge_step["env"]["RH_TOPSTEP_READ_ONLY"], "true")
        self.assertEqual(bridge_step["env"]["RH_LIVE_EXECUTION_ENABLED"], "false")
        self.assertIn(".venv/bin/python scripts/realtime_data_bridge.py --quiet --databento-only", bridge_step["command"])
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION=false", bridge_step["command"])
        self.assertFalse(bridge_step["required"])
        self.assertTrue(all(not step["writesOrders"] for step in payload["plannedSteps"]))
        self.assertTrue(all(not step["touchesBroker"] for step in payload["plannedSteps"]))

    def test_default_markdown_path_uses_current_utc_date(self):
        path = proof.default_markdown_path()

        self.assertEqual(path.parent, proof.HERMES)
        self.assertRegex(path.name, r"^bill-open-session-data-proof-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_surfaces_automation_contract(self):
        markdown = proof.render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "mode": "dry-run",
            "allCommandsPassed": True,
            "executionGradeDataProofPassed": False,
            "failedStepIds": [],
            "safeEnv": proof.SAFE_ENV,
            "stateSummary": {},
            "plannedSteps": [],
            "hardRules": [],
        })

        self.assertIn("## Automation Contract", markdown)
        self.assertIn("bill-open-session-data-proof", markdown)
        self.assertIn("Databento order-flow feature smoke", markdown)
        self.assertIn("must not submit orders", markdown)
        self.assertIn("# Bill Open-Session Data Proof - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_run_data_only_records_failed_required_step_without_touching_broker(self):
        def fake_run_step(step, *, env):
            return {
                "id": step["id"],
                "kind": step["kind"],
                "argv": step["argv"],
                "env": step.get("env", {}),
                "command": proof.format_command(step),
                "required": step["required"],
                "returncode": 1 if step["id"] == "databento-open-session-smoke" else 0,
                "passed": False if step["id"] == "databento-open-session-smoke" else True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
            }

        with patch.object(proof, "run_step", side_effect=fake_run_step), patch.object(proof, "summarize_state", return_value={}):
            payload = proof.build_payload(argparse.Namespace(run_data_only=True, timeout_sec=1.0))

        self.assertEqual(payload["mode"], "run-data-only")
        self.assertFalse(payload["allCommandsPassed"])
        self.assertFalse(payload["executionGradeDataProofPassed"])
        self.assertEqual(payload["failedStepIds"], ["databento-open-session-smoke"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])
        self.assertTrue(all(not step["touchesBroker"] for step in payload["executedSteps"]))

    def test_data_proof_flag_requires_realtime_preflight_and_databento_proof(self):
        with patch.object(proof, "summarize_state", return_value={
            "readyForExecutionData": True,
            "databentoReadyForExecutionDataProof": True,
        }):
            payload = proof.build_payload(argparse.Namespace(run_data_only=False, timeout_sec=1.0))

        self.assertTrue(payload["executionGradeDataProofPassed"])
        self.assertEqual(payload["decision"], "execution-grade-data-proof-passed")


if __name__ == "__main__":
    unittest.main()
