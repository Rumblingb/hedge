import argparse
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.premarket_risk_brief import build_payload, daily_plan_path, default_markdown_path, render_markdown


class PremarketRiskBriefTest(unittest.TestCase):
    def test_blocked_control_state_forces_no_trade_algo_and_watch_only_strategies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "daily.md"
            goal = root / "goal.json"
            handoff = root / "handoff.json"
            source = root / "source.json"
            freshness = root / "freshness.json"
            signal = root / "signal.json"
            session = root / "session.json"
            finnhub = root / "finnhub.json"
            rss = root / "rss.json"
            alpha = root / "alpha.json"
            futures = root / "futures.json"
            sizing = root / "sizing.json"
            topstep_learning = root / "learning.json"

            daily.write_text(
                "No new Bill/Hermes orders approved.\n"
                "BILL_ROUTE_APPROVAL: BLOCKED\n"
                "BROKER_RECONCILIATION: UNKNOWN\n"
            )
            goal.write_text(json.dumps({
                "blockedCount": 3,
                "blockedIds": ["futures-demo-not-cleared", "source-hygiene-not-cleared"],
            }))
            handoff.write_text(json.dumps({"decision": "KEEP_EXECUTION_LOCKED"}))
            source.write_text(json.dumps({
                "sourceHygieneCleared": False,
                "sourceCleanBlockers": ["canonical source root has dirty files"],
            }))
            freshness.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            signal.write_text(json.dumps({
                "decision": "advisory-only; cannot approve, size, or route trades",
                "blockers": ["stale inputs: risk_sizing"],
                "warnings": ["shadow input refreshed from stale source data"],
            }))
            session.write_text(json.dumps({
                "topstepMultipleSessionsDetected": True,
                "pauseBrokerTouchingProofs": True,
                "reason": "Topstep reported multiple sessions",
            }))
            finnhub.write_text(json.dumps({"status": "BLOCKED_NO_DATA", "fetchErrors": {"calendar": "demo"}}))
            rss.write_text(json.dumps({"status": "PASS", "newsCount": 12}))
            alpha.write_text(json.dumps({
                "nextOneVariableTest": {
                    "id": "fabervaale-orb-broker-grade-5m-depth",
                    "lane": "futures",
                    "oneVariable": "data source/depth",
                    "command": "npm run --silent bill:futures-broker-parity-plan",
                }
            }))
            futures.write_text(json.dumps({
                "nextTests": [
                    {"id": "fabervaale-orb-walkforward-depth", "oneVariable": "walk-forward sample depth"}
                ]
            }))
            sizing.write_text(json.dumps({
                "bestProfileId": "fixed-2",
                "oneVariable": "position sizing only",
            }))
            topstep_learning.write_text(json.dumps({"decision": "demo-learning-visible-execution-locked"}))

            payload = build_payload(argparse.Namespace(
                daily_plan=str(daily),
                goal_audit=str(goal),
                clearance_handoff=str(handoff),
                source_hygiene=str(source),
                data_freshness=str(freshness),
                signal_quality=str(signal),
                topstep_session_safety=str(session),
                finnhub_news=str(finnhub),
                prediction_news_rss=str(rss),
                alpha_direction=str(alpha),
                futures_triage=str(futures),
                sizing_overlay=str(sizing),
                topstep_learning=str(topstep_learning),
            ))

        self.assertEqual(payload["decision"], "NO_TRADE_ALGO")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["sizingPosture"]["accountTruth"], "50K Topstep challenge/funded policy; 100K demo is calibration only")
        self.assertEqual(payload["sizingPosture"]["algoMaxContracts"], 0)
        self.assertEqual(payload["sizingPosture"]["manualWatchMaxContractsIfDailyPlanClears"], 0)
        risk_kinds = {item["kind"] for item in payload["risks"]}
        self.assertIn("daily-plan", risk_kinds)
        self.assertIn("broker-reconciliation", risk_kinds)
        self.assertIn("topstep-session-safety", risk_kinds)
        self.assertIn("data-freshness", risk_kinds)
        self.assertIn("signal-quality", risk_kinds)
        self.assertIn("news-source", risk_kinds)
        self.assertEqual(payload["strategyUseForDay"]["status"], "watch-only")
        candidate_ids = [item["id"] for item in payload["strategyUseForDay"]["candidates"]]
        self.assertIn("fabervaale-orb-broker-grade-5m-depth", candidate_ids)
        self.assertIn("50k-sizing-fixed-2", candidate_ids)

        markdown = render_markdown(payload)
        self.assertIn("NO_TRADE_ALGO", markdown)
        self.assertIn("algoMaxContracts", markdown)
        self.assertIn("50K Topstep challenge/funded policy", markdown)
        self.assertIn("Topstep multiple-session safety is active", markdown)
        self.assertIn("Strategy Use For Day", markdown)

    def test_default_paths_use_operator_london_date_not_utc_date(self):
        near_midnight_utc = datetime(2026, 6, 4, 23, 30, tzinfo=timezone.utc)

        self.assertTrue(str(daily_plan_path(near_midnight_utc)).endswith("2026-06-05-bill-trading-plan.md"))
        self.assertTrue(str(default_markdown_path(near_midnight_utc)).endswith("premarket-risk-brief-2026-06-05.md"))


if __name__ == "__main__":
    unittest.main()
