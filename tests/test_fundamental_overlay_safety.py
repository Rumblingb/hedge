import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.insider_trading_scanner import InsiderScanner
from scripts.pead_earnings_scanner import PEADScanner
from scripts import insider_trading_scanner, pead_earnings_scanner, sr_proximity_detector


def assert_research_only(testcase: unittest.TestCase, payload: dict) -> None:
    testcase.assertTrue(payload["researchOnly"])
    testcase.assertFalse(payload["writesOrders"])
    testcase.assertFalse(payload["touchesBroker"])
    testcase.assertFalse(payload["movesFunds"])
    testcase.assertFalse(payload["readyForExecution"])
    testcase.assertFalse(payload["promoted_for_execution"])
    testcase.assertFalse(payload["tradable_signal"])
    testcase.assertEqual(payload["execution_role"], "research_only")


class FundamentalOverlaySafetyTests(unittest.TestCase):
    def test_research_overlays_default_to_canonical_state_dir(self):
        canonical = Path.home() / "hedge/.rumbling-hedge/state"

        self.assertEqual(pead_earnings_scanner.STATE_DIR, canonical)
        self.assertEqual(insider_trading_scanner.STATE_DIR, canonical)
        self.assertEqual(sr_proximity_detector.STATE_DIR, canonical)
        self.assertNotEqual(pead_earnings_scanner.STATE_DIR, Path.home() / ".rumbling-hedge/state")

    def test_pead_output_is_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            cache = state / "pead-earnings-cache.json"
            cache.write_text(json.dumps({"earnings": {}, "active_positions": []}))
            output_path = state / "pead-signal.latest.json"

            with patch.object(pead_earnings_scanner, "STATE_FILE", output_path), \
                 patch.object(pead_earnings_scanner, "EARNINGS_CACHE", cache):
                output = PEADScanner().run()

            assert_research_only(self, output)
            written = json.loads(output_path.read_text())
            assert_research_only(self, written)
            self.assertEqual(written["evidence_level"], "earnings-drift-research-only")

    def test_insider_no_data_output_is_research_only_and_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            cache = state / "insider-cache.json"
            cache.write_text(json.dumps({"trades": {}}))
            output_path = state / "insider-signal.latest.json"

            with patch.object(insider_trading_scanner, "STATE_FILE", output_path), \
                 patch.object(insider_trading_scanner, "CACHE_FILE", cache):
                output = InsiderScanner().run()

            assert_research_only(self, output)
            self.assertEqual(output["status"], "no_data")
            self.assertEqual(output["nq_bias"], "neutral")
            self.assertEqual(output["confidence"], 0.0)
            written = json.loads(output_path.read_text())
            assert_research_only(self, written)
            self.assertEqual(written["evidence_level"], "sec-form4-research-only")


if __name__ == "__main__":
    unittest.main()
