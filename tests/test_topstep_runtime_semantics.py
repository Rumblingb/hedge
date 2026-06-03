import unittest
from pathlib import Path

from scripts import trade_journal


class TopstepRuntimeSemanticsTest(unittest.TestCase):
    def test_trade_journal_uses_mnq_point_value(self):
        self.assertEqual(trade_journal.POINT_VALUE, 2.0)

    def test_trade_journal_has_demo_numeric_account_fallback(self):
        self.assertEqual(trade_journal.TOPSTEP_DEMO_NUMERIC_ACCOUNT_ID, 22983191)
        source = Path("scripts/trade_journal.py").read_text()
        self.assertIn("RH_TOPSTEP_NUMERIC_ACCOUNT_ID", source)
        self.assertIn("RH_TOPSTEP_ACCOUNT_ID", source)
        self.assertIn("return TOPSTEP_DEMO_NUMERIC_ACCOUNT_ID", source)

    def test_trade_journal_handles_null_topstep_custom_tags(self):
        self.assertEqual(
            trade_journal.detect_sl_tp({"exit_order": {"customTag": None}}),
            (False, False),
        )

    def test_trade_journal_dry_run_does_not_save_last_seen_state(self):
        source = Path("scripts/trade_journal.py").read_text()
        self.assertIn("if not dry_run:\n            save_state", source)

    def test_trade_journal_uses_canonical_hedge_state_dir(self):
        self.assertEqual(
            trade_journal.STATE_DIR,
            Path.home() / "hedge" / ".rumbling-hedge" / "state",
        )
        self.assertEqual(
            trade_journal.JOURNAL_PATH,
            Path.home() / "hedge" / ".rumbling-hedge" / "state" / "trade-journal.jsonl",
        )
        self.assertIn("migrate_legacy_journal_state", Path("scripts/trade_journal.py").read_text())

    def test_read_only_broker_observers_fail_closed_on_env_and_session_safety(self):
        fill_check = (Path.home() / ".hermes/scripts/topstep_demo_fill_check.py").read_text()
        watchdog = (Path.home() / ".hermes/scripts/topstep_demo_watchdog.py").read_text()
        journal = Path("scripts/trade_journal.py").read_text()

        for source in (fill_check, watchdog, journal):
            self.assertIn("RH_TOPSTEP_READ_ONLY", source)
            self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION", source)
            self.assertIn("RH_LIVE_EXECUTION_ENABLED", source)
            self.assertIn("BILL_ALLOW_TOPSTEP_BROKER_SESSION_PROOF", source)
            self.assertIn("topstep-session-safety", source)

    def test_read_only_broker_observers_do_not_contain_mutating_topstep_endpoints(self):
        observers = [
            Path.home() / ".hermes/scripts/topstep_demo_fill_check.py",
            Path.home() / ".hermes/scripts/topstep_demo_watchdog.py",
            Path("scripts/trade_journal.py"),
        ]
        forbidden = [
            "/api/Order/place",
            "/api/Order/submit",
            "/api/Order/cancel",
            "/api/Order/modify",
            "/api/Position/close",
            "/api/Position/closeContract",
            "submitOrder",
            "placeOrder",
            "cancelOrder",
            "closePosition",
        ]
        for path in observers:
            source = path.read_text()
            for token in forbidden:
                self.assertNotIn(token, source, f"{path} contains mutating endpoint/token {token}")

    def test_hermes_fill_checker_uses_projectx_position_enum(self):
        path = Path.home() / ".hermes/scripts/topstep_demo_fill_check.py"
        source = path.read_text()

        self.assertIn("def position_type_label", source)
        self.assertIn("position_type == 1", source)
        self.assertIn('return "LONG"', source)
        self.assertIn("position_type == 2", source)
        self.assertIn('return "SHORT"', source)
        self.assertNotIn('side = "LONG" if p.get("type") == 0 else "SHORT"', source)

    def test_topstep_operating_logs_use_current_month(self):
        bridge = (Path.home() / ".hermes/scripts/topstep_demo_bridge.py").read_text()
        fill_check = (Path.home() / ".hermes/scripts/topstep_demo_fill_check.py").read_text()

        self.assertIn('VAULT / f"{ts[:7]}-operating-log.md"', bridge)
        self.assertIn('VAULT / f"{check_ts[:7]}-operating-log.md"', fill_check)
        self.assertNotIn('VAULT / "2026-05-operating-log.md"', bridge)
        self.assertNotIn('VAULT / "2026-05-operating-log.md"', fill_check)

    def test_topstep_demo_bridge_self_gates_direct_send_and_stale_signals(self):
        bridge = (Path.home() / ".hermes/scripts/topstep_demo_bridge.py").read_text()

        self.assertIn("MAX_SIGNAL_AGE_SECONDS", bridge)
        self.assertIn("signal timestamp missing; refuse replay", bridge)
        self.assertIn("stale signal artifact", bridge)
        self.assertIn("gate_ok, gate_reason = execution_gate(signal_data, dry_run=False)", bridge)
        self.assertIn('return False, f"execution_gate: {gate_reason}"', bridge)
        self.assertIn("skip, skip_reason = should_skip(signal_data)", bridge)

    def test_non_oco_topstep_protection_script_fails_closed(self):
        script = (Path.home() / ".hermes/scripts/topstep_check_and_protect.py").read_text()

        self.assertIn("Deprecated non-OCO protection helper", script)
        self.assertIn("BILL_ALLOW_NON_OCO_PROTECTION_SCRIPT", script)
        self.assertIn("BLOCKED: topstep_check_and_protect.py is deprecated non-OCO execution code.", script)
        self.assertIn("sys.exit(1)", script)

    def test_read_only_fill_checker_refreshes_broker_reconciliation(self):
        fill_check = (Path.home() / ".hermes/scripts/topstep_demo_fill_check.py").read_text()

        self.assertIn('STATE_DIR / "topstep-broker-reconciliation.latest.json"', fill_check)
        self.assertIn('STATE_DIR / "topstep-trade-journal-run.latest.json"', fill_check)
        self.assertIn('"broker_flat": len(positions) == 0', fill_check)
        self.assertIn('"writes_orders": False', fill_check)

    def test_guardrail_monitor_blocks_when_broker_position_is_open(self):
        monitor = (Path.home() / ".hermes/scripts/topstep_100k_guardrail_monitor.py").read_text()

        self.assertIn('broker_open_position_requires_manual_reconciliation', monitor)
        self.assertIn('reconciliation.get("broker_flat") is False', monitor)

    def test_watchdog_prefers_broker_reconciliation_over_tag_search(self):
        watchdog = (Path.home() / ".hermes/scripts/topstep_demo_watchdog.py").read_text()

        self.assertIn('topstep-broker-reconciliation.latest.json', watchdog)
        self.assertIn('reconciliation.get("broker_flat") is False', watchdog)
        self.assertIn("BROKER POSITION OPEN", watchdog)
        self.assertIn("Order.search tag matching is diagnostic", watchdog)

    def test_eod_review_uses_symbol_point_values(self):
        eod_review = (Path.home() / ".hermes/scripts/topstep_eod_review.py").read_text()

        self.assertIn("POINT_VALUES", eod_review)
        self.assertIn('parser.add_argument("--date"', eod_review)
        self.assertIn("review_date = date.fromisoformat", eod_review)
        self.assertIn('"MNQ": 2.0', eod_review)
        self.assertIn('"NQ": 20.0', eod_review)
        self.assertIn("def trade_pnl_dollars", eod_review)
        self.assertIn("point_value_for_trade(trade) * contracts", eod_review)
        self.assertIn("eodTrustworthy", eod_review)
        self.assertIn("pnlMismatchCount", eod_review)
        self.assertIn("UNRECONCILED - do not use for promotion/payout sizing", eod_review)
        self.assertIn("broker_flat", eod_review)
        self.assertNotIn("pnl_pts * 20 * contracts", eod_review)
        self.assertNotIn("pnl_pts * 20:+", eod_review)

    def test_hermes_60m_bridge_uses_mnq_two_dollar_point_value(self):
        bridge = (Path.home() / ".hermes/scripts/60m_exec_bridge.py").read_text()

        self.assertIn("MNQ point value: $2", bridge)
        self.assertIn("risk_per_contract = stop_distance * 2", bridge)
        self.assertIn("price_per_point = 2", bridge)
        self.assertNotIn("MNQ point value: $5", bridge)
        self.assertNotIn("risk_per_contract = stop_distance * 5", bridge)
        self.assertNotIn("price_per_point = 5", bridge)


if __name__ == "__main__":
    unittest.main()
