import unittest
from pathlib import Path

from scripts import multitf_entry_research_audit as audit


class MultiTfEntryResearchAuditTest(unittest.TestCase):
    def test_positive_delta_remains_research_only_when_lower_tf_coverage_is_thin(self):
        payload = audit.build_audit(
            {
                "baseline": {"total_r": 1000, "pf": 1.2, "wr": 0.55},
                "multi_tf": {"total_r": 1100, "pf": 1.25, "wr": 0.56},
                "trades": [
                    {
                        "entry_time": "2026-06-01T14:30:00+00:00",
                        "reason": "no_1m_data",
                        "points": 1,
                        "mtf_points": 1,
                        "improved": False,
                    }
                    for _ in range(80)
                ]
                + [
                    {
                        "entry_time": "2026-06-02T14:30:00+00:00",
                        "reason": "pullback_confirmed",
                        "points": -1,
                        "mtf_points": 2,
                        "improved": True,
                    }
                    for _ in range(20)
                ],
            },
            input_path=Path("results.json"),
        )

        self.assertEqual(payload["decision"], "research-only-multitf-entry-not-promotable")
        self.assertEqual(payload["evidenceGrade"], "promising-but-coverage-thin")
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])
        self.assertIn("lower-timeframe-coverage-too-thin", payload["blockers"])
        self.assertIn("not-run-through-purged-oos-promotion-gate", payload["blockers"])
        self.assertEqual(payload["summary"]["lowerTimeframeDecisionTrades"], 20)
        self.assertEqual(payload["summary"]["lowerTimeframeCoveragePct"], 20.0)

    def test_negative_delta_is_weak_research(self):
        payload = audit.build_audit(
            {
                "baseline": {"total_r": 1000, "pf": 1.2, "wr": 0.55},
                "multi_tf": {"total_r": 900, "pf": 1.1, "wr": 0.54},
                "trades": [
                    {
                        "entry_time": "2026-06-01T14:30:00+00:00",
                        "reason": "pullback_confirmed",
                        "points": 1,
                        "mtf_points": -1,
                        "improved": False,
                    }
                    for _ in range(80)
                ],
            },
            input_path=Path("results.json"),
        )

        self.assertEqual(payload["evidenceGrade"], "weak-or-negative")
        self.assertIn("multi-tf-delta-not-positive", payload["blockers"])
        self.assertIn("profit-factor-not-improved", payload["blockers"])

    def test_trades_without_timestamps_do_not_crash_audit(self):
        payload = audit.build_audit(
            {
                "baseline": {"total_r": 100, "pf": 1.1, "wr": 0.5},
                "multi_tf": {"total_r": 120, "pf": 1.2, "wr": 0.55},
                "trades": [
                    {
                        "reason": "pullback_confirmed",
                        "points": 1,
                        "mtf_points": 2,
                        "improved": True,
                    }
                    for _ in range(60)
                ],
            },
            input_path=Path("results.json"),
        )

        self.assertEqual(payload["summary"]["uniqueDays"], 0)
        self.assertEqual(payload["summary"]["firstTradeTime"], "")
        self.assertEqual(payload["summary"]["lastTradeTime"], "")
        self.assertFalse(payload["readyForExecution"])

    def test_markdown_surfaces_coverage_and_execution_lock(self):
        payload = audit.build_audit(
            {
                "baseline": {"total_r": 100, "pf": 1.1, "wr": 0.5},
                "multi_tf": {"total_r": 120, "pf": 1.2, "wr": 0.55},
                "trades": [
                    {
                        "entry_time": "2026-06-01T14:30:00+00:00",
                        "reason": "pullback_confirmed",
                        "points": 1,
                        "mtf_points": 2,
                        "improved": True,
                    }
                    for _ in range(60)
                ],
            },
            input_path=Path("results.json"),
        )

        markdown = audit.render_markdown(payload)

        self.assertIn("Ready for execution: `False`", markdown)
        self.assertIn("Lower-timeframe decision coverage", markdown)
        self.assertIn("not-cost-slippage-stressed", markdown)


if __name__ == "__main__":
    unittest.main()
