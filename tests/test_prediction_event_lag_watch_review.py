import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_event_lag_watch_review import build_review


class PredictionEventLagWatchReviewTests(unittest.TestCase):
    def test_materializes_watch_windows_without_paper_or_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clob = root / "clob.jsonl"
            event_time = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
            rows = []
            for idx in range(3):
                asset = f"asset-{idx}"
                rows.append({
                    "eventType": "best_bid_ask",
                    "assetId": asset,
                    "localTs": (event_time - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.49",
                    "bestAsk": "0.50",
                })
                rows.append({
                    "eventType": "best_bid_ask",
                    "assetId": asset,
                    "localTs": (event_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.55",
                    "bestAsk": "0.56",
                })
            clob.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            mapping = {
                "candidates": [
                    {
                        "externalId": f"market-{idx}",
                        "clobTokenId": f"asset-{idx}",
                        "articleDatetime": int(event_time.timestamp()),
                        "question": f"Question {idx}?",
                    }
                    for idx in range(3)
                ],
            }
            sensitivity = {
                "decision": "research-only-event-lag-sensitivity-watch",
                "baseline": {
                    "preMinutes": 30,
                    "horizonsMinutes": [15],
                    "minimumAbsMove": 0.01,
                    "minimumCompleteEvents": 3,
                },
                "scenarios": [
                    {
                        "label": "min-move-0.005",
                        "variable": "minimumAbsMove",
                        "value": 0.005,
                        "decision": "research-only-event-lag-replay-watch",
                    },
                    {
                        "label": "pre-60m",
                        "variable": "preMinutes",
                        "value": 60,
                        "decision": "research-only-event-lag-replay-blocked",
                    },
                ],
            }

            payload = build_review(sensitivity=sensitivity, mapping_plan=mapping, clob_paths=[clob])

        self.assertEqual(payload["decision"], "research-only-event-lag-watch-review-visible")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertTrue(payload["watchReady"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["watchScenarioCount"], 1)
        self.assertEqual(payload["repricedWatchWindowCount"], 3)
        self.assertEqual(payload["scenarioReviews"][0]["label"], "min-move-0.005")
        self.assertEqual(payload["watchWindows"][0]["question"], "Question 0?")
        self.assertIn("manual-review-required-before-forward-capture-or-paper-discussion", payload["blockers"])

    def test_blocks_when_sensitivity_has_no_watch_scenarios(self):
        payload = build_review(
            sensitivity={
                "decision": "research-only-event-lag-sensitivity-blocked",
                "baseline": {"preMinutes": 30, "horizonsMinutes": [15], "minimumAbsMove": 0.01, "minimumCompleteEvents": 3},
                "scenarios": [],
            },
            mapping_plan={"candidates": []},
            clob_paths=[],
        )

        self.assertEqual(payload["decision"], "research-only-event-lag-watch-review-blocked")
        self.assertFalse(payload["watchReady"])
        self.assertIn("no-watch-scenarios-from-sensitivity", payload["blockers"])
        self.assertFalse(payload["readyForPaper"])

    def test_dedupes_same_window_across_threshold_scenarios(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clob = root / "clob.jsonl"
            event_time = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
            clob.write_text("\n".join(json.dumps(row) for row in [
                {
                    "eventType": "best_bid_ask",
                    "assetId": "asset-1",
                    "localTs": (event_time - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.49",
                    "bestAsk": "0.50",
                },
                {
                    "eventType": "best_bid_ask",
                    "assetId": "asset-1",
                    "localTs": (event_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.55",
                    "bestAsk": "0.56",
                },
            ]) + "\n")
            mapping = {
                "candidates": [
                    {
                        "externalId": "market-1",
                        "clobTokenId": "asset-1",
                        "articleDatetime": int(event_time.timestamp()),
                    }
                ],
            }
            sensitivity = {
                "baseline": {"preMinutes": 30, "horizonsMinutes": [15], "minimumAbsMove": 0.01, "minimumCompleteEvents": 1},
                "scenarios": [
                    {"label": "min-move-0.0025", "variable": "minimumAbsMove", "value": 0.0025, "decision": "research-only-event-lag-replay-watch"},
                    {"label": "min-move-0.005", "variable": "minimumAbsMove", "value": 0.005, "decision": "research-only-event-lag-replay-watch"},
                ],
            }

            payload = build_review(sensitivity=sensitivity, mapping_plan=mapping, clob_paths=[clob])

        self.assertEqual(payload["scenarioRepricedWindowCount"], 2)
        self.assertEqual(payload["repricedWatchWindowCount"], 1)
        self.assertEqual(payload["duplicateScenarioWindowCount"], 1)


if __name__ == "__main__":
    unittest.main()
