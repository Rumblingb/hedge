import unittest

from scripts.topstep_daily_learning import build_learning, parse_operating_fills, parse_topstep_submissions


OPERATING_LOG = """
### Topstep Demo — 2026-05-29T11:18:31.312272+00:00
- Signal: `long@pre-trade-check` | Side: long | Entry: $30363.75 | SL: $30323.15 | TP: $30431.35
- Strategy: pre-trade-check
- Entry Order: 3046589723
- Result: submitted_with_oco_brackets

### Position Check — 2026-05-29T11:18:34.410328+00:00
- 🔴 OPEN: CON.F.US.MNQ.M26 SHORT 5 @ $30364.35
- ✅ NEW FILL: CON.F.US.MNQ.M26 BUY 4 @ $30364.50
"""


class TopstepDailyLearningTest(unittest.TestCase):
    def test_parses_operating_submissions_and_fills(self):
        submissions = parse_topstep_submissions(OPERATING_LOG)
        fills = parse_operating_fills(OPERATING_LOG)

        self.assertEqual(len(submissions), 1)
        self.assertEqual(submissions[0]["side"], "long")
        self.assertEqual(submissions[0]["entryOrder"], 3046589723)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0]["side"], "BUY")
        self.assertEqual(fills[0]["size"], 4)

    def test_build_learning_flags_side_size_and_bracket_issues_without_execution(self):
        payload = build_learning(
            operating_log_text=OPERATING_LOG,
            mistakes_text="env drift BILL_ENABLE_FUTURES_DEMO_EXECUTION=true recorded",
            reconciliation={
                "ts": "2026-05-29T18:54:24+00:00",
                "broker_flat": True,
                "open_positions": 0,
                "fills_today": 6,
                "matched_trades": 1,
                "matched_trade_summary": [
                    {
                        "direction": "SHORT",
                        "symbol": "CON.F.US.MNQ.M26",
                        "size": 4,
                        "entry_ts": "2026-05-29T11:18:31+00:00",
                        "exit_ts": "2026-05-29T11:18:31+00:00",
                        "entry_price": 30324.0,
                        "exit_price": 30364.5,
                    }
                ],
            },
            submission={"side": "long", "signal": "long@pre-trade-check", "submitted": True},
            guardrails={
                "limits": {"max_contracts": 1},
                "mode": {"read_only": False, "demo_only_required": True},
                "bridge_config": {"sl_bracket_type": 4, "tp_bracket_type": 2},
            },
            watchdog={"sl_hit_total": 5, "tp_hit_total": 0, "last_flat_status": True, "check_count": 81},
            generated_at="2026-06-01T00:00:00+00:00",
        )

        issue_ids = {row["id"] for row in payload["issues"]}
        self.assertEqual(payload["decision"], "demo-learning-visible-execution-locked")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertIn("intended-vs-reconciled-side-mismatch", issue_ids)
        self.assertIn("reconciled-size-exceeds-current-max-contracts", issue_ids)
        self.assertIn("guardrail-tp-bracket-type-stale", issue_ids)
        self.assertIn("demo-day-all-stops-no-targets", issue_ids)
        self.assertEqual(payload["brokerReconciliation"]["estimatedPnlDollars"], -324.0)
        self.assertTrue(payload["mustUpdateMistakes"])


if __name__ == "__main__":
    unittest.main()
