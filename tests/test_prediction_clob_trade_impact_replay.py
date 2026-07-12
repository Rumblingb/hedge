import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_clob_trade_impact_replay import build_report


class PredictionClobTradeImpactReplayTests(unittest.TestCase):
    def test_trade_impact_replay_stays_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clob.jsonl"
            rows = []
            start = datetime(2026, 5, 30, tzinfo=timezone.utc)
            for idx in range(40):
                asset_id = f"asset-{idx}"
                quote_ts = start + timedelta(minutes=idx * 2)
                trade_ts = quote_ts + timedelta(seconds=2)
                future_ts = trade_ts + timedelta(seconds=20)
                rows.extend([
                    {
                        "eventType": "best_bid_ask",
                        "assetId": asset_id,
                        "localTs": quote_ts.isoformat().replace("+00:00", "Z"),
                        "bestBid": "0.49",
                        "bestAsk": "0.51",
                    },
                    {
                        "eventType": "last_trade_price",
                        "assetId": asset_id,
                        "localTs": trade_ts.isoformat().replace("+00:00", "Z"),
                        "price": 0.51,
                        "side": "BUY",
                        "size": 20,
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
                min_trade_size=10,
                max_quote_age_ms=30_000,
                max_start_spread=0.05,
                min_samples=30,
                min_hit_rate=0.55,
                min_net=0.0025,
            ))

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["tradeFeatureRows"], 40)
        self.assertEqual(payload["watchResearchCount"], 1)
        self.assertEqual(payload["results"][0]["verdict"], "watch-research-only")


if __name__ == "__main__":
    unittest.main()
