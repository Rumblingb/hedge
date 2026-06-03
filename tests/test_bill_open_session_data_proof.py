import argparse
import unittest
from unittest.mock import patch

from scripts import bill_open_session_data_proof as proof


class BillOpenSessionDataProofTest(unittest.TestCase):
    def setUp(self):
        self.session_safety = patch.object(proof, "topstep_session_safety_summary", return_value={
            "present": False,
            "pauseBrokerTouchingProofs": False,
            "reason": "missing",
            "safeUntil": "operator-confirms-topstep-session-warning-cleared",
        })
        self.session_safety_mock = self.session_safety.start()
        self.addCleanup(self.session_safety.stop)

    def test_dry_run_keeps_execution_locked_and_plans_readonly_broker_archive(self):
        with patch.object(proof, "summarize_state", return_value={
            "nextOpenSessionProofWindow": {
                "nextOpenUtc": "2026-05-31T22:00:00+00:00",
                "recommendedProofStartUtc": "2026-05-31T22:05:00+00:00",
                "recommendedProofEndUtc": "2026-05-31T22:35:00+00:00",
            },
            "databentoStatus": "NO_QUOTES_MARKET_CLOSED",
            "topstepReadonlyBarArchiveReadyForResearchDepth": False,
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
        self.assertTrue(payload["brokerReadOnlyStepIncluded"])
        self.assertEqual(payload["brokerReadOnlyStepMode"], "read-only-market-data-archive")
        self.assertIsNone(payload["brokerReadOnlyStepSkippedReason"])
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
            and "npm run --silent bill:topstep-realtime-proof" in command
            for command in payload["commands"]
        ))
        self.assertTrue(any(
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false" in command
            and "RH_TOPSTEP_READ_ONLY=true" in command
            and "RH_LIVE_EXECUTION_ENABLED=false" in command
            and "npm run --silent bill:topstep-realtime-bridge" in command
            for command in payload["commands"]
        ))
        self.assertFalse(payload["includeDatabentoOptionalProof"])
        self.assertIn("databento-open-session-smoke", payload["skippedOptionalStepIds"])
        self.assertFalse(any("bill:databento-realtime-smoke" in command for command in payload["commands"]))
        self.assertFalse(any("bill:databento-orderflow-feature-smoke" in command for command in payload["commands"]))
        self.assertFalse(any("--databento-only" in command for command in payload["commands"]))
        self.assertIn(
            "Databento proof is optional and disabled for this run; TopstepX/ProjectX is the primary data path.",
            payload["risks"],
        )
        self.assertIn(
            "Topstep read-only bar archive has not yet accumulated enough RTH sessions for promotion review.",
            payload["risks"],
        )
        self.assertEqual(
            payload["plannedStepIds"],
            [step["id"] for step in payload["plannedSteps"]],
        )
        self.assertIn("topstep-realtime-proof", [step["id"] for step in payload["plannedSteps"]])
        self.assertIn("topstep-realtime-bridge-write", [step["id"] for step in payload["plannedSteps"]])
        self.assertIn("topstep-readonly-bar-archive", [step["id"] for step in payload["plannedSteps"]])
        self.assertNotIn("databento-open-session-smoke", [step["id"] for step in payload["plannedSteps"]])
        self.assertNotIn("databento-orderflow-feature-smoke", [step["id"] for step in payload["plannedSteps"]])
        self.assertNotIn("databento-open-session-bridge-write", [step["id"] for step in payload["plannedSteps"]])
        topstep_step = next(step for step in payload["plannedSteps"] if step["id"] == "topstep-readonly-bar-archive")
        self.assertFalse(topstep_step["required"])
        self.assertTrue(topstep_step["touchesBroker"])
        self.assertEqual(topstep_step["brokerTouchMode"], "read-only-market-data")
        self.assertFalse(topstep_step["writesOrders"])
        self.assertIn("bill:topstep-readonly-bar-archive", topstep_step["command"])
        topstep_realtime_step = next(step for step in payload["plannedSteps"] if step["id"] == "topstep-realtime-proof")
        self.assertTrue(topstep_realtime_step["required"])
        self.assertTrue(topstep_realtime_step["touchesBroker"])
        self.assertEqual(topstep_realtime_step["brokerTouchMode"], "read-only-market-data")
        self.assertIn("bill:topstep-realtime-proof", topstep_realtime_step["command"])
        topstep_bridge_step = next(step for step in payload["plannedSteps"] if step["id"] == "topstep-realtime-bridge-write")
        self.assertTrue(topstep_bridge_step["required"])
        self.assertTrue(topstep_bridge_step["touchesBroker"])
        self.assertEqual(topstep_bridge_step["brokerTouchMode"], "read-only-market-data")
        self.assertIn("bill:topstep-realtime-bridge", topstep_bridge_step["command"])
        self.assertTrue(all(not step.get("optional") for step in payload["plannedSteps"]))
        self.assertTrue(all(not step["writesOrders"] for step in payload["plannedSteps"]))
        self.assertTrue(all(
            not step["touchesBroker"] or step["brokerTouchMode"] == "read-only-market-data"
            for step in payload["plannedSteps"]
        ))

    def test_optional_databento_proof_requires_explicit_flag(self):
        with patch.object(proof, "summarize_state", return_value={
            "nextOpenSessionProofWindow": {},
            "databentoStatus": "NO_QUOTES_MARKET_CLOSED",
            "topstepReadonlyBarArchiveReadyForResearchDepth": True,
        }):
            payload = proof.build_payload(argparse.Namespace(
                run_data_only=False,
                timeout_sec=1.0,
                include_databento_optional_proof=True,
            ))

        self.assertTrue(payload["includeDatabentoOptionalProof"])
        self.assertEqual(payload["skippedOptionalStepIds"], [])
        self.assertIn("databento-open-session-smoke", [step["id"] for step in payload["plannedSteps"]])
        self.assertIn("databento-orderflow-feature-smoke", [step["id"] for step in payload["plannedSteps"]])
        self.assertIn("databento-open-session-bridge-write", [step["id"] for step in payload["plannedSteps"]])
        self.assertIn("Databento smoke ran while CME Globex was closed; use the next open-session proof window.", payload["risks"])
        self.assertIn(
            "Databento order-flow feature smoke has not proved depth/imbalance features for DOM-proxy replacement.",
            payload["risks"],
        )
        feature_step = next(step for step in payload["plannedSteps"] if step["id"] == "databento-orderflow-feature-smoke")
        self.assertFalse(feature_step["required"])
        self.assertTrue(feature_step["optional"])
        self.assertIn("bill:databento-orderflow-feature-smoke", feature_step["command"])
        bridge_step = next(step for step in payload["plannedSteps"] if step["id"] == "databento-open-session-bridge-write")
        self.assertEqual(bridge_step["env"]["BILL_DATABENTO_REALTIME_ENABLED"], "true")
        self.assertEqual(bridge_step["env"]["BILL_ENABLE_FUTURES_DEMO_EXECUTION"], "false")
        self.assertEqual(bridge_step["env"]["RH_TOPSTEP_READ_ONLY"], "true")
        self.assertEqual(bridge_step["env"]["RH_LIVE_EXECUTION_ENABLED"], "false")
        self.assertIn(".venv/bin/python scripts/realtime_data_bridge.py --quiet --databento-only", bridge_step["command"])
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION=false", bridge_step["command"])
        self.assertFalse(bridge_step["required"])
        self.assertTrue(bridge_step["optional"])

    def test_topstep_session_safety_pause_skips_direct_broker_touching_steps(self):
        self.session_safety_mock.return_value = {
            "present": True,
            "pauseBrokerTouchingProofs": True,
            "reason": "Topstep reported multiple sessions",
            "safeUntil": "operator-confirms-topstep-session-warning-cleared",
        }
        with patch.object(proof, "summarize_state", return_value={
            "readyForExecutionData": True,
            "topstepRealtimeReadyForExecutionDataProof": True,
            "topstepReadonlyBarArchiveReadyForResearchDepth": False,
        }):
            payload = proof.build_payload(argparse.Namespace(
                run_data_only=True,
                timeout_sec=1.0,
                include_databento_optional_proof=False,
            ))

        self.assertTrue(payload["brokerTouchingProofsPaused"])
        self.assertIn("topstep-realtime-proof", payload["skippedBrokerTouchingStepIds"])
        self.assertIn("topstep-realtime-bridge-write", payload["skippedBrokerTouchingStepIds"])
        self.assertIn("topstep-readonly-bar-archive", payload["skippedBrokerTouchingStepIds"])
        self.assertFalse(any(step["touchesBroker"] for step in payload["plannedSteps"]))
        self.assertFalse(any(step["touchesBroker"] for step in payload["executedSteps"]))
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["executionGradeDataProofPassed"])
        self.assertIn("Topstep session safety pause", payload["brokerReadOnlyStepSkippedReason"])
        self.assertTrue(all(not step["writesOrders"] for step in payload["plannedSteps"]))
        self.assertTrue(all(
            not step["touchesBroker"] or step["brokerTouchMode"] == "read-only-market-data"
            for step in payload["plannedSteps"]
        ))

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
        self.assertIn("TopstepX/ProjectX realtime proof", markdown)
        self.assertIn("Databento realtime/order-flow proof is optional secondary research", markdown)
        self.assertIn("Topstep read-only broker bar archive", markdown)
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
                "returncode": 1 if step["id"] == "topstep-realtime-proof" else 0,
                "passed": False if step["id"] == "topstep-realtime-proof" else True,
                "writesOrders": False,
                "touchesBroker": bool(step.get("touchesBroker")),
                "brokerTouchMode": step.get("brokerTouchMode"),
                "movesFunds": False,
            }

        with patch.object(proof, "run_step", side_effect=fake_run_step), patch.object(proof, "summarize_state", return_value={}):
            payload = proof.build_payload(argparse.Namespace(
                run_data_only=True,
                timeout_sec=1.0,
                include_databento_optional_proof=False,
            ))

        self.assertEqual(payload["mode"], "run-data-only")
        self.assertFalse(payload["allCommandsPassed"])
        self.assertFalse(payload["executionGradeDataProofPassed"])
        self.assertEqual(payload["failedStepIds"], ["topstep-realtime-proof"])
        self.assertFalse(payload["writesOrders"])
        self.assertTrue(payload["touchesBroker"])
        self.assertEqual(payload["brokerTouchMode"], "read-only-market-data")
        self.assertFalse(payload["movesFunds"])
        self.assertTrue(all(
            not step["touchesBroker"] or step["brokerTouchMode"] == "read-only-market-data"
            for step in payload["executedSteps"]
        ))

    def test_data_proof_flag_accepts_topstep_realtime_proof(self):
        with patch.object(proof, "summarize_state", return_value={
            "readyForExecutionData": True,
            "topstepRealtimeReadyForExecutionDataProof": True,
            "databentoReadyForExecutionDataProof": False,
        }):
            payload = proof.build_payload(argparse.Namespace(
                run_data_only=False,
                timeout_sec=1.0,
                include_databento_optional_proof=False,
            ))

        self.assertTrue(payload["executionGradeDataProofPassed"])
        self.assertEqual(payload["decision"], "execution-grade-data-proof-passed")


if __name__ == "__main__":
    unittest.main()
