import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_clob_spread_compression_replay import build_report


class PredictionClobSpreadCompressionReplayTests(unittest.TestCase):
    def test_spread_compression_replay_stays_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clob.jsonl"
            rows = []
            start = datetime(2026, 5, 30, tzinfo=timezone.utc)
            for idx in range(40):
                asset_id = f"asset-{idx}"
                prior_ts = start + timedelta(minutes=idx * 2)
                signal_ts = prior_ts + timedelta(seconds=20)
                future_ts = signal_ts + timedelta(seconds=20)
                rows.extend([
                    {
                        "eventType": "best_bid_ask",
                        "assetId": asset_id,
                        "localTs": prior_ts.isoformat().replace("+00:00", "Z"),
                        "bestBid": "0.45",
                        "bestAsk": "0.55",
                    },
                    {
                        "eventType": "best_bid_ask",
                        "assetId": asset_id,
                        "localTs": signal_ts.isoformat().replace("+00:00", "Z"),
                        "bestBid": "0.51",
                        "bestAsk": "0.53",
                    },
                    {
                        "eventType": "best_bid_ask",
                        "assetId": asset_id,
                        "localTs": future_ts.isoformat().replace("+00:00", "Z"),
                        "bestBid": "0.55",
                        "bestAsk": "0.57",
                    },
                ])
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            payload = build_report(Namespace(
                input=str(path),
                windows=[15],
                lookback_sec=60,
                min_spread_compression=0.03,
                min_abs_mid_move=0.005,
                max_start_spread=0.05,
                min_samples=30,
                min_hit_rate=0.55,
                min_net=0.0025,
            ))

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["quoteFeatureRows"], 120)
        self.assertEqual(payload["watchResearchCount"], 1)
        self.assertEqual(payload["results"][0]["verdict"], "watch-research-only")


if __name__ == "__main__":
    unittest.main()
