#!/usr/bin/env python3
"""Verify legacy 60m LucidFlex bridge firewall invariants without webhooks."""

import importlib.util
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "scripts" / "60m_exec_bridge.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("bridge_60m_under_test", BRIDGE_PATH)
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def assert_blocker(decision, expected):
    if expected not in decision["blockers"]:
        raise AssertionError(f"expected blocker {expected!r}; got {decision['blockers']}")


def main():
    with tempfile.TemporaryDirectory(prefix="bill-60m-firewall-") as raw:
        tmp = Path(raw)
        fake_env = tmp / "Library/Application Support/AgentPay/bill/bill.env"
        fake_env.parent.mkdir(parents=True, exist_ok=True)
        fake_env.write_text("\n".join([
            "BILL_ENABLE_LUCIDFLEX_EXECUTION=true",
            "BILL_LUCIDFLEX_LEGACY_PICKMYTRADE_ENABLED=true",
            "RH_LIVE_EXECUTION_ENABLED=true",
            "BILL_PICKMYTRADE_WEBHOOKS_JSON=[]",
        ]), encoding="utf-8")

        with patched_env({
            "HOME": str(tmp),
            "BILL_ENABLE_LUCIDFLEX_EXECUTION": "false",
            "BILL_LUCIDFLEX_LEGACY_PICKMYTRADE_ENABLED": "false",
            "RH_LIVE_EXECUTION_ENABLED": "false",
        }):
            bridge = load_bridge()
            if os.environ.get("BILL_ENABLE_LUCIDFLEX_EXECUTION") != "false":
                raise AssertionError("60m bridge allowed bill.env to override process execution disable flag")
            if os.environ.get("BILL_LUCIDFLEX_LEGACY_PICKMYTRADE_ENABLED") != "false":
                raise AssertionError("60m bridge allowed bill.env to override legacy route disable flag")
            if os.environ.get("RH_LIVE_EXECUTION_ENABLED") != "false":
                raise AssertionError("60m bridge allowed bill.env to override live execution disable flag")

        bridge.STATE_DIR = tmp / "state"
        bridge.VAULT_DIR = tmp / "vault"
        if bridge.current_trading_date(datetime(2026, 5, 29, 23, 30, tzinfo=timezone.utc)).isoformat() != "2026-05-30":
            raise AssertionError("60m bridge daily plan date does not use Bill trading timezone")
        if bridge.sma([{"close": 10.0}, {"close": 14.0}], 2) != 12.0:
            raise AssertionError("60m bridge SMA must read dict-based bars loaded from CSV")
        write_json(bridge.STATE_DIR / "topstep-100k-monitor.latest.json", {"status": "OK", "hard_blockers": [], "warnings": []})
        write_json(bridge.STATE_DIR / "live-readiness-gate.latest.json", {"readyForDemoExpansion": True, "blockers": []})

        armed_env = {
            "BILL_ENABLE_LUCIDFLEX_EXECUTION": "true",
            "BILL_LUCIDFLEX_LEGACY_PICKMYTRADE_ENABLED": "true",
            "RH_LIVE_EXECUTION_ENABLED": "false",
        }

        with patched_env({
            "BILL_ENABLE_LUCIDFLEX_EXECUTION": "false",
            "BILL_LUCIDFLEX_LEGACY_PICKMYTRADE_ENABLED": "false",
            "RH_LIVE_EXECUTION_ENABLED": "false",
        }):
            write_daily(bridge.today_daily_plan_path(), "")
            decision = bridge.execution_firewall_decision()
            if decision["allowed"]:
                raise AssertionError("60m bridge allowed execution with disabled env and missing daily plan")
            assert_blocker(decision, "BILL_ENABLE_LUCIDFLEX_EXECUTION is not true")
            assert_blocker(decision, "BILL_LUCIDFLEX_LEGACY_PICKMYTRADE_ENABLED is not true")
            assert_blocker(decision, "daily plan missing or unreadable: " + str(bridge.today_daily_plan_path()))

        with patched_env(armed_env):
            write_daily(bridge.today_daily_plan_path(), "\n".join([
                "No new Bill/Hermes orders approved.",
                "- `BILL_ROUTE_APPROVAL: APPROVED`",
                "BROKER_RECONCILIATION: GREEN",
            ]))
            decision = bridge.execution_firewall_decision()
            if decision["allowed"]:
                raise AssertionError("60m bridge accepted markdown/prose route approval")
            assert_blocker(decision, "daily plan explicitly says no new Bill/Hermes orders approved")
            assert_blocker(decision, "daily plan lacks BILL_ROUTE_APPROVAL: APPROVED")

        with patched_env(armed_env):
            write_daily(bridge.today_daily_plan_path(), "\n".join([
                "BILL_ROUTE_APPROVAL: APPROVED",
                "BROKER_RECONCILIATION: GREEN",
            ]))
            decision = bridge.execution_firewall_decision()
            if not decision["allowed"]:
                raise AssertionError(f"60m bridge blocked fully approved temp state: {decision['blockers']}")

        write_json(bridge.STATE_DIR / "live-readiness-gate.latest.json", {"readyForDemoExpansion": False})
        with patched_env(armed_env):
            decision = bridge.execution_firewall_decision()
            if decision["allowed"]:
                raise AssertionError("60m bridge allowed execution with live-readiness red")
            assert_blocker(decision, "live-readiness gate does not allow demo expansion")

        write_json(bridge.STATE_DIR / "live-readiness-gate.latest.json", {
            "readyForDemoExpansion": True,
            "blockers": ["source tree has uncommitted source changes"],
        })
        with patched_env(armed_env):
            decision = bridge.execution_firewall_decision()
            if decision["allowed"]:
                raise AssertionError("60m bridge allowed inconsistent live-readiness artifact")
            if not any("live-readiness gate has blockers despite demo flag" in item for item in decision["blockers"]):
                raise AssertionError(f"expected live-readiness consistency blocker; got {decision['blockers']}")

    print(json.dumps({
        "ok": True,
        "checked": [
            "fail_closed_disabled_env_or_missing_daily",
            "bill_env_cannot_arm_execution_control_flags",
            "use_bill_trading_timezone_daily_plan",
            "sma_uses_loaded_dict_bars",
            "reject_markdown_or_prose_approval_tokens",
            "allow_only_exact_standalone_controls_with_green_artifacts",
            "block_live_readiness_red",
            "reject_live_readiness_ready_with_blockers",
        ],
        "script": str(BRIDGE_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
