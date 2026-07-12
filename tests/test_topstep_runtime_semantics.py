import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts import master_bridge, trade_journal


class TopstepRuntimeSemanticsTest(unittest.TestCase):
    def test_trade_journal_uses_mnq_point_value(self):
        self.assertEqual(trade_journal.POINT_VALUE, 2.0)

    def test_trade_journal_has_demo_numeric_account_fallback(self):
        self.assertEqual(trade_journal.TOPSTEP_DEMO_NUMERIC_ACCOUNT_ID, 22983191)
        source = Path("scripts/trade_journal.py").read_text()
        self.assertIn("RH_TOPSTEP_NUMERIC_ACCOUNT_ID", source)
        self.assertIn("RH_TOPSTEP_ACCOUNT_ID", source)
        self.assertIn("return TOPSTEP_DEMO_NUMERIC_ACCOUNT_ID", source)

    def test_trade_journal_prefers_exact_reconciliation_account_binding(self):
        source = Path("scripts/trade_journal.py").read_text()
        self.assertIn('"RH_TOPSTEP_RECONCILE_ACCOUNT_ID"', source)
        with mock.patch.dict("os.environ", {"RH_TOPSTEP_RECONCILE_ACCOUNT_ID": "23536817"}, clear=False):
            self.assertEqual(trade_journal.read_account_id(), 23536817)

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

        self.assertIn("RH_TOPSTEP_RECONCILE_ACCOUNT_ID", fill_check)
        self.assertIn("must be a numeric ProjectX account id", fill_check)

    def test_read_only_broker_observers_do_not_contain_mutating_topstep_endpoints(self):
        # Strict observers: must contain zero mutating endpoints/tokens.
        observers = [
            Path.home() / ".hermes/scripts/topstep_demo_fill_check.py",
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

    def test_watchdog_autoflatten_is_the_only_guarded_mutation_path(self):
        """The watchdog is read-only by default. Its only mutating endpoint
        (/api/Position/closeContract) must be strictly gated behind the
        explicit BILL_WATCHDOG_AUTOFLATTEN env flag, and it must not contain
        any order-placement/cancellation endpoints."""
        path = Path.home() / ".hermes/scripts/topstep_demo_watchdog.py"
        source = path.read_text()

        forbidden = [
            "/api/Order/place",
            "/api/Order/submit",
            "/api/Order/cancel",
            "/api/Order/modify",
            "submitOrder",
            "placeOrder",
            "cancelOrder",
            "closePosition",
        ]
        for token in forbidden:
            self.assertNotIn(token, source, f"{path} contains mutating endpoint/token {token}")

        self.assertIn("/api/Position/closeContract", source)
        self.assertIn("BILL_WATCHDOG_AUTOFLATTEN", source)
        self.assertIn("def flatten_position", source)
        self.assertIn("def kill_switch_triggered", source)
        # flatten_position must only be reachable through the autoflatten gate.
        self.assertIn('truthy(read_flag("BILL_WATCHDOG_AUTOFLATTEN"))', source)

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

    def test_topstep_demo_bridge_pre_submit_position_check(self):
        bridge = (Path.home() / ".hermes/scripts/topstep_demo_bridge.py").read_text()

        self.assertIn("def pre_submit_position_check(token):", bridge)
        self.assertIn("/api/Position/searchOpen", bridge)
        self.assertIn("pre_submit_position_check(token)", bridge)
        self.assertIn("write_reconciliation_artifact", bridge)
        self.assertIn('return False, pre_submit_detail', bridge)
        # main() must abort with non-zero exit when pre-submit finds a position.
        self.assertIn('detail.startswith("pre_submit_position_check:")', bridge)
        self.assertIn("sys.exit(1)", bridge)

    def test_topstep_demo_bridge_orphan_auto_remediation(self):
        bridge = (Path.home() / ".hermes/scripts/topstep_demo_bridge.py").read_text()

        self.assertIn("def close_position(token, contract_id):", bridge)
        self.assertIn("/api/Position/closeContract", bridge)
        self.assertIn("def cancel_order(token, order_id):", bridge)
        self.assertIn("/api/Order/cancel", bridge)
        self.assertIn("def cancel_residual_orders(", bridge)
        self.assertIn("action_taken", bridge)
        self.assertIn("orphan-order-alert.latest.json", bridge)
        # Orphan remediation must still write the alert artifact even when it succeeds.
        self.assertIn('"remediation": remediation', bridge)

    def test_topstep_demo_bridge_partial_fill_validation(self):
        bridge = (Path.home() / ".hermes/scripts/topstep_demo_bridge.py").read_text()

        self.assertIn("requested_size", bridge)
        self.assertIn("0 < filled_qty < requested_size", bridge)
        self.assertIn("partial-fill-alert.latest.json", bridge)
        self.assertIn("verify_bracket_orders(token, entry_order_id, contract_id, requested_size=sz)", bridge)

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


class MasterBridgeReconciliationFreshnessTest(unittest.TestCase):
    def _write_reconciliation(self, state_dir, ts, broker_flat):
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "topstep-broker-reconciliation.latest.json").write_text(json.dumps({
            "ts": ts,
            "account_id": 22983191,
            "open_positions": 0 if broker_flat else 1,
            "positions": [],
            "broker_flat": broker_flat,
            "source": "topstep_demo_fill_check",
        }))

    def test_blocks_when_artifact_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(master_bridge, "CANONICAL_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "LEGACY_STATE_DIR", state_dir):
                blockers = master_bridge.reconciliation_freshness_blockers()
        self.assertTrue(any("missing" in b for b in blockers))

    def test_blocks_when_artifact_stale_even_after_refresh_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            self._write_reconciliation(state_dir, stale_ts, broker_flat=True)
            with mock.patch.object(master_bridge, "CANONICAL_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "LEGACY_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "_refresh_reconciliation_artifact") as refresh:
                blockers = master_bridge.reconciliation_freshness_blockers()
        refresh.assert_called_once()
        self.assertTrue(any("stale" in b for b in blockers))

    def test_blocks_when_fresh_but_not_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            fresh_ts = datetime.now(timezone.utc).isoformat()
            self._write_reconciliation(state_dir, fresh_ts, broker_flat=False)
            with mock.patch.object(master_bridge, "CANONICAL_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "LEGACY_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "_refresh_reconciliation_artifact") as refresh:
                blockers = master_bridge.reconciliation_freshness_blockers()
        refresh.assert_called_once()
        self.assertTrue(any("broker_flat" in b for b in blockers))

    def test_passes_when_fresh_and_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            fresh_ts = datetime.now(timezone.utc).isoformat()
            self._write_reconciliation(state_dir, fresh_ts, broker_flat=True)
            with mock.patch.object(master_bridge, "CANONICAL_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "LEGACY_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "_refresh_reconciliation_artifact") as refresh:
                blockers = master_bridge.reconciliation_freshness_blockers()
        refresh.assert_not_called()
        self.assertEqual(blockers, [])

    def test_recovers_when_refresh_writes_fresh_flat_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            self._write_reconciliation(state_dir, stale_ts, broker_flat=True)

            def fake_refresh():
                fresh_ts = datetime.now(timezone.utc).isoformat()
                self._write_reconciliation(state_dir, fresh_ts, broker_flat=True)

            with mock.patch.object(master_bridge, "CANONICAL_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "LEGACY_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "_refresh_reconciliation_artifact", side_effect=fake_refresh) as refresh:
                blockers = master_bridge.reconciliation_freshness_blockers()
        refresh.assert_called_once()
        self.assertEqual(blockers, [])

    def test_execution_firewall_decision_includes_reconciliation_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            with mock.patch.object(master_bridge, "CANONICAL_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "LEGACY_STATE_DIR", state_dir),                  mock.patch.object(master_bridge, "_refresh_reconciliation_artifact"):
                decision = master_bridge.execution_firewall_decision()
        self.assertFalse(decision["allowed"])
        self.assertTrue(any("broker reconciliation artifact is missing" in b for b in decision["blockers"]))

    def test_refresh_helper_skips_during_pytest(self):
        # PYTEST_CURRENT_TEST is set by pytest itself during test runs.
        self.assertIn("PYTEST_CURRENT_TEST", Path("scripts/master_bridge.py").read_text())
        with mock.patch("subprocess.run") as run:
            master_bridge._refresh_reconciliation_artifact()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
