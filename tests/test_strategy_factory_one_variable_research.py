import json
import tempfile
import unittest
from pathlib import Path

from scripts.strategy_factory_one_variable_research import build_queue, replace_arg


class Args:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class StrategyFactoryOneVariableResearchTest(unittest.TestCase):
    def test_build_queue_keeps_every_experiment_research_only_and_single_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = root / "strategy-factory.latest.json"
            data = root / "NQ-2022-2025-15m.csv"
            out_root = root / "research"
            output = root / "strategy-factory-one-variable-research.latest.json"
            factory.write_text(json.dumps({
                "status": "blocked",
                "blockers": ["walkforward result is not deployable"],
                "gates": {
                    "walkforwardDeployable": False,
                    "rollingOosWindows": 3,
                    "rollingOosDeployableWindows": 0,
                },
                "quantCoverage": {
                    "sampleSizeOk": True,
                    "inSampleBars": 210516,
                    "oosBars": 807057,
                    "profilesEvaluated": 3,
                    "profileSelection": {"selectedIds": ["orb-breakout-proven"]},
                },
                "researchContext": {
                    "noEdgeLedger": {
                        "needsMoreDataProfiles": 30,
                        "promotableProfiles": 0,
                    }
                },
            }))
            data.write_text("timestamp,open,high,low,close,volume\n")
            run_dir = out_root / "ny-morning-only"
            run_dir.mkdir(parents=True)
            (run_dir / "final_info.json").write_text(json.dumps({
                "AlphaStrategyTemplate": {
                    "means": {"candidate_count": 0, "ready_for_execution": False},
                    "experiment": {
                        "baseline_results": [
                            {
                                "baseline": {"id": "orb-breakout-15m", "strategy": "orb", "timeframe": "15m"},
                                "means": {"walkforward_positive_fold_share": 1.0},
                                "experiment": {
                                    "raw_trade_count": 302,
                                    "gate": {"kept": 165},
                                    "oos": {
                                        "trade_count": 50,
                                        "total_net_points": 713.25,
                                        "profit_factor": 1.46,
                                        "win_rate": 0.62,
                                    },
                                    "metric_blockers": ["walkforward-oos-profit-factor-too-low"],
                                    "research_candidate": False,
                                },
                            }
                        ]
                    },
                }
            }))

            payload = build_queue(Args(
                factory=str(factory),
                data=str(data),
                out_root=str(out_root),
                output=str(output),
            ))

        self.assertEqual(payload["decision"], "research-only-one-variable-queue")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["factoryDiagnosis"]["needsMoreDataProfiles"], 30)
        self.assertEqual(payload["experimentCount"], 6)
        self.assertEqual(payload["recommendedOrder"][0], "baseline-known-baselines-15m")
        self.assertTrue(payload["resultSummary"]["present"])
        self.assertEqual(payload["resultSummary"]["runCount"], 1)
        self.assertEqual(payload["resultSummary"]["bestObserved"]["baselineId"], "orb-breakout-15m")
        self.assertEqual(payload["resultSummary"]["bestObserved"]["oosTradeCount"], 50)
        self.assertFalse(payload["resultSummary"]["nextFollowUp"]["readyForExecution"])
        self.assertIn("walkforward PF/cost stress", payload["resultSummary"]["nextFollowUp"]["oneVariable"])

        baseline = payload["experiments"][0]
        self.assertEqual(baseline["oneVariable"], "none-baseline")
        self.assertIsNone(baseline["changedFlag"])

        changed = payload["experiments"][1:]
        for item in changed:
            self.assertTrue(item["researchOnly"])
            self.assertFalse(item["writesOrders"])
            self.assertFalse(item["touchesBroker"])
            self.assertFalse(item["readyForExecution"])
            self.assertIsInstance(item["changedFlag"], str)
            self.assertIsInstance(item["changedValue"], str)
            self.assertIn(item["changedFlag"], item["command"])
            self.assertIn("--strategy", item["command"])
            self.assertIn("known_baselines", item["command"])

        by_id = {item["id"]: item for item in payload["experiments"]}
        self.assertEqual(by_id["min-oos-trades-5"]["changedFlag"], "--min_oos_trades")
        self.assertEqual(by_id["min-oos-trades-5"]["changedValue"], "5")
        self.assertEqual(by_id["folds-3"]["changedFlag"], "--folds")
        self.assertEqual(by_id["max-trades-per-session-5"]["changedFlag"], "--max_trades_per_session")
        self.assertEqual(by_id["timeframe-agreement-1"]["changedFlag"], "--min_timeframe_agreement")
        self.assertEqual(by_id["ny-morning-only"]["changedFlag"], "--sessions")

    def test_replace_arg_changes_only_requested_flag_value(self):
        original = ["python", "experiment.py", "--folds", "5", "--min_oos_trades", "10"]
        updated = replace_arg(original, "--folds", "3")

        self.assertEqual(original, ["python", "experiment.py", "--folds", "5", "--min_oos_trades", "10"])
        self.assertEqual(updated, ["python", "experiment.py", "--folds", "3", "--min_oos_trades", "10"])


if __name__ == "__main__":
    unittest.main()
