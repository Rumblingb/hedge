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

    def test_one_minute_data_is_selectable_for_entry_research(self):
        module = load_template_module()

        self.assertIn("1m", module.DEFAULT_DATA_BY_TIMEFRAME)
        self.assertIn("1m-es", module.DEFAULT_DATA_BY_TIMEFRAME)
        self.assertEqual(module.TIMEFRAME_MINUTES["1m"], 1)
        self.assertTrue(module.DEFAULT_DATA_BY_TIMEFRAME["1m"].exists())
        self.assertTrue(module.DEFAULT_DATA_BY_TIMEFRAME["1m-es"].exists())

    def test_three_minute_data_is_derived_from_one_minute_research_data(self):
        module = load_template_module()

        self.assertIn("3m", module.DEFAULT_DATA_BY_TIMEFRAME)
        self.assertIn("3m-es", module.DEFAULT_DATA_BY_TIMEFRAME)
        self.assertEqual(module.DEFAULT_DATA_BY_TIMEFRAME["3m"], module.DEFAULT_DATA_BY_TIMEFRAME["1m"])
        self.assertEqual(module.DEFAULT_DATA_BY_TIMEFRAME["3m-es"], module.DEFAULT_DATA_BY_TIMEFRAME["1m-es"])
        self.assertEqual(module.timeframe_minutes("3m"), 3)
        self.assertEqual(module.timeframe_minutes("3m-es"), 3)

    def test_three_minute_resample_uses_complete_right_labeled_bars(self):
        module = load_template_module()
        source = pd.DataFrame(
            [
                {
                    "ts": ts,
                    "symbol": "NQ",
                    "open": 100 + i,
                    "high": 101 + i,
                    "low": 99 + i,
                    "close": 100.5 + i,
                    "volume": 10 + i,
                }
                for i, ts in enumerate(pd.date_range("2026-06-01T13:31:00Z", periods=6, freq="1min"))
            ]
        )
        frame = module.load_bars_from_frame(source, "NQ")

        resampled = module.resample_bars(frame, "3m", "NQ")

        self.assertEqual([str(ts) for ts in resampled["ts"]], [
            "2026-06-01 13:33:00+00:00",
            "2026-06-01 13:36:00+00:00",
        ])
        first = resampled.iloc[0]
        self.assertEqual(first["open"], 100)
        self.assertEqual(first["high"], 103)
        self.assertEqual(first["low"], 99)
        self.assertEqual(first["close"], 102.5)
        self.assertEqual(first["volume"], 33)

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
                agreement_timeframes="",
                agreement_sma_window=20,
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

    def test_timeframe_agreement_uses_only_complete_prior_bars(self):
        module = load_template_module()
        agreement_frame = pd.DataFrame({
            "ts": pd.to_datetime([
                "2026-06-01T12:00:00Z",
                "2026-06-01T13:00:00Z",
                "2026-06-01T14:00:00Z",
            ], utc=True),
            "close": [100.0, 90.0, 130.0],
        })
        prepared = module.prepare_agreement_frame(agreement_frame, "60m", sma_window=2)
        trades = [{
            "date": "2026-06-01",
            "session": "ny_morning",
            "direction": "long",
            "entryTs": "2026-06-01 14:30:00+00:00",
            "minutesFromOpen": 60,
            "netPoints": 1.0,
        }]

        annotated, report = module.annotate_timeframe_agreement(trades, {"60m": prepared})

        self.assertTrue(report["available"])
        self.assertEqual(annotated[0]["timeframeAgreement"], 1)
        evidence = annotated[0]["timeframeAgreementEvidence"]
        self.assertEqual(evidence[1]["timeframe"], "60m")
        self.assertEqual(evidence[1]["signal"], "short")
        self.assertEqual(evidence[1]["barEnd"], "2026-06-01 14:00:00+00:00")

    def test_session_gate_drops_below_min_timeframe_agreement(self):
        module = load_template_module()
        trades = [
            {
                "date": "2026-06-01",
                "session": "ny_morning",
                "minutesFromOpen": 30,
                "timeframeAgreement": 1,
            },
            {
                "date": "2026-06-01",
                "session": "ny_morning",
                "minutesFromOpen": 45,
                "timeframeAgreement": 2,
            },
        ]

        kept, report = module.trade_session_gate(
            trades,
            allowed_sessions=["ny_morning"],
            skip_sessions=[],
            min_timeframe_agreement=2,
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["minutesFromOpen"], 45)
        self.assertEqual(report["dropped"], {"timeframe-agreement-below-min": 1})

    def test_zero_raw_trades_are_not_mislabeled_as_missing_agreement(self):
        module = load_template_module()
        with TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "bars.csv"
            timestamps = pd.date_range("2026-05-01T13:30:00Z", periods=40, freq="30min")
            pd.DataFrame([{
                "ts": ts.isoformat(),
                "symbol": "NQ",
                "open": 20000,
                "high": 20001,
                "low": 19999,
                "close": 20000,
                "volume": 1000,
            } for ts in timestamps]).to_csv(data_path, index=False)
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
                agreement_timeframes="",
                agreement_sma_window=20,
                folds=3,
                shuffle_splits=2,
                min_train_trades=20,
                min_oos_trades=10,
            )

            result = module.evaluate_run(args, data_path, ["ny_morning", "ny_afternoon"], ["london", "premarket"])

        self.assertEqual(result["experiment"]["raw_trade_count"], 0)
        self.assertNotIn(
            "timeframe-agreement-not-available-in-single-csv-template",
            result["experiment"]["metric_blockers"],
        )


if __name__ == "__main__":
    unittest.main()
