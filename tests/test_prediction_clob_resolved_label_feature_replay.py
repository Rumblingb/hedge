import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.prediction_clob_resolved_label_feature_replay import build_report


def _make_corpus(path: Path, *, pre_resolution: bool):
    """Build a tiny resolved BTC-style corpus.

    pre_resolution=True  -> microstructure populated at frac=0.1 (forward-eligible)
    pre_resolution=False -> microstructure only at the resolution bar (frac=1.0)
    """
    rng = np.random.default_rng(7)
    n_markets = 12
    rows = []
    for m in range(n_markets):
        win = int(rng.integers(0, 2))  # resolved YES=1 / NO=0
        start_ts = 1_700_000_000
        end_ts = start_ts + 600  # 600s market life, 5m bars -> final bar near end
        if pre_resolution:
            ts = start_ts + int(0.1 * (end_ts - start_ts))  # frac 0.1
            frac_bars = [ts]
        else:
            ts = start_ts + 590  # frac ~0.98 (resolution bar)
            frac_bars = [ts]
        for tsb in frac_bars:
            up_imb = 0.6 if win == 1 else -0.6
            down_imb = -0.6 if win == 1 else 0.6
            rows.append({
                "market_id": f"m{m}",
                "ts": tsb,
                "up_price": 0.5, "down_price": 0.5,
                "target_up_win": win, "target_down_win": 1 - win,
                "start_ts": start_ts, "end_ts": end_ts,
                "up_bid_depth": 100.0, "up_ask_depth": 50.0,
                "down_bid_depth": 50.0, "down_ask_depth": 100.0,
                "up_depth_imbalance": up_imb, "down_depth_imbalance": down_imb,
                "ob_rows": 10.0,
                "trade_count": 100.0, "trade_usdc": 5000.0,
                "buy_usdc": 3000.0, "sell_usdc": 2000.0,
                "trade_flow_imbalance": 0.3, "avg_trade_price": 0.5,
                "avg_spread": 0.03, "spot_price": 60000.0,
            })
    pd.DataFrame(rows).to_parquet(path)


class PredictionClobResolvedLabelFeatureReplayTests(unittest.TestCase):
    def test_forward_mode_reports_no_eligible_pre_resolution_rows_on_resolution_only_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus.parquet"
            _make_corpus(corpus, pre_resolution=False)
            payload = build_report(Namespace(
                corpus=str(corpus),
                output=str(Path(tmp) / "out.json"),
                markdown_output=str(Path(tmp) / "out.md"),
                max_elig_frac=0.5,
                include_resolution_bar=False,
                cv_folds=5,
                min_samples=30,
                min_hit_rate=0.55,
                min_net=0.0025,
            ))
        self.assertEqual(payload["mode"], "pre-resolution-forward")
        self.assertEqual(payload["eligibleRows"], 0)
        self.assertIn("zero-eligible-pre-resolution-rows", payload["blockers"])
        self.assertFalse(payload["readyForPaper"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])

    def test_negative_control_detects_tautology_and_is_not_promoted_in_forward_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus.parquet"
            _make_corpus(corpus, pre_resolution=False)
            payload = build_report(Namespace(
                corpus=str(corpus),
                output=str(Path(tmp) / "out.json"),
                markdown_output=str(Path(tmp) / "out.md"),
                max_elig_frac=0.5,
                include_resolution_bar=True,  # deliberately tautological
                cv_folds=5,
                min_samples=30,
                min_hit_rate=0.55,
                min_net=0.0025,
            ))
        self.assertEqual(payload["mode"], "negative-control-resolution-bar")
        # The harness runs; but the feature family is by-design not a forward signal here.
        self.assertGreater(payload["negativeControlResolutionBarAuc"], 0.9)

    def test_forward_mode_runs_on_pre_resolution_corpus_and_is_gated_by_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus.parquet"
            _make_corpus(corpus, pre_resolution=True)
            payload = build_report(Namespace(
                corpus=str(corpus),
                output=str(Path(tmp) / "out.json"),
                markdown_output=str(Path(tmp) / "out.md"),
                max_elig_frac=0.5,
                include_resolution_bar=False,
                cv_folds=5,
                min_samples=30,
                min_hit_rate=0.55,
                min_net=0.0025,
            ))
        self.assertEqual(payload["mode"], "pre-resolution-forward")
        self.assertGreater(payload["eligibleRows"], 0)
        # Even with a synthetic strong signal, the family must still be reported research-only
        # unless it clears the no-edge contract; the test asserts the gate is applied.
        self.assertIn(payload["verdict"], ("watch-research-only", "reject"))
        self.assertTrue(payload["researchOnly"])


if __name__ == "__main__":
    unittest.main()
