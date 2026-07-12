import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import topstep_operator_login_yield as login_yield


class TopstepOperatorLoginYieldTests(unittest.TestCase):
    def test_engage_holds_until_explicit_operator_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = Path(tmpdir)
            safety = state / "topstep-session-safety.latest.json"
            token = state / "topstep-auth-token.json"
            token.write_text("credential-cache-placeholder")
            with patch.object(login_yield, "SAFETY", safety), patch.object(login_yield, "TOKEN_CACHE", token):
                result = login_yield.engage()
            payload = json.loads(safety.read_text())

        self.assertEqual(login_yield.HOLD_UNTIL_OPERATOR_CONFIRMATION, result["safeUntil"])
        self.assertEqual(login_yield.HOLD_UNTIL_OPERATOR_CONFIRMATION, payload["safeUntil"])
        self.assertTrue(payload["pauseBrokerTouchingProofs"])
        self.assertTrue(result["tokenCacheDropped"])

    def test_refresh_hold_preserves_token_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = Path(tmpdir)
            safety = state / "topstep-session-safety.latest.json"
            token = state / "topstep-auth-token.json"
            safety.write_text(json.dumps({
                "pauseBrokerTouchingProofs": True,
                "topstepMultipleSessionsDetected": True,
                "safeUntil": "2026-06-18",
            }))
            token.write_text("credential-cache-placeholder")
            with patch.object(login_yield, "SAFETY", safety), patch.object(login_yield, "TOKEN_CACHE", token):
                result = login_yield.refresh_hold()
            payload = json.loads(safety.read_text())
            token_value = token.read_text()

        self.assertTrue(result["updated"])
        self.assertFalse(result["tokenCacheDropped"])
        self.assertEqual("credential-cache-placeholder", token_value)
        self.assertEqual(login_yield.HOLD_UNTIL_OPERATOR_CONFIRMATION, payload["safeUntil"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])


if __name__ == "__main__":
    unittest.main()
