import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_event_timestamp_dataset import VAULT, build_dataset, default_markdown_path, render_markdown


class PredictionEventTimestampDatasetTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^prediction-event-timestamp-dataset-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "candidateCount": 0,
            "coverageStatusCounts": {},
            "completeWindowTargetCount": 0,
            "unrecoverablePreEventTargetCount": 0,
            "forwardCaptureRequired": False,
            "readyForPaper": False,
            "rows": [],
            "hardRules": [],
        })

        self.assertIn("# Prediction Event Timestamp Dataset - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_timestamp_dataset_marks_complete_and_unrecoverable_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clob = root / "clob.jsonl"
            event_time = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
            rows = [
                {
                    "eventType": "best_bid_ask",
                    "assetId": "complete",
                    "localTs": (event_time - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.49",
                    "bestAsk": "0.51",
                },
                {
                    "eventType": "best_bid_ask",
                    "assetId": "complete",
                    "localTs": (event_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.52",
                    "bestAsk": "0.54",
                },
                {
                    "eventType": "best_bid_ask",
                    "assetId": "post-only",
                    "localTs": (event_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.2",
                    "bestAsk": "0.22",
                },
            ]
            clob.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

            payload = build_dataset(
                mapping_plan={
                    "decision": "research-only-event-market-mapping-candidates-ready",
                    "candidates": [
                        {
                            "externalId": "market-complete",
                            "clobTokenId": "complete",
                            "articleDatetime": int(event_time.timestamp()),
                            "headline": "Iran update",
                            "question": "US x Iran permanent peace deal?",
                        },
                        {
                            "externalId": "market-post-only",
                            "clobTokenId": "post-only",
                            "articleDatetime": int(event_time.timestamp()),
                            "headline": "Fed update",
                            "question": "Fed rates?",
                        },
                    ],
                },
                clob_paths=[clob],
                pre_minutes=30,
                horizons_minutes=[15],
                generated_at_ms=int((event_time + timedelta(hours=1)).timestamp() * 1000),
            )

        by_id = {row["externalId"]: row for row in payload["rows"]}
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(by_id["market-complete"]["coverageStatus"], "window-range-present")
        self.assertEqual(by_id["market-complete"]["completePostWindowCount"], 1)
        self.assertEqual(by_id["market-post-only"]["coverageStatus"], "missing-pre-event-window")
        self.assertTrue(by_id["market-post-only"]["unrecoverablePreEvent"])
        self.assertTrue(payload["forwardCaptureRequired"])
        self.assertEqual(payload["completeWindowTargetCount"], 1)
        self.assertEqual(payload["unrecoverablePreEventTargetCount"], 1)


if __name__ == "__main__":
    unittest.main()
