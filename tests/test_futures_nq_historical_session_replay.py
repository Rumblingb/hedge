import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from scripts.futures_nq_historical_session_replay import VAULT, build_replay, default_markdown_path, render_markdown


def write_breakout_parquet(path: Path, days: int, positive: bool) -> None:
    rows = []
    start = datetime(2026, 1, 5, 14, 30)
    for day in range(days):
        day_start = start + timedelta(days=day)
        base = 20000 + day * 5
        for bar in range(27):
            ts = day_start + timedelta(minutes=bar * 15)
            if bar < 2:
                open_px = base
                high = base + 10
                low = base - 10
                close = base
            elif bar == 2:
                open_px = base + 11
                high = base + 20
                low = base + 5
                close = base + 15
            else:
                open_px = base + 15
                high = base + 30
                low = base + 10
                close = base + (50 if positive else -20)
            rows.append({
                "ts": ts,
                "open": float(open_px),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": 100.0,
            })
    pl.DataFrame(rows).write_parquet(path)


def write_fabervaale_parquet(path: Path, days: int, target_hit: bool = True) -> None:
    rows = []
    start = datetime(2026, 1, 5, 14, 30)
    for day in range(days):
        day_start = start + timedelta(days=day)
        base = 20000 + day * 3
        for bar in range(78):
            ts = day_start + timedelta(minutes=bar * 5)
            if bar < 6:
                open_px = base
                high = base + 10
                low = base - 10
                close = base
            elif bar == 6:
                open_px = base + 11
                high = base + 15
                low = base + 8
                close = base + 12
            elif target_hit:
                open_px = base + 15
                high = base + 31
                low = base + 12
                close = base + 30
            else:
                open_px = base + 5
                high = base + 8
                low = base - 11
                close = base - 10
            rows.append({
                "ts": ts,
                "open": float(open_px),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": 100.0,
            })
    pl.DataFrame(rows).write_parquet(path)


class FuturesNqHistoricalSessionReplayTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^futures-nq-historical-session-replay-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "source": {},
            "strategy": "first-break-session-close",
            "tradeCount": 0,
            "trainStats": {},
            "oosStats": {},
            "blockers": [],
            "hardRules": [],
        })

        self.assertIn("# Futures NQ Historical Session Replay - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_positive_fixed_rule_remains_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nq.parquet"
            write_breakout_parquet(path, days=30, positive=True)
            payload = build_replay(
                coverage={"decision": "research-only-historical-nq-source-ready"},
                input_path=str(path),
                cadence_minutes=15,
                cost_points=1.0,
            )

        self.assertEqual(payload["decision"], "research-only-historical-session-replay-watch")
        self.assertGreater(payload["oosStats"]["netR"], 0)
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])

    def test_negative_oos_blocks_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nq.parquet"
            write_breakout_parquet(path, days=30, positive=False)
            payload = build_replay(
                coverage={"decision": "research-only-historical-nq-source-ready"},
                input_path=str(path),
                cadence_minutes=15,
                cost_points=1.0,
            )

        self.assertEqual(payload["decision"], "research-only-historical-session-replay-blocked")
        self.assertIn("oos-edge-below-contract-after-cost", payload["blockers"])

    def test_fabervaale_orb_replay_is_long_only_research_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nq-5m.parquet"
            write_fabervaale_parquet(path, days=30, target_hit=True)
            payload = build_replay(
                coverage={"decision": "research-only-historical-nq-source-ready"},
                input_path=str(path),
                cadence_minutes=5,
                cost_points=1.0,
                strategy="fabervaale-orb",
            )

        self.assertEqual(payload["strategy"], "fabervaale-orb")
        self.assertEqual(payload["decision"], "research-only-historical-session-replay-watch")
        self.assertTrue(all(trade["direction"] == "long" for trade in payload["trades"]))
        self.assertTrue(all(trade["exitReason"] == "target-1r" for trade in payload["trades"]))
        self.assertGreater(payload["oosStats"]["netR"], 0)
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])

    def test_fabervaale_orb_blocks_when_cadence_is_too_coarse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nq-15m.parquet"
            write_breakout_parquet(path, days=30, positive=True)
            payload = build_replay(
                coverage={"decision": "research-only-historical-nq-source-ready"},
                input_path=str(path),
                cadence_minutes=15,
                cost_points=1.0,
                strategy="fabervaale-orb",
            )

        self.assertEqual(payload["decision"], "research-only-historical-session-replay-blocked")
        self.assertIn("cadence-too-coarse-for-fabervaale-5m-close", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
