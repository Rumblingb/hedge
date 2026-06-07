import unittest

from scripts.topstep_daily_learning import (
    build_learning,
    parse_operating_fills,
    parse_operator_pnl_claims,
    parse_trade_journal_jsonl,
    parse_topstep_submissions,
    symbol_from_trade_id,
)


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

    def test_parses_operator_reported_pnl_as_context_not_broker_proof(self):
        claims = parse_operator_pnl_claims(
            "Operator-reported: Topstep 100K demo is up $3,000 and Friday losing day -$400."
        )

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["reportedNetUpDollars"], 3000.0)
        self.assertEqual(claims[0]["reportedLosingDayDollars"], -400.0)
        self.assertEqual(claims[0]["reportedLosingDayLabel"], "Friday")
        self.assertFalse(claims[0]["brokerProof"])
        self.assertEqual(claims[0]["promotionUse"], "context-only-until-broker-reconciled")

    def test_parses_trade_journal_jsonl_and_uses_it_when_reconciliation_has_no_matches(self):
        journal = parse_trade_journal_jsonl(
            '{"trade_id":"t1","direction":"SHORT","symbol":"CON.F.US.MNQ.M26","size":15,'
            '"entry_price":30664.0,"exit_price":30609.0,"pnl_pts":55.0,"pnl_dollars":1650.0,'
            '"entry_ts":"2026-06-03T15:37:09+00:00","exit_ts":"2026-06-03T15:44:35+00:00",'
            '"session":"NY_MORNING","day_of_week":"Wednesday"}\n'
        )
        payload = build_learning(
            operating_log_text=OPERATING_LOG,
            mistakes_text="",
            reconciliation={"broker_flat": True, "open_positions": 0, "fills_today": 2, "matched_trade_summary": []},
            submission={"side": "short", "signal": "manual", "submitted": False},
            guardrails={"limits": {"max_contracts": 15}, "bridge_config": {"sl_bracket_type": 4, "tp_bracket_type": 1}},
            watchdog={"sl_hit_total": 0, "tp_hit_total": 0},
            trade_journal_rows=journal,
            generated_at="2026-06-03T21:00:00+00:00",
        )

        self.assertEqual(payload["brokerReconciliation"]["tradeEvidenceSource"], "trade-journal")
        self.assertEqual(payload["brokerReconciliation"]["estimatedPnlDollars"], 1650.0)
        self.assertEqual(payload["tradeJournal"]["rowCount"], 1)
        self.assertEqual(payload["reconciledTrades"][0]["tradeId"], "t1")

    def test_session_shadow_observations_are_learning_only_until_broker_proof(self):
        journal = parse_trade_journal_jsonl(
            '{"trade_id":"OBS-LONG-MNQ-20260608-143500-1",'
            '"source":"session-shadow-manual-observation",'
            '"direction":"LONG","symbol":"MNQ","size":1,'
            '"entry_price":30000.0,"exit_price":30012.5,'
            '"pnl_pts":12.5,"pnl_dollars":25.0,'
            '"entry_ts":"2026-06-08T14:35:00+00:00","exit_ts":"2026-06-08T14:45:00+00:00",'
            '"session":"NY_MORNING","day_of_week":"Monday",'
            '"observationOnly":true,"brokerProof":false,'
            '"promotionUse":"demo-observation-learning-only-until-broker-reconciled"}\n'
        )
        payload = build_learning(
            operating_log_text="",
            mistakes_text="",
            reconciliation={"ts": "2026-06-08T20:55:44+00:00", "broker_flat": True, "open_positions": 0},
            submission={"side": "long"},
            guardrails={"limits": {"max_contracts": 1}, "bridge_config": {"sl_bracket_type": 4, "tp_bracket_type": 1}},
            watchdog={},
            trade_journal_rows=journal,
        )

        issue_ids = {row["id"] for row in payload["issues"]}
        self.assertEqual(payload["brokerReconciliation"]["tradeEvidenceSource"], "trade-journal")
        self.assertEqual(payload["reconciledTrades"][0]["source"], "session-shadow-manual-observation")
        self.assertTrue(payload["reconciledTrades"][0]["observationOnly"])
        self.assertFalse(payload["reconciledTrades"][0]["brokerProof"])
        self.assertEqual(
            payload["reconciledTrades"][0]["promotionUse"],
            "demo-observation-learning-only-until-broker-reconciled",
        )
        self.assertIn("journal-observation-needs-broker-proof", issue_ids)
        self.assertFalse(payload["readyForDemoExpansion"])

    def test_trade_journal_fallback_filters_to_reconciliation_date(self):
        journal = parse_trade_journal_jsonl(
            '{"trade_id":"SHORT-CON.F.US.MNQ.M26-20260529-111750-20260529-111750",'
            '"direction":"SHORT","size":1,"entry_price":30323.25,"exit_price":30363.75,'
            '"pnl_pts":-40.5,"pnl_dollars":-202.5,'
            '"entry_ts":"2026-05-29T11:17:50+00:00","exit_ts":"2026-05-29T11:17:50+00:00"}\n'
            '{"trade_id":"SHORT-CON.F.US.MNQ.M26-20260603-153709-20260603-154435",'
            '"direction":"SHORT","size":15,"entry_price":30664.0,"exit_price":30609.0,'
            '"pnl_pts":55.0,"pnl_dollars":1650.0,'
            '"entry_ts":"2026-06-03T15:37:09+00:00","exit_ts":"2026-06-03T15:44:35+00:00"}\n'
        )
        payload = build_learning(
            operating_log_text=OPERATING_LOG,
            mistakes_text="",
            reconciliation={"ts": "2026-06-03T20:55:44+00:00", "broker_flat": True, "open_positions": 0},
            submission={"side": "short"},
            guardrails={"limits": {"max_contracts": 20}, "bridge_config": {"sl_bracket_type": 4, "tp_bracket_type": 1}},
            watchdog={},
            trade_journal_rows=journal,
        )

        self.assertEqual(symbol_from_trade_id("SHORT-CON.F.US.MNQ.M26-20260603-153709-20260603-154435"), "CON.F.US.MNQ.M26")
        self.assertEqual(payload["tradeJournal"]["totalRowCount"], 2)
        self.assertEqual(payload["tradeJournal"]["rowCount"], 1)
        self.assertEqual(payload["brokerReconciliation"]["totalMatchedSize"], 15)
        self.assertEqual(payload["brokerReconciliation"]["estimatedPnlDollars"], 1650.0)

    def test_build_learning_flags_side_size_and_bracket_issues_without_execution(self):
        payload = build_learning(
            operating_log_text=OPERATING_LOG,
            mistakes_text=(
                "env drift BILL_ENABLE_FUTURES_DEMO_EXECUTION=true recorded\n"
                "Operator-reported: Topstep 100K demo is up $3,000 and Friday losing day -$400."
            ),
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
        self.assertIn("operator-pnl-claim-needs-broker-proof", issue_ids)
        self.assertEqual(payload["brokerReconciliation"]["estimatedPnlDollars"], -324.0)
        self.assertEqual(payload["operatorReportedPnl"]["claimCount"], 1)
        self.assertTrue(payload["operatorReportedPnl"]["brokerProofRequired"])
        self.assertEqual(payload["accountSizing"]["liveChallengeSizingAccount"], "50K")
        self.assertEqual(payload["accountSizing"]["demoCalibrationAccount"], "100K")
        self.assertEqual(payload["accountSizing"]["challengeInstrument"], "MNQ")
        self.assertIn(
            "100K demo results are calibration context only",
            payload["nextActions"][1],
        )
        self.assertTrue(payload["mustUpdateMistakes"])

    def test_build_learning_flags_active_broker_position_as_p0(self):
        payload = build_learning(
            operating_log_text=OPERATING_LOG,
            mistakes_text="",
            reconciliation={
                "ts": "2026-06-01T16:11:09+00:00",
                "broker_flat": False,
                "open_positions": 1,
                "fills_today": 1,
                "matched_trades": None,
                "matched_trade_summary": [],
            },
            submission={"side": "long", "signal": "long@orb-breakout", "submitted": True},
            guardrails={"limits": {"max_contracts": 1}, "bridge_config": {"sl_bracket_type": 4, "tp_bracket_type": 1}},
            watchdog={"sl_hit_total": 0, "tp_hit_total": 0},
            generated_at="2026-06-01T16:12:00+00:00",
        )

        issue_ids = {row["id"] for row in payload["issues"]}
        self.assertIn("broker-open-position-active", issue_ids)
        self.assertTrue(payload["mustUpdateMistakes"])
        self.assertFalse(payload["readyForDemoExpansion"])


if __name__ == "__main__":
    unittest.main()
