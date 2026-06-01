import importlib.util
import json
import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "ai-scientist-templates" / "financial_strategy" / "experiment.py"


def load_template_module():
    spec = importlib.util.spec_from_file_location("financial_strategy_experiment", TEMPLATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AiScientistFinancialTemplateTest(unittest.TestCase):
    def test_known_baselines_are_real_strategy_entries(self):
        module = load_template_module()

        strategies = {row["strategy"] for row in module.KNOWN_BASELINES}

        self.assertEqual(
            strategies,
            {"orb", "wq_trend_mom", "wq_vol_regime"},
        )
        self.assertTrue(all("not implemented" not in row["source"].lower() for row in module.KNOWN_BASELINES))

    def test_lossless_profit_factor_stays_strict_json(self):
        module = load_template_module()

        metrics = module.metrics([{"netPoints": 10, "session": "ny_morning", "entryTs": "2026-06-01T14:00:00Z"}])

        self.assertIsNone(metrics["profit_factor"])
        self.assertTrue(metrics["profit_factor_lossless"])
        json.dumps(metrics, allow_nan=False)

    def test_wq_strategy_evaluation_is_research_only_and_non_routing(self):
        module = load_template_module()
        with TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "bars.csv"
            timestamps = pd.date_range("2026-05-01T13:30:00Z", periods=100, freq="30min")
            rows = []
            for i, ts in enumerate(timestamps):
                base = 20000 + i * 4
                rows.append({
                    "ts": ts.isoformat(),
                    "symbol": "NQ",
                    "open": base,
                    "high": base + 8,
                    "low": base - 4,
                    "close": base + 6,
                    "volume": 1000 + i * 10,
                })
            pd.DataFrame(rows).to_csv(data_path, index=False)

            args = Namespace(
                data=str(data_path),
                timeframe="30m",
                strategy="wq_trend_mom",
                symbol="NQ",
                sessions="ny_morning,ny_afternoon",
                skip_sessions="london,premarket",
                opening_minutes=30,
                range_window_bars=None,
                hold_bars=2,
                cost_points=1.5,
                volume_threshold=1.0,
                entry_offset_ticks=0,
                tick_size=0.25,
                short_sma=3,
                long_sma=8,
                short_lookback=10,
                long_lookback=20,
                short_threshold=1.6,
                long_threshold=0.8,
                max_trades_per_session=3,
                min_timeframe_agreement=2,
                folds=3,
                shuffle_splits=2,
                min_train_trades=20,
                min_oos_trades=10,
            )

            result = module.evaluate_run(
                args,
                data_path,
                ["ny_morning", "ny_afternoon"],
                ["london", "premarket"],
            )

        self.assertEqual(result["experiment"]["strategy"], "wq_trend_mom")
        self.assertFalse(result["means"]["ready_for_paper"])
        self.assertFalse(result["means"]["ready_for_execution"])
        self.assertIn(
            "template-output-is-not-paper-demo-or-execution-promotion",
            result["experiment"]["promotion_blockers"],
        )
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
