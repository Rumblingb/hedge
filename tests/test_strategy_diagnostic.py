import tempfile
import unittest
from pathlib import Path

from scripts.strategy_diagnostic import (
    analyze_orb,
    analyze_wq_trend_momentum,
    build_report,
    group_sessions,
    load_bars,
)


def write_sample_csv(path: Path) -> None:
    rows = ["ts,symbol,open,high,low,close,volume"]
    for index in range(70):
        hour = 14 + index // 60
        minute = index % 60
        price = 100 + index * 0.1
        close = 105.0 if index == 14 else price
        volume = 250 if index == 14 else 100
        rows.append(
            f"2026-06-01T{hour:02d}:{minute:02d}:00Z,NQ,{price:.2f},{max(price, close):.2f},{min(price, close):.2f},{close:.2f},{volume}"
        )
    path.write_text("\n".join(rows) + "\n")


write_fixture = write_sample_csv


class StrategyDiagnosticTest(unittest.TestCase):
    def test_diagnoses_orb_and_trend_without_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            write_sample_csv(path)

            bars = load_bars(path)
            sessions = group_sessions(bars)
            orb = analyze_orb(sessions, range_window=12, vol_threshold=1.3)
            trend = analyze_wq_trend_momentum(sessions, sma_short=5, sma_long=20, min_spread_pct=0.0001)

        self.assertEqual(len(bars), 70)
        self.assertEqual(1, len(sessions))
        self.assertGreaterEqual(orb["breakoutPass"], 1)
        self.assertGreaterEqual(trend["signals"], 1)

    def test_report_is_research_only_and_not_execution_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            write_sample_csv(path)
            payload = build_report(path, session_limit=1, max_rows=50)

        self.assertEqual("research-only-strategy-diagnostic", payload["decision"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertIn("diagnostic-only-no-execution-authority", payload["promotionBlockers"])


if __name__ == "__main__":
    unittest.main()
