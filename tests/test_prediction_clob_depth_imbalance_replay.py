import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_clob_depth_imbalance_replay import build_report


class PredictionClobDepthImbalanceReplayTests(unittest.TestCase):
    def test_depth_imbalance_replay_stays_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clob.jsonl"
            rows = []
            start = datetime(2026, 5, 30, tzinfo=timezone.utc)
            for idx in range(40):
                book_ts = start + timedelta(minutes=idx * 2)
                future_ts = book_ts + timedelta(seconds=30)
                rows.append({
                    "eventType": "book",
                    "assetId": "asset-a",
                    "localTs": book_ts.isoformat().replace("+00:00", "Z"),
                    "bids": [{"price": "0.49", "size": "100"}],
                    "asks": [{"price": "0.51", "size": "10"}],
                })
                rows.append({
                    "eventType": "best_bid_ask",
                    "assetId": "asset-a",
                    "localTs": future_ts.isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.52",
                    "bestAsk": "0.54",
                })
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            payload = build_report(Namespace(
                input=str(path),
                windows=[15],
                imbalance_threshold=0.2,
                max_start_spread=0.05,
                min_samples=30,
                min_hit_rate=0.55,
                min_net=0.0025,
            ))

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["bookFeatureRows"], 40)
        self.assertEqual(payload["watchResearchCount"], 1)
        self.assertEqual(payload["results"][0]["verdict"], "watch-research-only")


if __name__ == "__main__":
    unittest.main()
