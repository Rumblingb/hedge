import json
import tempfile
import unittest
from pathlib import Path

import scripts.signal_source_truth_audit as audit


class SignalSourceTruthAuditTest(unittest.TestCase):
    def test_alpha_lab_is_research_only_when_60m_signal_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            legacy_state = state / "legacy"
            legacy_state.mkdir()
            original_state = audit.STATE
            original_legacy_state = audit.LEGACY_STATE
            try:
                audit.STATE = state
                audit.LEGACY_STATE = legacy_state
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
                audit.LEGACY_STATE = original_legacy_state

    def test_never_route_source_promoted_flag_is_an_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            legacy_state = state / "legacy"
            legacy_state.mkdir()
            original_state = audit.STATE
            original_legacy_state = audit.LEGACY_STATE
            try:
                audit.STATE = state
                audit.LEGACY_STATE = legacy_state
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
                audit.LEGACY_STATE = original_legacy_state

    def test_fundamental_overlay_requires_full_promotion_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            legacy_state = state / "legacy"
            legacy_state.mkdir()
            original_state = audit.STATE
            original_legacy_state = audit.LEGACY_STATE
            try:
                audit.STATE = state
                audit.LEGACY_STATE = legacy_state
                (state / "pead-signal.latest.json").write_text(json.dumps({
                    "nq_bias": "bullish",
                    "promoted_for_execution": True,
                    "tradable_signal": False,
                }))

                row = audit.classify("pead-signal.latest.json")

                self.assertEqual(row["authority"], "never-route-unless-promoted")
                self.assertTrue(row["promotedLikeExecution"])
                self.assertEqual(row["issue"], "partial-or-ambiguous-execution-promotion")
            finally:
                audit.STATE = original_state
                audit.LEGACY_STATE = original_legacy_state

    def test_legacy_only_overlay_is_visible_to_fallback_readers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "canonical"
            legacy_state = root / "legacy"
            state.mkdir()
            legacy_state.mkdir()
            original_state = audit.STATE
            original_legacy_state = audit.LEGACY_STATE
            try:
                audit.STATE = state
                audit.LEGACY_STATE = legacy_state
                (legacy_state / "insider-signal.latest.json").write_text(json.dumps({
                    "generated_at": "2026-06-01T19:30:00+00:00",
                    "nq_bias": "bearish",
                    "confidence": 0.65,
                    "promoted_for_execution": False,
                    "tradable_signal": False,
                }))

                row = audit.classify(
                    "insider-signal.latest.json",
                    now=audit.datetime(2026, 6, 1, 20, 0, tzinfo=audit.timezone.utc),
                )

                self.assertTrue(row["present"])
                self.assertFalse(row["canonicalPresent"])
                self.assertTrue(row["legacyPresent"])
                self.assertEqual(row["issue"], "legacy-only-source-visible-to-fallback-readers")
                self.assertIn("legacy-only-source-visible-to-fallback-readers", row["sourceIssues"])
            finally:
                audit.STATE = original_state
                audit.LEGACY_STATE = original_legacy_state

    def test_divergent_canonical_and_legacy_state_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "canonical"
            legacy_state = root / "legacy"
            state.mkdir()
            legacy_state.mkdir()
            original_state = audit.STATE
            original_legacy_state = audit.LEGACY_STATE
            try:
                audit.STATE = state
                audit.LEGACY_STATE = legacy_state
                (state / "60m-signals-latest.json").write_text(json.dumps({
                    "researchOnly": True,
                    "generatedAt": "2026-06-01T20:00:00+00:00",
                    "promotedForExecution": False,
                    "tradableSignal": False,
                }))
                (legacy_state / "60m-signals-latest.json").write_text(json.dumps({
                    "command": "60m-strategy-eval",
                    "generatedAt": "2026-05-19T21:33:25+00:00",
                    "status": "no-signals",
                }))

                row = audit.classify(
                    "60m-signals-latest.json",
                    now=audit.datetime(2026, 6, 1, 20, 0, tzinfo=audit.timezone.utc),
                )

                self.assertEqual(row["issue"], "canonical-legacy-state-divergence")
                self.assertIn("canonical-legacy-state-divergence", row["sourceIssues"])
                self.assertIn("legacy-source-stale", row["warnings"])
                self.assertEqual(row["canonical"]["timestamp"], "2026-06-01T20:00:00+00:00")
                self.assertEqual(row["legacy"]["timestamp"], "2026-05-19T21:33:25+00:00")
            finally:
                audit.STATE = original_state
                audit.LEGACY_STATE = original_legacy_state


if __name__ == "__main__":
    unittest.main()
