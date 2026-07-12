import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_clob_latency_staleness_replay import build_report


class PredictionClobLatencyStalenessReplayTests(unittest.TestCase):
    def test_latency_staleness_replay_stays_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clob.jsonl"
            rows = []
            start = datetime(2026, 5, 30, tzinfo=timezone.utc)
            for idx in range(40):
                asset_id = f"asset-{idx}"
                prior_ts = start + timedelta(minutes=idx * 2)
                signal_ts = prior_ts + timedelta(seconds=5)
                future_ts = signal_ts + timedelta(seconds=20)
                for ts, bid, ask in [
                    (prior_ts, "0.49", "0.51"),
                    (signal_ts, "0.52", "0.54"),
                    (future_ts, "0.56", "0.58"),
                ]:
                    exchange_ms = int((ts - timedelta(milliseconds=250)).timestamp() * 1000)
                    rows.append({
                        "eventType": "best_bid_ask",
                        "assetId": asset_id,
                        "localTs": ts.isoformat().replace("+00:00", "Z"),
                        "exchangeTs": str(exchange_ms),
                        "bestBid": bid,
                        "bestAsk": ask,
                    })
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            payload = build_report(Namespace(
                input=str(path),
                windows=[15],
                lookback_sec=60,
                max_latency_ms=1_000,
                max_staleness_ms=10_000,
                min_abs_prior_move=0.005,
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
