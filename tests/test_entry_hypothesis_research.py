import unittest
from datetime import datetime, timedelta, timezone

from scripts import entry_hypothesis_research as research


def bar(ts, open_, high, low, close, volume=100):
    return research.Bar(
        ts=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class EntryHypothesisResearchTest(unittest.TestCase):
    def test_report_is_research_only_and_blocks_execution(self):
        start = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)
        bars15 = []
        price = 100.0
        for index in range(80):
            ts = start + timedelta(minutes=15 * index)
            if index % 4 == 1:
                bars15.append(bar(ts, price, price + 8, price - 1, price + 6))
                price += 6
            else:
                bars15.append(bar(ts, price, price + 2, price - 2, price + 1))
                price += 1

        trades = research.run_baseline(bars15, cost_points=1.0)
        payload = research.hypothesis_summary(
            "baseline",
            trades,
            signal_count=len(trades),
            covered_count=len(trades),
            train_fraction=0.7,
            extra_costs=[1.0, 2.0],
            notes=["synthetic"],
        )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertIn("not-demo-or-execution-evidence", payload["blockers"])
        self.assertIn("not-broker-grade-current-session-proof", payload["blockers"])
        self.assertIn("costStress", payload)
        self.assertGreaterEqual(payload["train"]["tradeCount"], 1)

    def test_lower_timeframe_red_candle_reports_coverage(self):
        start = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)
        bars15 = [
            bar(start, 100, 101, 99, 100),
            bar(start + timedelta(minutes=15), 100, 110, 100, 108),
            bar(start + timedelta(minutes=30), 108, 109, 107, 108.5),
        ] + [
            bar(start + timedelta(minutes=45 + 15 * index), 108, 109, 107, 108)
            for index in range(8)
        ]
        lower = [
            bar(start + timedelta(minutes=15 + index), 108, 109, 106, 107)
            for index in range(3)
        ]

        trades, signals, covered = research.run_lower_red_pullback(
            bars15,
            research.lower_index(lower),
            hypothesis="red-entry",
            cost_points=1.0,
        )

        self.assertEqual(signals, 1)
        self.assertEqual(covered, 1)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].hypothesis, "red-entry")

    def test_markdown_keeps_non_promotable_language(self):
        payload = {
            "decision": "research-only-entry-hypotheses-not-promotable",
            "readyForExecution": False,
            "readyForDemoExpansion": False,
            "data": {"bars15m": 10},
            "bestResearchWatch": {"id": "baseline"},
            "hypotheses": [
                {
                    "id": "baseline",
                    "oos": {"tradeCount": 1, "netPoints": -1, "profitFactor": 0, "maxDrawdownPoints": 1},
                    "coveragePct": 100,
                    "evidenceGrade": "research-only-blocked",
                    "blockers": ["too-few-oos-trades"],
                }
            ],
        }

        markdown = research.render_markdown(payload)

        self.assertIn("Ready for execution: `False`", markdown)
        self.assertIn("research-only", markdown)
        self.assertIn("blocked from demo/live promotion", markdown)


if __name__ == "__main__":
    unittest.main()
