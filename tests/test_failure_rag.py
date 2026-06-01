import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import failure_rag


class FailureRagTests(unittest.TestCase):
    def test_configure_state_dir_moves_trade_log_and_signal_paths(self):
        original_state = failure_rag.STATE_DIR
        original_trade_log = failure_rag.TRADE_LOG_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                state_dir = Path(tmp) / "state"
                failure_rag.configure_state_dir(state_dir)

                self.assertEqual(failure_rag.STATE_DIR, state_dir)
                self.assertEqual(failure_rag.TRADE_LOG_PATH, state_dir / "failure_rag_trades.json")
        finally:
            failure_rag.STATE_DIR = original_state
            failure_rag.TRADE_LOG_PATH = original_trade_log

    def test_query_error_state_is_advisory_only(self):
        original_state = failure_rag.STATE_DIR
        original_trade_log = failure_rag.TRADE_LOG_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                state_dir = Path(tmp) / "state"
                failure_rag.configure_state_dir(state_dir)
                failure_rag.cmd_query(SimpleNamespace())

                payload = json.loads((state_dir / "failure-rag.latest.json").read_text())
                self.assertEqual(payload["signal_name"], "failure_rag")
                self.assertTrue(payload["researchOnly"])
                self.assertFalse(payload["writesOrders"])
                self.assertFalse(payload["touchesBroker"])
                self.assertFalse(payload["tradable_signal"])
                self.assertFalse(payload["promoted_for_execution"])
                self.assertFalse(payload["readyForExecution"])
        finally:
            failure_rag.STATE_DIR = original_state
            failure_rag.TRADE_LOG_PATH = original_trade_log


if __name__ == "__main__":
    unittest.main()
