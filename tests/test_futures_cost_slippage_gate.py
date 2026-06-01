import argparse
import unittest

from scripts.futures_cost_slippage_gate import build_survivor_review, dedupe_backtrader_rows, score_backtrader_rows


class FuturesCostSlippageGateTest(unittest.TestCase):
    def test_backtrader_survivors_are_deduped_by_independent_config(self):
        args = argparse.Namespace(
            base_slippage_points=0.25,
            commission_round_turn=1.48,
            multiplier=2.0,
            default_stop_points=8.0,
        )
        artifact = {
            "results": [
                {
                    "strategy": "wq-vol-regime-60m",
                    "timeframeMinutes": 60,
                    "contracts": contracts,
                    "stopPoints": 8.0,
                    "targetPoints": 32.0,
                    "closedTrades": 20,
                    "avgR": 0.9,
                    "totalR": 18.0,
                    "winRate": 0.55,
                }
                for contracts in (1, 2, 3)
            ]
        }

        scored = score_backtrader_rows(artifact, args)
        survivors = [row for row in scored if row["survivesAllStress"]]
        deduped_survivors = [row for row in dedupe_backtrader_rows(scored) if row["survivesAllStress"]]

        self.assertEqual(len(scored), 3)
        self.assertEqual(len(survivors), 3)
        self.assertEqual(len(deduped_survivors), 1)
        self.assertEqual(deduped_survivors[0]["strategy"], "wq-vol-regime-60m")

    def test_survivor_review_blocks_full_sample_only_survivors(self):
        review = build_survivor_review(
            [
                {
                    "strategy": "wq-vol-regime-60m",
                    "timeframeMinutes": 60,
                    "stopPoints": 12,
                    "targetPoints": 32,
                    "stress": [{"stressedTotalR": 10}, {"stressedTotalR": 8}, {"stressedTotalR": 6}],
                }
                for _ in range(6)
            ],
            [],
            [
                {
                    "timeframeHint": "latest.json",
                    "status": "reject-current-oos",
                    "aggregateRaw": {"netR": -10, "profitFactor": 0.5},
                    "survivingWindowRatio": 0.0,
                    "survivesGate": False,
                }
            ],
        )

        self.assertEqual(review["status"], "blocked-full-sample-only")
        self.assertEqual(review["decision"], "do-not-promote-backtrader-survivors-without-oos-survivors")
        self.assertEqual(review["parameterMiningRisk"], "high")
        self.assertEqual(review["blockedSurvivorExamples"][0]["reviewDecision"], "hypothesis-seed-only")


if __name__ == "__main__":
    unittest.main()
