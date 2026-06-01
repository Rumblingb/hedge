import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_clob_quote_intensity_replay import build_report


class PredictionClobQuoteIntensityReplayTests(unittest.TestCase):
    def test_quote_intensity_replay_stays_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clob.jsonl"
            rows = []
            start = datetime(2026, 5, 30, tzinfo=timezone.utc)
            for idx in range(80):
                ts = start + timedelta(seconds=idx)
                bid = 0.40 + idx * 0.002
                rows.append({
                    "eventType": "best_bid_ask",
                    "assetId": "asset-a",
                    "localTs": ts.isoformat().replace("+00:00", "Z"),
                    "bestBid": f"{bid:.3f}",
                    "bestAsk": f"{bid + 0.002:.3f}",
                })
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            payload = build_report(Namespace(
                input=str(path),
                windows=[15],
                lookback_sec=60,
                min_updates=5,
                min_abs_prior_move=0.001,
                max_start_spread=0.05,
                min_samples=30,
                min_hit_rate=0.55,
                min_net=0.0025,
            ))

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertGreaterEqual(payload["quoteFeatureRows"], 80)
        self.assertEqual(payload["watchResearchCount"], 1)
        self.assertEqual(payload["results"][0]["verdict"], "watch-research-only")


if __name__ == "__main__":
    unittest.main()
