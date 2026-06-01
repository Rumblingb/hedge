import unittest

from scripts.ai_screener import deterministic_summary


class AiScreenerTest(unittest.TestCase):
    def test_deterministic_fallback_excludes_non_signal_artifacts(self):
        summary = deterministic_summary({
            "alpha-lab": {
                "topCandidates": [{"feature": "ret_1"}],
                "readyForExecution": False,
            },
            "futures-nq-fabervaale-orb-replay": {
                "decision": "research-only",
                "direction": "bullish",
            },
            "ichimoku-nq-signal": {
                "action": "BUY",
                "confidence": 0.7,
            },
            "whale-flow-signal": {
                "direction": "bearish",
                "confidence": 0.2,
            },
        })

        sources = {row["source"] for row in summary["topRows"]}
        self.assertEqual(sources, {"ichimoku-nq-signal", "whale-flow-signal"})
        self.assertGreaterEqual(summary["excludedNonSignalArtifactCount"], 2)
        self.assertIn("diagnostic-only-no-execution-authority", summary["blockers"])
        self.assertEqual(summary["decision"], "diagnostic-no-trade")


if __name__ == "__main__":
    unittest.main()
