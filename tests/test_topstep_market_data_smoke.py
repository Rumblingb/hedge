import argparse
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import topstep_market_data_smoke as smoke


class TopstepMarketDataSmokeTests(unittest.TestCase):
    def test_safety_blockers_require_read_only_locks(self):
        values = {
            "RH_TOPSTEP_READ_ONLY": "false",
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "true",
            "RH_LIVE_EXECUTION_ENABLED": "true",
        }

        with patch.object(smoke, "read_secure", lambda key: values.get(key)):
            blockers = smoke.safety_blockers()

        self.assertIn("RH_TOPSTEP_READ_ONLY must be true for market-data smoke", blockers)
        self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION must be false", blockers)
        self.assertIn("RH_LIVE_EXECUTION_ENABLED must be false", blockers)

    def test_safety_blockers_pause_topstep_sessions_after_multiple_session_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            safety = Path(tmp) / "topstep-session-safety.latest.json"
            safety.write_text(
                '{"topstepMultipleSessionsDetected": true, '
                '"pauseBrokerTouchingProofs": true, '
                '"reason": "multiple sessions"}'
            )
            values = {
                "RH_TOPSTEP_READ_ONLY": "true",
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                "RH_LIVE_EXECUTION_ENABLED": "false",
            }

            with patch.object(smoke, "TOPSTEP_SESSION_SAFETY", safety), \
                patch.object(smoke, "read_secure", lambda key: values.get(key)):
                blockers = smoke.safety_blockers()

        self.assertEqual(1, len(blockers))
        self.assertIn("Topstep session safety is active", blockers[0])

    def test_session_safety_override_is_explicit_for_deliberate_proof_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            safety = Path(tmp) / "topstep-session-safety.latest.json"
            safety.write_text('{"topstepMultipleSessionsDetected": true, "pauseBrokerTouchingProofs": true}')
            values = {
                "RH_TOPSTEP_READ_ONLY": "true",
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                "RH_LIVE_EXECUTION_ENABLED": "false",
                "BILL_ALLOW_TOPSTEP_BROKER_SESSION_PROOF": "true",
            }

            with patch.object(smoke, "TOPSTEP_SESSION_SAFETY", safety), \
                patch.object(smoke, "read_secure", lambda key: values.get(key)):
                blockers = smoke.safety_blockers()
                summary = smoke.topstep_session_safety_summary()

        self.assertEqual([], blockers)
        self.assertTrue(summary["active"])
        self.assertTrue(summary["overrideEnabled"])

    def test_build_report_reads_bars_without_execution_authority(self):
        args = argparse.Namespace(
            search_text="NQ",
            live=False,
            lookback_minutes=45,
            unit_number=1,
            limit=100,
        )
        contracts = [
            {"id": "CON.F.US.ENQ.M26", "symbolId": "F.US.ENQ", "activeContract": True, "name": "NQ Jun 2026"},
            {"id": "CON.F.US.MNQ.M26", "symbolId": "F.US.MNQ", "activeContract": True, "name": "MNQ Jun 2026"},
        ]
        bar = {
            "t": datetime(2026, 6, 2, 12, 30, tzinfo=timezone.utc).isoformat(),
            "o": 30500.0,
            "h": 30510.0,
            "l": 30490.0,
            "c": 30505.0,
            "v": 100,
        }
        safe_values = {
            "RH_TOPSTEP_READ_ONLY": "true",
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
            "RH_LIVE_EXECUTION_ENABLED": "false",
        }

        with tempfile.TemporaryDirectory() as tmp:
            inactive_safety = Path(tmp) / "topstep-session-safety.latest.json"
            with patch.object(smoke, "TOPSTEP_SESSION_SAFETY", inactive_safety), \
                patch.object(smoke, "read_secure", lambda key: safe_values.get(key)), \
                patch.object(smoke, "login", return_value="token"), \
                patch.object(smoke, "search_contracts", return_value=contracts), \
                patch.object(smoke, "retrieve_bars", return_value=[bar]):
                payload = smoke.build_report(args)

        self.assertEqual(payload["status"], "BARS_OK")
        self.assertTrue(payload["brokerCurrentBarsProofPassed"])
        self.assertTrue(payload["researchOnly"])
        self.assertTrue(payload["touchesBroker"])
        self.assertEqual(payload["brokerTouchMode"], "read-only-market-data")
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["placesOrders"])
        self.assertFalse(payload["modifiesOrders"])
        self.assertFalse(payload["cancelsOrders"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["topstepSessionSafety"]["active"])
        self.assertEqual(payload["symbols"]["NQ"]["status"], "BARS_OK")
        self.assertEqual(payload["symbols"]["MNQ"]["status"], "BARS_OK")

    def test_build_report_does_not_login_when_session_safety_blocks(self):
        args = argparse.Namespace(
            search_text="NQ",
            live=False,
            lookback_minutes=45,
            unit_number=1,
            limit=100,
        )
        with tempfile.TemporaryDirectory() as tmp:
            safety = Path(tmp) / "topstep-session-safety.latest.json"
            safety.write_text('{"topstepMultipleSessionsDetected": true, "pauseBrokerTouchingProofs": true}')
            safe_values = {
                "RH_TOPSTEP_READ_ONLY": "true",
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                "RH_LIVE_EXECUTION_ENABLED": "false",
            }
            with patch.object(smoke, "TOPSTEP_SESSION_SAFETY", safety), \
                patch.object(smoke, "read_secure", lambda key: safe_values.get(key)), \
                patch.object(smoke, "login") as login:
                payload = smoke.build_report(args)

        self.assertEqual(payload["status"], "BLOCKED_BY_SAFETY_ENV")
        self.assertTrue(payload["topstepSessionSafety"]["active"])
        self.assertFalse(payload["brokerCurrentBarsProofPassed"])
        login.assert_not_called()


if __name__ == "__main__":
    unittest.main()
