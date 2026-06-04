import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts import strategy_test_framework_status as status


class StrategyTestFrameworkStatusTest(unittest.TestCase):
    def test_build_status_blocks_stale_missing_and_non_deployable_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "ALL-6MARKETS-60m-60d-normalized.csv").write_text("ts,symbol,open,high,low,close,volume\n")
            payload = status.build_status(
                now=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
                data_dir=data_dir,
                matrix={
                    "generatedAt": "2026-05-31T21:45:42.785Z",
                    "status": "reject",
                    "csvPath": "/Users/brain/hedge/data/free/ALL-6MARKETS-60m-60d-normalized.csv",
                    "configs": [
                        {
                            "configId": "fixed-20d-5d",
                            "windowsEvaluated": 6,
                            "failureModes": ["stitched-oos-net-negative"],
                        }
                    ],
                },
                playbook={
                    "generatedAt": "2026-06-03T22:13:29+00:00",
                    "decision": "research-only-strategy-playbook; no execution approval",
                    "strategies": [{"id": "orb-breakout-15m"}],
                },
                factory={"walkforwardDeployable": False, "decision": "research-only"},
                goal={"decision": "continue-research-only-locked", "blockedIds": ["futures-demo-not-cleared"]},
                futures_no_edge={},
                one_variable={
                    "decision": "research-only-one-variable-queue",
                    "recommendedOrder": ["baseline-known-baselines-15m"],
                    "resultSummary": {
                        "bestObserved": {
                            "experimentId": "ny-morning-only",
                            "baselineId": "orb-breakout-15m",
                            "oosTradeCount": 50,
                            "oosNetPoints": 713.25,
                            "oosProfitFactor": 1.46,
                            "blockers": ["walkforward-oos-profit-factor-too-low"],
                        },
                        "nextFollowUp": {
                            "oneVariable": "walkforward PF/cost stress detail only",
                            "researchOnly": True,
                            "readyForExecution": False,
                        },
                    },
                },
            )

        self.assertEqual(payload["decision"], "research-only-strategy-framework-recovery-blocked")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertIn("requested-90d-1m-normalized-missing", payload["blockedIds"])
        self.assertIn("walkforward-matrix-stale", payload["blockedIds"])
        self.assertIn("walkforward-matrix-not-robust", payload["blockedIds"])
        self.assertIn("walkforward-matrix-rejection-not-recorded", payload["blockedIds"])
        self.assertIn("strategy-factory-not-deployable", payload["blockedIds"])
        self.assertEqual(payload["legacyDataRequests"][0]["status"], "missing")
        self.assertEqual(payload["walkforwardMatrix"]["totalWindowsEvaluated"], 6)
        self.assertEqual(payload["walkforwardMatrix"]["status"], "reject")
        self.assertEqual("factory-one-variable-ai-scientist-queue", payload["nextCommands"][0]["id"])
        self.assertIn("bill:strategy-factory-one-variable-research", payload["nextCommands"][0]["command"])
        self.assertIn("registration-and-matrix-smoke", [item["id"] for item in payload["nextCommands"]])
        self.assertTrue(payload["nextCommands"][-1]["operatorReviewRequired"])
        self.assertFalse(payload["futuresNoEdgeMemory"]["matrixRejectionRecorded"])
        self.assertEqual(
            payload["oneVariableResearch"]["resultSummary"]["bestObserved"]["baselineId"],
            "orb-breakout-15m",
        )
        self.assertEqual(
            payload["oneVariableResearch"]["resultSummary"]["nextFollowUp"]["oneVariable"],
            "walkforward PF/cost stress detail only",
        )

    def test_build_status_accepts_recorded_matrix_no_edge_memory(self):
        payload = status.build_status(
            now=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
            matrix={
                "generatedAt": "2026-06-04T11:00:00Z",
                "status": "reject",
                "configs": [{"configId": "fixed", "windowsEvaluated": 1, "failureModes": ["stitched-oos-net-negative"]}],
            },
            playbook={"generatedAt": "2026-06-04T11:00:00Z", "strategies": []},
            factory={"walkforwardDeployable": False},
            goal={},
            futures_no_edge={
                "generatedAt": "2026-06-04T11:05:00Z",
                "count": 6,
                "noEdgeCount": 5,
                "needsNewFeatureCount": 1,
                "learningSummary": ["matrix current family rejected"],
                "entries": [
                    {
                        "id": "six-market-walkforward-matrix-current-profile-family",
                        "verdict": "no-edge",
                    }
                ],
            },
            data_dir=Path(tempfile.gettempdir()) / "missing-strategy-test-data",
        )

        self.assertTrue(payload["futuresNoEdgeMemory"]["matrixRejectionRecorded"])
        self.assertEqual(payload["futuresNoEdgeMemory"]["matrixEntryVerdict"], "no-edge")
        self.assertNotIn("walkforward-matrix-rejection-not-recorded", payload["blockedIds"])
        self.assertNotIn("requested-90d-1m-normalized-missing", payload["blockedIds"])
        self.assertNotIn("requested-30d-oos-csv-missing", payload["blockedIds"])
        self.assertEqual(payload["legacyDataRequests"][0]["status"], "optional-after-data-source-review")

    def test_render_markdown_surfaces_stale_thread_rule(self):
        payload = {
            "generatedAt": "2026-06-04T12:00:00+00:00",
            "decision": "research-only-strategy-framework-recovery-blocked",
            "readyForExecution": False,
            "blockedIds": ["walkforward-matrix-stale"],
            "walkforwardMatrix": {
                "status": "reject",
                "csvPath": "data/free/ALL-6MARKETS-60m-60d-normalized.csv",
                "ageHours": 84.0,
                "totalWindowsEvaluated": 6,
            },
            "dataSets": {
                "currentDefaultMatrixCsv": {"exists": True, "path": "data/free/ALL-6MARKETS-60m-60d-normalized.csv"}
            },
            "legacyDataRequests": [
                {"id": "requested-90d-1m-normalized", "exists": False, "status": "optional-after-data-source-review"}
            ],
            "futuresNoEdgeMemory": {
                "present": True,
                "count": 6,
                "noEdgeCount": 5,
                "matrixRejectionRecorded": True,
            },
            "oneVariableResearch": {
                "present": True,
                "decision": "research-only-one-variable-queue",
                "resultSummary": {
                    "bestObserved": {
                        "experimentId": "ny-morning-only",
                        "baselineId": "orb-breakout-15m",
                        "oosTradeCount": 50,
                        "oosNetPoints": 713.25,
                        "oosProfitFactor": 1.46,
                        "blockers": ["walkforward-oos-profit-factor-too-low"],
                    },
                    "nextFollowUp": {
                        "oneVariable": "walkforward PF/cost stress detail only",
                        "why": "strongest blocked result",
                    },
                },
            },
            "nextCommands": [{"command": "npm run --silent bill:walkforward-matrix", "why": "refresh"}],
            "staleThreadRule": "Old demo-routing claims are stale.",
        }

        markdown = status.render_markdown(payload)

        self.assertIn("Strategy Test Framework Status", markdown)
        self.assertIn("Ready for execution: `False`", markdown)
        self.assertIn("Matrix rejection recorded: `True`", markdown)
        self.assertIn("Best observed still-blocked result", markdown)
        self.assertIn("walkforward PF/cost stress detail only", markdown)
        self.assertIn("Old demo-routing claims are stale.", markdown)

    def test_compact_output_is_json_shape(self):
        payload = status.build_status(
            now=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
            matrix={"generatedAt": "2026-06-04T11:00:00Z", "status": "research-only", "configs": []},
            playbook={"generatedAt": "2026-06-04T11:00:00Z", "strategies": []},
            factory={"walkforwardDeployable": False},
            goal={},
            futures_no_edge={},
            data_dir=Path(tempfile.gettempdir()) / "missing-strategy-test-data",
        )

        json.dumps({
            "decision": payload["decision"],
            "blockedIds": payload["blockedIds"],
            "matrixStatus": payload["walkforwardMatrix"]["status"],
            "readyForExecution": payload["readyForExecution"],
        })


if __name__ == "__main__":
    unittest.main()
