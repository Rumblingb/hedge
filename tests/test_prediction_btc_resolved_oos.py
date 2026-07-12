import unittest

import polars as pl

from scripts.prediction_btc_resolved_oos import Rule, rule_summary, signals_for_rule


class PredictionBtcResolvedOosTest(unittest.TestCase):
    def test_rule_summary_uses_earliest_signal_per_market_and_stays_research_only(self):
        df = pl.DataFrame({
            "market_id": ["m1", "m1", "m2", "m3"],
            "ts": [1, 2, 3, 4],
            "end_ts": [10, 10, 20, 30],
            "target_up_win": [1, 1, 0, 1],
            "target_down_win": [0, 0, 1, 0],
            "up_price": [0.40, 0.35, 0.40, 0.40],
            "down_price": [0.60, 0.65, 0.60, 0.60],
            "avg_spread": [0.02, 0.02, 0.02, 0.02],
            "spot_distance_to_strike_pct": [0.01, 0.02, 0.01, 0.01],
        })
        rule = Rule(
            "test-up",
            "up",
            "spot distance",
            "fixture",
            pl.col("spot_distance_to_strike_pct") > 0,
        )

        signals = signals_for_rule(df, rule)
        summary = rule_summary(rule, signals)

        self.assertEqual(signals.height, 3)
        self.assertEqual(summary["train"]["trades"], 1)
        self.assertEqual(summary["oos"]["trades"], 2)
        self.assertFalse(summary["passesResearchContract"])
        self.assertEqual(summary["decision"], "reject-current-fixed-rule")


if __name__ == "__main__":
    unittest.main()
