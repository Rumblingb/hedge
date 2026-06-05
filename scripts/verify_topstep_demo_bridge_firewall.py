#!/usr/bin/env python3
"""Verify Topstep demo bridge firewall invariants without broker auth or orders."""

import importlib.util
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

BRIDGE_PATH = Path.home() / ".hermes" / "scripts" / "topstep_demo_bridge.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("topstep_demo_bridge_under_test", BRIDGE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {BRIDGE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def patched_env(values):
    old = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_daily(path: Path, text: str):
    daily = path
    daily.parent.mkdir(parents=True, exist_ok=True)
    daily.write_text(text, encoding="utf-8")
    return daily


def assert_reason(reason, expected):
    if expected not in reason:
        raise AssertionError(f"expected reason containing {expected!r}; got {reason!r}")


def valid_signal():
    return {
        "ts": "2026-05-29T00:00:00Z",
        "signal": "long@firewall-test",
        "strategy": "firewall-test",
        "side": "long",
        "entry": 100.0,
        "stop": 99.0,
        "target": 102.0,
        "contracts": 1,
        "route": "topstep_demo",
        "submitted": None,
        "status": "pending_topstep_demo_submission",
        "execution_firewall": {"allowed": True, "blockers": []},
    }


def fresh_signal():
    signal = valid_signal()
    signal["ts"] = datetime.now(timezone.utc).isoformat()
    return signal


def main():
    bridge = load_bridge()
    with tempfile.TemporaryDirectory(prefix="bill-topstep-bridge-firewall-") as raw:
        tmp = Path(raw)
        bridge.STATE_DIR = tmp / "state"
        bridge.VAULT_DIR = tmp / "vault"
        bridge.VAULT = bridge.VAULT_DIR / "Trading" / "Topstep-100K"
        bridge.ENV_PATH = tmp / "missing.env"
        bridge.SIGNAL_PATH = bridge.STATE_DIR / "master-signal.latest.json"
        bridge.RECENT_PATH = bridge.STATE_DIR / "topstep-demo-submission.latest.json"
        if bridge.current_trading_date(datetime(2026, 5, 29, 23, 30, tzinfo=timezone.utc)).isoformat() != "2026-05-30":
            raise AssertionError("Topstep bridge daily plan date does not use Bill trading timezone")

        write_json(bridge.STATE_DIR / "topstep-100k-monitor.latest.json", {"status": "OK", "hard_blockers": [], "warnings": []})
        write_json(bridge.STATE_DIR / "live-readiness-gate.latest.json", {"readyForDemoExpansion": True, "blockers": []})

        armed_env = {
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "true",
            "RH_TOPSTEP_READ_ONLY": "false",
            "RH_LIVE_EXECUTION_ENABLED": "false",
            "BILL_KILL_SWITCH": "false",
            "RH_KILL_SWITCH": "false",
        }

        with patched_env({
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
            "RH_TOPSTEP_READ_ONLY": "true",
            "RH_LIVE_EXECUTION_ENABLED": "false",
            "BILL_KILL_SWITCH": "false",
            "RH_KILL_SWITCH": "false",
        }):
            ok, reason = bridge.execution_gate(valid_signal())
            if ok:
                raise AssertionError("bridge allowed disabled env and missing daily plan")
            assert_reason(reason, "RH_TOPSTEP_READ_ONLY is true")
            assert_reason(reason, "BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true")
            assert_reason(reason, "daily plan missing or unreadable: " + str(bridge.today_daily_plan_path()))

        with patched_env(armed_env):
            write_daily(bridge.today_daily_plan_path(), "\n".join([
                "No new Bill/Hermes orders approved.",
                "- `BILL_ROUTE_APPROVAL: APPROVED`",
                "BROKER_RECONCILIATION: GREEN",
            ]))
            ok, reason = bridge.execution_gate(valid_signal())
            if ok:
                raise AssertionError("bridge accepted markdown/prose approval token")
            assert_reason(reason, "daily plan explicitly says no new Bill/Hermes orders approved")
            assert_reason(reason, "daily plan lacks BILL_ROUTE_APPROVAL: APPROVED")

        with patched_env(armed_env):
            write_daily(bridge.today_daily_plan_path(), "\n".join([
                "BILL_ROUTE_APPROVAL: APPROVED",
                "BROKER_RECONCILIATION: GREEN",
            ]))
            signal = valid_signal()
            signal.pop("execution_firewall")
            ok, reason = bridge.execution_gate(signal)
            if ok:
                raise AssertionError("bridge accepted signal without master execution firewall")
            assert_reason(reason, "master signal execution_firewall.allowed is not true")

        with patched_env(armed_env):
            ok, reason = bridge.execution_gate(valid_signal())
            if not ok:
                raise AssertionError(f"bridge blocked fully approved temp state: {reason}")

            signal = fresh_signal()
            signal["side"] = "buy"
            ok, reason = bridge.send_signal("fake-token", signal)
            if ok:
                raise AssertionError("bridge accepted invalid side as an order side")
            assert_reason(str(reason), "invalid side: buy")

            signal = fresh_signal()
            signal["contracts"] = "1.5"
            ok, reason = bridge.send_signal("fake-token", signal)
            if ok:
                raise AssertionError("bridge accepted fractional contract size")
            assert_reason(str(reason), "contracts must be a whole number")

        write_json(bridge.STATE_DIR / "topstep-100k-monitor.latest.json", {"status": "OK", "hard_blockers": [], "warnings": ["needs review"]})
        with patched_env(armed_env):
            ok, reason = bridge.execution_gate(valid_signal())
            if ok:
                raise AssertionError("bridge allowed execution with monitor warning")
            assert_reason(reason, "Topstep monitor warnings require reconciliation")

        write_json(bridge.STATE_DIR / "topstep-100k-monitor.latest.json", {"status": "OK", "hard_blockers": [], "warnings": []})
        write_json(bridge.STATE_DIR / "live-readiness-gate.latest.json", {"readyForDemoExpansion": False})
        with patched_env(armed_env):
            ok, reason = bridge.execution_gate(valid_signal())
            if ok:
                raise AssertionError("bridge allowed execution with live-readiness red")
            assert_reason(reason, "live-readiness gate does not allow demo expansion")

        write_json(bridge.STATE_DIR / "live-readiness-gate.latest.json", {
            "readyForDemoExpansion": True,
            "blockers": ["source tree has uncommitted source changes"],
        })
        with patched_env(armed_env):
            ok, reason = bridge.execution_gate(valid_signal())
            if ok:
                raise AssertionError("bridge allowed inconsistent live-readiness artifact")
            assert_reason(reason, "live-readiness gate has blockers despite demo flag")

        with patched_env({}):
            ok, reason = bridge.execution_gate(valid_signal(), dry_run=True)
            if not ok or reason != "dry run":
                raise AssertionError(f"dry-run should bypass submit gates without enabling order path; got {ok}, {reason}")

    print(json.dumps({
        "ok": True,
        "checked": [
            "fail_closed_disabled_env_or_missing_daily",
            "use_bill_trading_timezone_daily_plan",
            "reject_markdown_or_prose_approval_tokens",
            "require_master_execution_firewall_on_signal",
            "allow_only_exact_standalone_controls_with_green_artifacts",
            "reject_invalid_side_before_broker_write",
            "reject_bad_contract_size_before_broker_write",
            "block_topstep_monitor_warnings",
            "block_live_readiness_red",
            "reject_live_readiness_ready_with_blockers",
            "dry_run_gate_returns_without_auth_or_submit",
        ],
        "script": str(BRIDGE_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
