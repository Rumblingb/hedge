#!/usr/bin/env python3
"""Verify master_bridge execution firewall invariants without touching live state."""

import importlib.util
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER_BRIDGE_PATH = ROOT / "scripts" / "master_bridge.py"


def load_master_bridge():
    spec = importlib.util.spec_from_file_location("master_bridge_under_test", MASTER_BRIDGE_PATH)
    if spec is None or spec.loader is None:
      raise RuntimeError(f"could not load {MASTER_BRIDGE_PATH}")
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


def assert_blocker(decision, expected):
    if expected not in decision["blockers"]:
        raise AssertionError(f"expected blocker {expected!r}; got {decision['blockers']}")


def main():
    source = MASTER_BRIDGE_PATH.read_text()
    forbidden = [
        'os.environ["BILL_ENABLE_FUTURES_DEMO_EXECUTION"] = "true"',
        'os.environ["RH_TOPSTEP_READ_ONLY"] = "false"',
        'readyForDemoExpansion"] = True',
        "demo_override",
    ]
    for needle in forbidden:
        if needle in source:
            raise AssertionError(f"master bridge contains forbidden auto-relax path: {needle}")

    bridge = load_master_bridge()
    with tempfile.TemporaryDirectory(prefix="bill-firewall-") as raw:
        tmp = Path(raw)
        state = tmp / "state"
        vault = tmp / "vault"
        fake_env = tmp / "bill.env"
        fake_env.write_text("\n".join([
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=true",
            "RH_TOPSTEP_READ_ONLY=false",
            "RH_LIVE_EXECUTION_ENABLED=true",
            "RH_TOPSTEP_DEMO_ONLY=false",
            "BILL_PICKMYTRADE_ENABLED=true",
            "BILL_SIGNAL_ROUTER_ENABLED=true",
            "RH_TOPSTEP_API_KEY=fake-key",
        ]), encoding="utf-8")
        bridge.CANONICAL_STATE_DIR = state
        bridge.LEGACY_STATE_DIR = tmp / "legacy-state"
        bridge.VAULT_DIR = vault
        bridge.BILL_ENV = fake_env
        with patched_env({
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
            "RH_TOPSTEP_READ_ONLY": "true",
            "RH_LIVE_EXECUTION_ENABLED": "false",
            "RH_TOPSTEP_DEMO_ONLY": "true",
            "BILL_PICKMYTRADE_ENABLED": "false",
            "BILL_SIGNAL_ROUTER_ENABLED": "false",
            "RH_TOPSTEP_API_KEY": None,
        }):
            bridge.load_env()
            if os.environ.get("BILL_ENABLE_FUTURES_DEMO_EXECUTION") != "false":
                raise AssertionError("master bridge allowed bill.env to override futures demo execution flag")
            if os.environ.get("RH_TOPSTEP_READ_ONLY") != "true":
                raise AssertionError("master bridge allowed bill.env to override Topstep read-only flag")
            if os.environ.get("RH_LIVE_EXECUTION_ENABLED") != "false":
                raise AssertionError("master bridge allowed bill.env to override live execution flag")
            if os.environ.get("RH_TOPSTEP_DEMO_ONLY") != "true":
                raise AssertionError("master bridge allowed bill.env to override demo-only flag")
            if os.environ.get("RH_TOPSTEP_API_KEY") != "fake-key":
                raise AssertionError("master bridge did not load non-control credentials from bill.env")

        if bridge.current_trading_date(datetime(2026, 5, 29, 23, 30, tzinfo=timezone.utc)).isoformat() != "2026-05-30":
            raise AssertionError("master bridge daily plan date does not use Bill trading timezone")
        if not bridge.is_fomc_day(datetime(2026, 5, 18, 23, 30, tzinfo=timezone.utc)):
            raise AssertionError("master bridge FOMC day check does not use Bill trading timezone")
        if bridge.ny_minutes(datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)) != 570:
            raise AssertionError("master bridge NY session clock does not handle EST")

        green_monitor = {"status": "OK", "hard_blockers": [], "warnings": []}
        green_live_gate = {"readyForDemoExpansion": True, "blockers": []}
        write_json(state / "topstep-100k-monitor.latest.json", green_monitor)
        write_json(state / "live-readiness-gate.latest.json", green_live_gate)

        armed_env = {
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "true",
            "RH_TOPSTEP_READ_ONLY": "false",
            "RH_LIVE_EXECUTION_ENABLED": "false",
            "RH_TOPSTEP_DEMO_ONLY": "true",
        }

        with patched_env({
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
            "RH_TOPSTEP_READ_ONLY": "true",
            "RH_LIVE_EXECUTION_ENABLED": "false",
            "RH_TOPSTEP_DEMO_ONLY": "true",
            "BILL_PICKMYTRADE_WEBHOOKS_JSON": json.dumps([{
                "url": "https://example.invalid/webhook",
                "token": "test-token",
            }]),
        }):
            write_daily(bridge.today_daily_plan_path(), "")
            decision = bridge.execution_firewall_decision()
            if decision["allowed"]:
                raise AssertionError("firewall allowed execution with missing daily plan and disabled env")
            assert_blocker(decision, "daily plan missing or unreadable: " + str(bridge.today_daily_plan_path()))
            assert_blocker(decision, "BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true")
            assert_blocker(decision, "RH_TOPSTEP_READ_ONLY is true")
            if bridge.send_signal({
                "strategy": "firewall-test",
                "side": "long",
                "entry": 100.0,
                "stop": 99.0,
                "target": 102.0,
                "atr": 1.0,
            }, 1):
                raise AssertionError("legacy PickMyTrade helper bypassed the master execution firewall")

        with patched_env(armed_env):
            write_daily(bridge.today_daily_plan_path(), "\n".join([
                "No new Bill/Hermes orders approved.",
                "- `BILL_ROUTE_APPROVAL: APPROVED`",
                "BROKER_RECONCILIATION: GREEN",
            ]))
            decision = bridge.execution_firewall_decision()
            if decision["allowed"]:
                raise AssertionError("firewall accepted markdown/prose approval token")
            assert_blocker(decision, "daily plan explicitly says no new Bill/Hermes orders approved")
            assert_blocker(decision, "daily plan lacks BILL_ROUTE_APPROVAL: APPROVED")

        with patched_env(armed_env):
            write_daily(bridge.today_daily_plan_path(), "\n".join([
                "BILL_ROUTE_APPROVAL: APPROVED",
                "BROKER_RECONCILIATION: GREEN",
            ]))
            decision = bridge.execution_firewall_decision()
            if not decision["allowed"]:
                raise AssertionError(f"firewall blocked fully approved temp state: {decision['blockers']}")

        write_json(state / "topstep-100k-monitor.latest.json", {"status": "OK", "hard_blockers": [], "warnings": ["needs review"]})
        with patched_env(armed_env):
            decision = bridge.execution_firewall_decision()
            if decision["allowed"]:
                raise AssertionError("firewall allowed execution with monitor warning")
            if not any("Topstep monitor warnings require reconciliation" in item for item in decision["blockers"]):
                raise AssertionError(f"expected monitor warning blocker; got {decision['blockers']}")

        write_json(state / "topstep-100k-monitor.latest.json", {"status": "OK", "hard_blockers": [], "warnings": []})
        write_json(state / "live-readiness-gate.latest.json", {
            "readyForDemoExpansion": True,
            "blockers": ["source tree has uncommitted source changes"],
        })
        with patched_env(armed_env):
            decision = bridge.execution_firewall_decision()
            if decision["allowed"]:
                raise AssertionError("firewall allowed inconsistent live-readiness artifact")
            if not any("live-readiness gate has blockers despite demo flag" in item for item in decision["blockers"]):
                raise AssertionError(f"expected live-readiness consistency blocker; got {decision['blockers']}")

    print(json.dumps({
        "ok": True,
        "checked": [
            "fail_closed_missing_daily_or_disabled_env",
            "bill_env_cannot_arm_execution_control_flags",
            "use_bill_trading_timezone_daily_plan",
            "reject_markdown_or_prose_approval_tokens",
            "reject_bridge_auto_relax_or_live_gate_mutation",
            "legacy_pickmytrade_helper_has_own_firewall",
            "reject_live_readiness_ready_with_blockers",
            "allow_only_exact_standalone_controls_with_green_artifacts",
            "block_topstep_monitor_warnings",
        ],
        "script": str(MASTER_BRIDGE_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
