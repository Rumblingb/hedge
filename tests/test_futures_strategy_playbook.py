import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scripts import futures_strategy_playbook as playbook


class FuturesStrategyPlaybookTest(unittest.TestCase):
    def test_build_payload_is_research_only_and_ranks_current_gold_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            goal = root / "goal.json"
            handoff = root / "handoff.json"
            premarket = root / "premarket.json"
            futures = root / "futures.json"
            session = root / "session.json"
            one_variable = root / "one-variable.json"
            sizing = root / "sizing.json"
            learning = root / "learning.json"
            goal.write_text(json.dumps({
                "decision": "continue-research-only-locked",
                "blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"],
            }))
            handoff.write_text(json.dumps({"decision": "KEEP_EXECUTION_LOCKED", "readyForExecution": False}))
            premarket.write_text(json.dumps({
                "decision": "NO_TRADE_ALGO",
                "sizingPosture": {"algoMaxContracts": 0, "manualWatchMaxContractsIfDailyPlanClears": 0},
                "riskCounts": {"hard": 2, "reduce": 1},
                "risks": [
                    {"severity": "hard", "kind": "daily-plan", "reason": "blocked"},
                    {"severity": "reduce", "kind": "signal-quality-warning", "reason": "warning"},
                ],
            }))
            futures.write_text(json.dumps({"decision": "research-only; no futures strategy is currently demo-expandable"}))
            session.write_text(json.dumps({
                "topstepMultipleSessionsDetected": True,
                "pauseBrokerTouchingProofs": True,
                "reason": "multiple sessions",
            }))
            one_variable.write_text(json.dumps({
                "resultSummary": {
                    "bestObserved": {
                        "baselineId": "orb-breakout-15m",
                        "experimentId": "ny-morning-only",
                        "oosTradeCount": 50,
                        "oosProfitFactor": 1.46,
                        "walkforwardPositiveFoldShare": 1.0,
                        "blockers": ["walkforward-oos-profit-factor-too-low"],
                    }
                }
            }))
            sizing.write_text(json.dumps({
                "decision": "research-only-sizing-overlay-watch",
                "bestProfileId": "fixed-2",
                "assumptions": {"accountSize": "50K", "instrument": "MNQ"},
                "profileResults": [
                    {
                        "id": "fixed-2",
                        "blockers": [],
                        "summary": {"netPnl": 6366.0, "maxDrawdown": 1477.0},
                        "dailyStats": {"bestDayPnl": 913.0},
                        "bestDayPnl": 913.0,
                        "consistencyShare": 0.14,
                    }
                ],
            }))
            learning.write_text(json.dumps({
                "issues": [{"id": "intended-vs-reconciled-side-mismatch", "severity": "P1"}]
            }))

            payload = playbook.build_payload(argparse.Namespace(
                goal_audit=str(goal),
                clearance_handoff=str(handoff),
                premarket_risk_brief=str(premarket),
                futures_evidence_triage=str(futures),
                topstep_session_safety=str(session),
                strategy_factory_one_variable=str(one_variable),
                sizing_overlay=str(sizing),
                topstep_learning=str(learning),
            ))

        self.assertEqual(payload["decision"], "research-only-strategy-playbook; no execution approval")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["accountTruth"]["liveChallengeAccount"], "Topstep 50K")
        self.assertIn("topstep-session-safety", payload["hardBlockers"])
        self.assertIn("goal-audit-blocked", payload["hardBlockers"])
        self.assertIn("premarket-no-trade", payload["hardBlockers"])

        by_id = {row["id"]: row for row in payload["strategies"]}
        self.assertEqual(by_id["orb-breakout-15m"]["rank"], 1)
        self.assertEqual(by_id["orb-breakout-15m"]["currentEvidence"]["experimentId"], "ny-morning-only")
        self.assertEqual(by_id["wq-vol-regime-60m"]["executionPolicy"], "blocked from demo/live; research-only")
        self.assertTrue(any(
            "walkforward OOS remains negative" in item
            for item in by_id["wq-vol-regime-60m"]["doNotUseWhen"]
        ))
        self.assertIn("prediction-market signals may be context overlays only", " ".join(payload["globalRules"]).lower())
        self.assertEqual(payload["dailyTacticalPlan"]["decision"], "stand-down")
        self.assertEqual(payload["dailyTacticalPlan"]["maxAlgoContracts"], 0)
        self.assertEqual(payload["dailyTacticalPlan"]["preferredWatch"]["strategyId"], "orb-breakout-15m")
        self.assertIn("intended-vs-reconciled-side-mismatch", json.dumps(payload["dailyTacticalPlan"]["demoLearningIssues"]))

    def test_render_markdown_surfaces_no_execution_permission(self):
        payload = {
            "decision": "research-only-strategy-playbook; no execution approval",
            "readyForExecution": False,
            "hardBlockers": ["topstep-session-safety"],
            "gateSnapshot": {"premarketDecision": "NO_TRADE_ALGO"},
            "accountTruth": {"liveChallengeAccount": "Topstep 50K"},
            "globalRules": ["LLMs research, deterministic algos route only after gates clear."],
            "dailyTacticalPlan": {
                "decision": "stand-down",
                "maxAlgoContracts": 0,
                "maxManualWatchContractsIfHumanClearsDailyPlan": 0,
                "preferredWatch": {"strategyId": "orb-breakout-15m"},
                "demoLearningIssues": [{"id": "issue"}],
                "redFolderAndRiskDownRules": ["No-trade is valid."],
            },
            "strategies": [
                {
                    "id": "orb-breakout-15m",
                    "rank": 1,
                    "role": "primary candidate",
                    "timeframe": "15m",
                    "session": "NY morning",
                    "knownParams": {"rangeWindow": 8},
                    "currentEvidence": {"experimentId": "ny-morning-only"},
                    "executionPolicy": "research-only until all gates clear",
                    "useWhen": ["broker data fresh"],
                    "doNotUseWhen": ["session warning active"],
                    "promotionEvidenceNeeded": ["walkforward"],
                }
            ],
            "nextEvidenceQueue": ["clear session warning"],
        }

        markdown = playbook.render_markdown(payload)

        self.assertIn("Research-only strategy map", markdown)
        self.assertIn("Ready for execution: `False`", markdown)
        self.assertIn("Daily Tactical Plan", markdown)
        self.assertIn("Risk-Down Rules", markdown)
        self.assertIn("`orb-breakout-15m`", markdown)


if __name__ == "__main__":
    unittest.main()
