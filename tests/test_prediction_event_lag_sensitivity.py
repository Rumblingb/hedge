import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.prediction_event_lag_sensitivity import build_sensitivity


class PredictionEventLagSensitivityTests(unittest.TestCase):
    def test_sensitivity_changes_one_variable_and_stays_research_only(self):
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
                    "bestAsk": "0.51",
                })
                rows.append({
                    "eventType": "best_bid_ask",
                    "assetId": asset,
                    "localTs": (event_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                    "bestBid": "0.491",
                    "bestAsk": "0.511",
                })
            clob.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            mapping = {
                "decision": "research-only-event-market-mapping-candidates-ready",
                "candidates": [
                    {
                        "externalId": f"market-{idx}",
                        "clobTokenId": f"asset-{idx}",
                        "articleDatetime": int(event_time.timestamp()),
                    }
                    for idx in range(3)
                ],
            }

            payload = build_sensitivity(
                mapping_plan=mapping,
                clob_paths=[clob],
                baseline_pre_minutes=30,
                baseline_horizons=[15],
                baseline_min_abs_move=0.01,
                pre_minutes_values=[15, 60],
                min_abs_move_values=[0.0005, 0.01],
                horizon_sets=[[15], [30]],
                min_events=3,
            )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["watchReady"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["scenarioCount"], 7)
        self.assertEqual(payload["bestCompleteWindowCount"], 3)
        self.assertEqual(payload["bestRepricedWindowCount"], 0)
        variables = {item["label"]: item["variable"] for item in payload["scenarios"]}
        self.assertEqual(variables["baseline"], "none")
        self.assertEqual(variables["pre-15m"], "preMinutes")
        self.assertEqual(variables["min-move-0.0005"], "minimumAbsMove")
        self.assertEqual(variables["horizons-30"], "horizonsMinutes")
        self.assertIn("sensitivity-no-repricing-under-tested-one-variable-grid", payload["blockers"])

    def test_watch_scenario_is_manual_research_not_paper_ready(self):
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
                    }
                    for idx in range(3)
                ],
            }

            payload = build_sensitivity(
                mapping_plan=mapping,
                clob_paths=[clob],
                baseline_pre_minutes=30,
                baseline_horizons=[15],
                baseline_min_abs_move=0.01,
                pre_minutes_values=[],
                min_abs_move_values=[],
                horizon_sets=[],
                min_events=3,
            )

        self.assertEqual(payload["decision"], "research-only-event-lag-sensitivity-watch")
        self.assertTrue(payload["watchReady"])
        self.assertEqual(payload["watchScenarioCount"], 1)
        self.assertGreater(payload["bestRepricedWindowCount"], 0)
        self.assertFalse(payload["readyForPaper"])


if __name__ == "__main__":
    unittest.main()
