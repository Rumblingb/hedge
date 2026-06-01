import json
import tempfile
import unittest
from pathlib import Path

import scripts.signal_source_truth_audit as audit


class SignalSourceTruthAuditTest(unittest.TestCase):
    def test_alpha_lab_is_research_only_when_60m_signal_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            original_state = audit.STATE
            try:
                audit.STATE = state
                (state / "alpha-lab.latest.json").write_text(json.dumps({
                    "command": "alpha-lab",
                    "topCandidates": [{"feature": "ret_1"}],
                    "readyForExecution": False,
                }))
                (state / "60m-signals-latest.json").write_text(json.dumps({
                    "researchOnly": True,
                    "promotedForExecution": False,
                    "tradableSignal": False,
                }))

                row = audit.classify("alpha-lab.latest.json")

                self.assertEqual(row["role"], "research-candidates")
                self.assertEqual(row["authority"], "never-route")
                self.assertFalse(row["promotedLikeExecution"])
                self.assertIn("coexists-with-60m-signal-source", row["issue"])
            finally:
                audit.STATE = original_state

    def test_never_route_source_promoted_flag_is_an_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            original_state = audit.STATE
            try:
                audit.STATE = state
                (state / "60m-signal.latest.json").write_text(json.dumps({
                    "signal": "LONG",
                    "readyForExecution": True,
                }))

                row = audit.classify("60m-signal.latest.json")

                self.assertEqual(row["authority"], "never-route")
                self.assertTrue(row["promotedLikeExecution"])
                self.assertEqual(row["issue"], "research-or-advisory-source-promoted")
            finally:
                audit.STATE = original_state


if __name__ == "__main__":
    unittest.main()
