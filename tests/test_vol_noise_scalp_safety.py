import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import scripts.vol_noise_scalp as vol_noise


class VolNoiseScalpSafetyTest(unittest.TestCase):
    def test_state_output_is_research_only_even_with_backtest_signals(self):
        rows = 120
        df = pd.DataFrame({
            "ts": pd.date_range("2026-05-20T13:30:00Z", periods=rows, freq="15min"),
            "symbol": ["NQ"] * rows,
            "open": [30000.0] * rows,
            "high": [30020.0] * rows,
            "low": [29980.0] * rows,
            "close": [30010.0] * rows,
            "volume": [1000] * rows,
            "hour_utc": [13] * rows,
            "minute_utc": [30] * rows,
            "signal_raw": [0] * (rows - 1) + [1],
            "contracts": [0] * (rows - 1) + [1],
            "range_p75": [20.0] * rows,
            "range_p25": [10.0] * rows,
            "ub": [30030.0] * rows,
            "lb": [30000.0] * rows,
            "noise_width": [30.0] * rows,
            "ewma_vol": [0.01] * rows,
        })
        metrics = {
            "total_trades": 1,
            "wr": 100.0,
            "total_pnl": 10.0,
            "avg_pnl": 10.0,
            "avg_win": 10.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "sharpe_annualized": 0.0,
            "max_dd_pct": 0.0,
            "avg_bars_held": 1.0,
            "long_trades": 1,
            "long_pnl": 10.0,
            "short_trades": 0,
            "short_pnl": 0.0,
            "sessions": {},
            "exit_reasons": {"end_of_data": 1},
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(vol_noise, "STATE_DIR", Path(tmp)), patch.object(
                sys,
                "argv",
                ["vol_noise_scalp.py", "--csv", "/tmp/fake.csv", "--symbol", "NQ", "--tf", "15", "--json"],
            ), patch.object(vol_noise, "check_data_freshness", return_value={
                "fresh": False,
                "last_timestamp": "2026-05-29T20:00:00.000Z",
                "age_hours": 40.0,
                "max_age_hours": 48,
            }), patch.object(vol_noise, "load_data", return_value=df.copy()), patch.object(
                vol_noise, "compute_noise_area", return_value=df.copy()
            ), patch.object(
                vol_noise, "compute_volume_threshold", return_value=df.copy()
            ), patch.object(
                vol_noise, "compute_trend_filter", return_value=df.copy()
            ), patch.object(
                vol_noise, "compute_ewma_vol", return_value=df.copy()
            ), patch.object(
                vol_noise, "generate_signals", return_value=df.copy()
            ), patch.object(
                vol_noise, "position_sizing", return_value=df.copy()
            ), patch.object(
                vol_noise, "backtest_simple", return_value=[{"pnl_dollar": 10.0}]
            ), patch.object(
                vol_noise, "compute_metrics", return_value=metrics
            ):
                vol_noise.main()

            payload = json.loads((Path(tmp) / "vol-noise-scalp-NQ-15m.json").read_text())
            self.assertTrue(payload["researchOnly"])
            self.assertFalse(payload["writesOrders"])
            self.assertFalse(payload["touchesBroker"])
            self.assertFalse(payload["tradable_signal"])
            self.assertFalse(payload["promoted_for_execution"])
            self.assertFalse(payload["readyForExecution"])
            self.assertEqual(payload["execution_block_reason"], "research-data-stale")


if __name__ == "__main__":
    unittest.main()
