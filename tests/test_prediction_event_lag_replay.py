import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_event_lag_replay import VAULT, build_replay, default_markdown_path, render_markdown


class PredictionEventLagReplayTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-event-lag-replay-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "completeEventCount": 0,
            "completeWindowCount": 0,
            "repricedWindowCount": 0,
            "blockers": [],
            "byHorizon": {},
            "hardRules": [],
        })

        self.assertIn("# Prediction Event Lag Replay - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_replay_stays_research_only_and_uses_pre_event_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clob = root / "clob.jsonl"
            event_time = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
            rows = []
            for idx in range(3):
                asset = f"asset-{idx}"
                rows.append({
                    "eventType": "best_bid_ask",
                    "assetId": asset,
                    "localTs": (event_time - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.49",
                    "bestAsk": "0.51",
                })
                rows.append({
                    "eventType": "best_bid_ask",
                    "assetId": asset,
                    "localTs": (event_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.52",
                    "bestAsk": "0.54",
                })
            clob.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            mapping = {
                "decision": "research-only-event-market-mapping-candidates-ready",
                "candidates": [
                    {
                        "externalId": f"market-{idx}",
                        "clobTokenId": f"asset-{idx}",
                        "articleDatetime": int(event_time.timestamp()),
                        "headline": "Iran ceasefire update",
                        "question": "US announces new Iran agreement?",
                    }
                    for idx in range(3)
                ],
            }
            payload = build_replay(
                mapping_plan=mapping,
                clob_paths=[clob],
                pre_minutes=30,
                horizons_minutes=[15],
                min_events=3,
                min_abs_move=0.01,
            )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["completeEventCount"], 3)
        self.assertEqual(payload["completeWindowCount"], 3)
        self.assertEqual(payload["repricedWindowCount"], 3)
        self.assertEqual(payload["decision"], "research-only-event-lag-replay-watch")
        self.assertGreaterEqual(payload["sampleWindows"][0]["preAgeSec"], 0)
        self.assertGreater(payload["sampleWindows"][0]["postDelaySec"], 0)

    def test_replay_blocks_without_pre_event_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clob = root / "clob.jsonl"
            event_time = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
            clob.write_text(json.dumps({
                "eventType": "best_bid_ask",
                "assetId": "asset-a",
                "localTs": (event_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                "bestBid": "0.52",
                "bestAsk": "0.54",
            }) + "\n")
            payload = build_replay(
                mapping_plan={
                    "candidates": [{
                        "externalId": "market-a",
                        "clobTokenId": "asset-a",
                        "articleDatetime": int(event_time.timestamp()),
                    }],
                },
                clob_paths=[clob],
                pre_minutes=30,
                horizons_minutes=[15],
                min_events=1,
            )

        self.assertEqual(payload["completeWindowCount"], 0)
        self.assertIn("too-few-complete-event-windows", payload["blockers"])
        self.assertIn("no-pre-event-quote-within-window", payload["missingReasonCounts"])

    def test_replay_uses_stable_thresholds_for_boundary_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clob = root / "clob.jsonl"
            event_time = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
            rows = [
                {
                    "eventType": "best_bid_ask",
                    "assetId": "asset-clears",
                    "localTs": (event_time - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.690",
                    "bestAsk": "0.700",
                },
                {
                    "eventType": "best_bid_ask",
                    "assetId": "asset-clears",
                    "localTs": (event_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.680",
                    "bestAsk": "0.690",
                },
                {
                    "eventType": "best_bid_ask",
                    "assetId": "asset-equals-half-spread",
                    "localTs": (event_time - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.170",
                    "bestAsk": "0.180",
                },
                {
                    "eventType": "best_bid_ask",
                    "assetId": "asset-equals-half-spread",
                    "localTs": (event_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.175",
                    "bestAsk": "0.185",
                },
            ]
            clob.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            mapping = {
                "candidates": [
                    {
                        "externalId": "clears-min-threshold",
                        "clobTokenId": "asset-clears",
                        "articleDatetime": int(event_time.timestamp()),
                    },
                    {
                        "externalId": "equals-half-spread",
                        "clobTokenId": "asset-equals-half-spread",
                        "articleDatetime": int(event_time.timestamp()),
                    },
                ],
            }

            payload = build_replay(
                mapping_plan=mapping,
                clob_paths=[clob],
                pre_minutes=30,
                horizons_minutes=[15],
                min_events=1,
                min_abs_move=0.01,
            )

        by_external_id = {item["externalId"]: item for item in payload["sampleWindows"]}
        clears = by_external_id["clears-min-threshold"]
        equals_half_spread = by_external_id["equals-half-spread"]
        self.assertEqual(clears["absMidMove"], 0.01)
        self.assertTrue(clears["clearsMinAbsMove"])
        self.assertTrue(clears["clearsHalfSpread"])
        self.assertTrue(clears["repriced"])
        self.assertEqual(equals_half_spread["absMoveAfterHalfSpread"], 0.0)
        self.assertFalse(equals_half_spread["clearsHalfSpread"])
        self.assertFalse(equals_half_spread["repriced"])


if __name__ == "__main__":
    unittest.main()
