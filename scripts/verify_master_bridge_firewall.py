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
    bridge = load_master_bridge()
    with tempfile.TemporaryDirectory(prefix="bill-firewall-") as raw:
        tmp = Path(raw)
        state = tmp / "state"
        vault = tmp / "vault"
        bridge.CANONICAL_STATE_DIR = state
        bridge.LEGACY_STATE_DIR = tmp / "legacy-state"
        bridge.VAULT_DIR = vault
        if bridge.current_trading_date(datetime(2026, 5, 29, 23, 30, tzinfo=timezone.utc)).isoformat() != "2026-05-30":
            raise AssertionError("master bridge daily plan date does not use Bill trading timezone")
        if not bridge.is_fomc_day(datetime(2026, 5, 18, 23, 30, tzinfo=timezone.utc)):
            raise AssertionError("master bridge FOMC day check does not use Bill trading timezone")
        if bridge.ny_minutes(datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)) != 570:
            raise AssertionError("master bridge NY session clock does not handle EST")

        green_monitor = {"status": "OK", "hard_blockers": [], "warnings": []}
        green_live_gate = {"readyForDemoExpansion": True}
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
        }):
            write_daily(bridge.today_daily_plan_path(), "")
            decision = bridge.execution_firewall_decision()
            if decision["allowed"]:
                raise AssertionError("firewall allowed execution with missing daily plan and disabled env")
            assert_blocker(decision, "daily plan missing or unreadable: " + str(bridge.today_daily_plan_path()))
            assert_blocker(decision, "BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true")
            assert_blocker(decision, "RH_TOPSTEP_READ_ONLY is true")

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

    print(json.dumps({
        "ok": True,
        "checked": [
            "fail_closed_missing_daily_or_disabled_env",
            "use_bill_trading_timezone_daily_plan",
            "reject_markdown_or_prose_approval_tokens",
            "allow_only_exact_standalone_controls_with_green_artifacts",
            "block_topstep_monitor_warnings",
        ],
        "script": str(MASTER_BRIDGE_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
