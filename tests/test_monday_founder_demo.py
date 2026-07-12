import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import monday_founder_demo
from scripts.monday_founder_demo import SAFE_ENV, assess_readiness


class MondayFounderDemoTests(unittest.TestCase):
    def test_safe_env_keeps_all_execution_disabled(self):
        self.assertEqual("false", SAFE_ENV["BILL_ENABLE_FUTURES_DEMO_EXECUTION"])
        self.assertEqual("true", SAFE_ENV["RH_TOPSTEP_READ_ONLY"])
        self.assertEqual("false", SAFE_ENV["RH_LIVE_EXECUTION_ENABLED"])

    def test_presentation_can_be_ready_only_while_trade_clearance_stays_locked(self):
        ready, blockers = assess_readiness({
            "readyForPresentationDemo": True,
            "readyForDemoExpansion": False,
            "readyForExecution": False,
            "tradeClearance": {"executionLocked": True},
        })

        self.assertTrue(ready)
        self.assertEqual([], blockers)

    def test_assessment_fails_if_demo_expansion_is_accidentally_cleared(self):
        ready, blockers = assess_readiness({
            "readyForPresentationDemo": True,
            "readyForDemoExpansion": True,
            "readyForExecution": False,
            "tradeClearance": {"executionLocked": True},
        })

        self.assertFalse(ready)
        self.assertIn("readyForDemoExpansion must remain false", blockers)

    def test_main_uses_bounded_readiness_endpoint_instead_of_full_state(self):
        requested_paths = []

        def fake_fetch(path):
            requested_paths.append(path)
            if path == "/api/monday-readiness":
                return {
                    "readyForPresentationDemo": True,
                    "readyForDemoExpansion": False,
                    "readyForExecution": False,
                    "tradeClearance": {"executionLocked": True},
                    "presentationWarnings": [],
                    "presentationChecks": [],
                }
            if path == "/api/live-readiness-gate":
                return {
                    "passCount": 19,
                    "totalCount": 21,
                    "failedChecks": [{"id": "source-clean"}],
                }
            raise AssertionError(f"unexpected endpoint: {path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "receipt.json"
            with (
                patch.object(monday_founder_demo, "run_step", return_value={"id": "ok", "passed": True}),
                patch.object(monday_founder_demo, "ensure_command_center", return_value={}),
                patch.object(monday_founder_demo, "fetch_json", side_effect=fake_fetch),
                patch.object(monday_founder_demo, "OUT", out),
            ):
                self.assertEqual(0, monday_founder_demo.main())

            receipt = json.loads(out.read_text())

        self.assertEqual(["/api/monday-readiness", "/api/live-readiness-gate"], requested_paths)
        self.assertEqual(19, receipt["liveReadiness"]["passCount"])
        self.assertEqual(21, receipt["liveReadiness"]["totalCount"])
        self.assertEqual([{"id": "source-clean"}], receipt["liveReadiness"]["failedChecks"])


if __name__ == "__main__":
    unittest.main()
