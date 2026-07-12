import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts import (
    backtrader_research_loop,
    cot_signal,
    donchian_breakout,
    ichimoku_full_system,
    noise_stepforward_analysis,
    session_trader,
)


def sample_ohlcv(rows: int = 90) -> pd.DataFrame:
    base = np.linspace(100.0, 130.0, rows)
    return pd.DataFrame({
        "time": pd.date_range("2026-05-01", periods=rows, freq="h"),
        "open": base,
        "high": base + 2.0,
        "low": base - 2.0,
        "close": base + 0.5,
        "volume": np.full(rows, 1000),
    })


class FuturesStrategyShadowSafetyTests(unittest.TestCase):
    def test_backtrader_research_output_contract_is_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(backtrader_research_loop, "STATE_DIR", root / "state"), \
                 patch.object(backtrader_research_loop, "RESULT_DIR", root / "results"), \
                 patch.object(backtrader_research_loop, "FEED_DIR", root / "feeds"):
                output = backtrader_research_loop.write_outputs(
                    [
                        {
                            "strategy": "orb-breakout-15m",
                            "timeframeMinutes": 15,
                            "contracts": 1,
                            "stopPoints": 12.0,
                            "targetPoints": 24.0,
                            "closedTrades": 3,
                            "totalR": 1.25,
                            "researchOnly": True,
                        }
                    ],
                    {"orb-breakout-15m": str(root / "feed.csv")},
                    SimpleNamespace(
                        symbol="NQ",
                        session_start="14:30",
                        session_end="21:00",
                        contracts="1",
                        stop_points="12",
                        target_points="24",
                        mult=2.0,
                        commission=0.74,
                    ),
                )

            payload = json.loads(output.read_text())
            self.assertTrue(payload["researchOnly"])
            self.assertFalse(payload["executionIsolation"]["hasBrokerCredentials"])
            self.assertFalse(payload["executionIsolation"]["writesOrders"])
            self.assertIn(str(root / "state"), payload["executionIsolation"]["allowedOutputs"])
            self.assertEqual(payload["inputs"]["symbol"], "NQ")
            self.assertEqual(payload["results"][0]["strategy"], "orb-breakout-15m")
            self.assertTrue(payload["results"][0]["researchOnly"])
            self.assertTrue(Path(payload["csvPath"]).exists())

    def test_cot_signal_from_fresh_positioning_is_weekly_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            positioning = state_dir / "cftc-tff-positioning.latest.json"
            positioning.write_text(json.dumps({
                "freshForWeeklyResearch": True,
                "markets": {
                    "NQ": {
                        "reportDate": "2026-05-26",
                        "records": 52,
                        "openInterest": 1000,
                        "dealerNetPct": -10.0,
                        "dealerZ52": -2.1,
                        "assetManagerNetPct": 5.0,
                        "assetManagerZ52": 0.4,
                        "leveragedMoneyNetPct": 8.0,
                        "leveragedMoneyZ52": 1.7,
                        "positioningRegime": "crowded",
                    }
                },
            }))

            output = cot_signal.signal_from_positioning_report(positioning)

            self.assertEqual(output["evidence_level"], "weekly_cftc_positioning_research_only")
            self.assertTrue(output["researchOnly"])
            self.assertFalse(output["writesOrders"])
            self.assertFalse(output["touchesBroker"])
            self.assertFalse(output["tradable_signal"])
            self.assertFalse(output["promoted_for_execution"])
            self.assertFalse(output["readyForExecution"])
            self.assertIn("Do not route", output["execution_policy"][0])

    def test_donchian_writes_research_only_state_for_generic_nq_consumer(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            with patch.object(donchian_breakout, "STATE_DIR", state_dir), \
                 patch.object(donchian_breakout, "STATE_FILE", state_dir / "donchian-signal.latest.json"), \
                 patch.object(donchian_breakout, "load_data", return_value=sample_ohlcv()):
                output = donchian_breakout.run("NQ", "60m")

            written = json.loads((state_dir / "donchian-signal.latest.json").read_text())
            self.assertEqual(output["execution_role"], "diagnostic_only")
            self.assertTrue(written["researchOnly"])
            self.assertFalse(written["writesOrders"])
            self.assertFalse(written["touchesBroker"])
            self.assertFalse(written["tradable_signal"])
            self.assertFalse(written["promoted_for_execution"])
            self.assertFalse(written["readyForExecution"])

    def test_ichimoku_writes_research_only_state_for_generic_nq_consumer(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            with patch.object(ichimoku_full_system, "STATE_DIR", state_dir), \
                 patch.object(ichimoku_full_system, "STATE_FILE", state_dir / "ichimoku-signal.latest.json"), \
                 patch.object(ichimoku_full_system, "load_data", return_value=sample_ohlcv()):
                output = ichimoku_full_system.run("NQ", "60m")

            written = json.loads((state_dir / "ichimoku-signal.latest.json").read_text())
            self.assertEqual(output["execution_role"], "diagnostic_only")
            self.assertTrue(written["researchOnly"])
            self.assertFalse(written["writesOrders"])
            self.assertFalse(written["touchesBroker"])
            self.assertFalse(written["tradable_signal"])
            self.assertFalse(written["promoted_for_execution"])
            self.assertFalse(written["readyForExecution"])

    def test_noise_stepforward_is_evidence_only_even_with_no_valid_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "noise-analysis.latest.json"
            with patch.object(noise_stepforward_analysis, "STATE_FILE", state_file), \
                 patch.object(noise_stepforward_analysis, "compute_epps_effect", return_value={}), \
                 patch.object(noise_stepforward_analysis, "rolling_noise_analysis", return_value={"status": "missing"}), \
                 patch.object(noise_stepforward_analysis, "step_forward_stability", return_value={"status": "missing"}):
                output = noise_stepforward_analysis.run_full_analysis(["NQ"])

            written = json.loads(state_file.read_text())
            self.assertIsNone(output["noise_summary"]["most_noisy_60m"])
            self.assertIsNone(output["stepforward_summary"]["best_oos"])
            self.assertTrue(written["researchOnly"])
            self.assertFalse(written["writesOrders"])
            self.assertFalse(written["touchesBroker"])
            self.assertFalse(written["tradable_signal"])
            self.assertFalse(written["promoted_for_execution"])
            self.assertFalse(written["readyForExecution"])
            self.assertEqual(written["execution_role"], "diagnostic_only")

    def test_session_trader_returns_no_trade_when_recent_nq_data_is_missing(self):
        with patch.object(session_trader, "fetch_nq_bars", return_value={}):
            output = session_trader.run()

        self.assertEqual(output["decision"], "NO_TRADE")
        self.assertEqual(output["reason"], "insufficient_recent_nq_data")
        self.assertTrue(output["researchOnly"])
        self.assertFalse(output["writesOrders"])


if __name__ == "__main__":
    unittest.main()
