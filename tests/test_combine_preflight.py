import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import combine_preflight


class CombinePreflightTests(unittest.TestCase):
    def test_clear_preflight_never_claims_execution_authority(self):
        checks = [
            "check_fomc",
            "check_feed",
            "check_flat_and_recon",
            "check_account",
            "check_plan_approval",
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            state = Path(tmpdir)
            patches = [patch.object(combine_preflight, name, return_value=(True, "green")) for name in checks]
            for active_patch in patches:
                active_patch.start()
            self.addCleanup(lambda: [active_patch.stop() for active_patch in reversed(patches)])
            with patch.object(combine_preflight, "STATE", state):
                self.assertEqual(0, combine_preflight.main())
            record = json.loads((state / "combine-preflight.latest.json").read_text())

        self.assertEqual("CLEAR", record["verdict"])
        self.assertTrue(record["researchOnly"])
        self.assertFalse(record["writesOrders"])
        self.assertFalse(record["touchesBroker"])
        self.assertFalse(record["movesFunds"])
        self.assertFalse(record["readyForExecution"])
        self.assertFalse(record["readyForDemoExpansion"])
        self.assertFalse(record["readyForLive"])
        self.assertIn("preflight-evidence-only", record["authority"])


if __name__ == "__main__":
    unittest.main()
