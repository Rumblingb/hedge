#!/usr/bin/env python3
"""One-order NQ ORB-3m challenge-profile demo for ProjectX testbed-B.

The script refreshes read-only ProjectX evidence, requires the exact numeric
account to be broker-flat, waits for a fresh faithful ORB signal, applies the
founder-approved $1,000 / 1.5R challenge overlay, and delegates the only broker
write to the guarded Topstep demo bridge. It never routes to a live account.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
ACCOUNT_ID = 23536817
ACCOUNT_NAME = "50KTC-V2-DLL-507159-71363980"
CONTRACT_ID = "CON.F.US.MNQ.U26"
SIGNAL_PATH = STATE / f"master-signal.{ACCOUNT_ID}.latest.json"
RECEIPT_PATH = STATE / f"topstep-demo-submission.{ACCOUNT_ID}.latest.json"
COUNT_PATH = STATE / f"testbed-b-canary-count.{ACCOUNT_ID}.json"
ORB_SIGNAL_PATH = STATE / "orb-signal.latest.json"
RED_FOLDER_STATUS = STATE / "red-folder-calendar.latest.json"
FOMC_STATUS = Path.home() / ".rumbling-hedge" / "state" / "fomc-gate.latest.json"
DAILY_PLAN = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes" / "daily" / f"{date.today().isoformat()}-bill-trading-plan.md"
NY = ZoneInfo("America/New_York")
TICK_SIZE = 0.25
TICK_VALUE_MNQ = 0.50
RISK_BUDGET_USD = 1000.0
MIN_RISK_UTILIZATION = 0.90
TARGET_RR = 1.5
TARGET_GOAL_USD = 1500.0
MAX_MICROS_50K = 50


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_ts(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except Exception:
        return None


def machine_control_lines() -> set[str]:
    try:
        return {line.strip() for line in DAILY_PLAN.read_text().splitlines() if line.strip()}
    except Exception:
        return set()


def canary_window_open(now: datetime | None = None) -> bool:
    now = (now or datetime.now(timezone.utc)).astimezone(NY)
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 48 <= minutes <= 11 * 60 + 30


def trades_today() -> int:
    data = read_json(COUNT_PATH)
    return int(data.get("count") or 0) if data.get("date") == date.today().isoformat() else 0


def record_trade() -> None:
    COUNT_PATH.write_text(json.dumps({"date": date.today().isoformat(), "count": trades_today() + 1}, indent=2) + "\n")


def signal_blockers(signal: dict, run_started: datetime, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    blockers: list[str] = []
    sig_ts = parse_ts(signal.get("ts"))
    if not sig_ts or sig_ts < run_started or (now - sig_ts).total_seconds() > 120:
        blockers.append("ORB signal was not generated fresh by this canary run")
    if signal.get("tradable_signal") is not True or signal.get("promoted_for_execution") is not True:
        blockers.append("ORB signal is not promoted/tradable")
    if signal.get("side") not in {"long", "short"}:
        blockers.append("ORB signal side is invalid")
    try:
        entry = float(signal.get("entry"))
        stop = float(signal.get("stop"))
        target = float(signal.get("target"))
        price_now = float(signal.get("price_now"))
        rr = float(signal.get("rr"))
        stop_points = abs(entry - stop)
        if rr < 1.95:
            blockers.append(f"ORB signal RR is below 2R: {rr:.2f}")
        if stop_points <= 0:
            blockers.append("ORB stop distance must be positive")
        if abs(price_now - entry) > 5.0:
            blockers.append(f"breakout moved too far from entry reference: {abs(price_now - entry):.2f} points")
        if signal.get("side") == "long" and not (stop < entry < target):
            blockers.append("long ORB geometry is invalid")
        if signal.get("side") == "short" and not (target < entry < stop):
            blockers.append("short ORB geometry is invalid")
    except (TypeError, ValueError):
        blockers.append("ORB signal price geometry is missing or non-numeric")
    return blockers


def build_challenge_order(signal: dict) -> tuple[dict, list[str]]:
    """Size the locked ORB entry/stop inside the founder's 50K demo profile."""
    blockers: list[str] = []
    try:
        side = str(signal["side"])
        entry = round(float(signal["entry"]) / TICK_SIZE) * TICK_SIZE
        original_stop = float(signal["stop"])
        raw_stop_ticks = int(abs(entry - original_stop) / TICK_SIZE)
        # Even stop ticks permit an exact 1.5R whole-tick target.
        stop_ticks = raw_stop_ticks if raw_stop_ticks % 2 == 0 else raw_stop_ticks - 1
        if stop_ticks < 4:
            return {}, ["challenge stop must be at least 4 MNQ ticks"]
        risk_per_contract = stop_ticks * TICK_VALUE_MNQ
        contracts = math.floor(RISK_BUDGET_USD / risk_per_contract)
        if contracts < 1:
            blockers.append("challenge stop is too wide for one MNQ within the $1,000 risk budget")
        if contracts > MAX_MICROS_50K:
            blockers.append(f"challenge sizing requires {contracts} MNQ, above the 50K cap of {MAX_MICROS_50K}")
        contracts = min(contracts, MAX_MICROS_50K)
        actual_risk = contracts * risk_per_contract
        target_ticks = int(stop_ticks * TARGET_RR)
        actual_target = contracts * target_ticks * TICK_VALUE_MNQ
        if actual_risk < RISK_BUDGET_USD * MIN_RISK_UTILIZATION or actual_risk > RISK_BUDGET_USD:
            blockers.append(
                f"integer MNQ sizing uses ${actual_risk:.2f}; required band is "
                f"${RISK_BUDGET_USD * MIN_RISK_UTILIZATION:.2f}-${RISK_BUDGET_USD:.2f}"
            )
        if abs((actual_target / actual_risk if actual_risk else 0) - TARGET_RR) > 1e-9:
            blockers.append("challenge bracket does not preserve exact 1.5R geometry")
        if actual_target > TARGET_GOAL_USD:
            blockers.append(f"challenge target exceeds ${TARGET_GOAL_USD:.2f}: ${actual_target:.2f}")
        if side == "long":
            stop = entry - stop_ticks * TICK_SIZE
            target = entry + target_ticks * TICK_SIZE
        elif side == "short":
            stop = entry + stop_ticks * TICK_SIZE
            target = entry - target_ticks * TICK_SIZE
        else:
            return {}, blockers + ["challenge side must be long or short"]
        return {
            "side": side,
            "entry": entry,
            "stop": stop,
            "target": target,
            "rr": TARGET_RR,
            "contracts": contracts,
            "stop_ticks": stop_ticks,
            "target_ticks": target_ticks,
            "risk_usd": round(actual_risk, 2),
            "target_usd": round(actual_target, 2),
            "risk_budget_usd": RISK_BUDGET_USD,
            "target_goal_usd": TARGET_GOAL_USD,
        }, blockers
    except (KeyError, TypeError, ValueError) as exc:
        return {}, [f"challenge sizing inputs are invalid: {exc}"]


def run_checked(args: list[str], env: dict[str, str], timeout: int = 120) -> None:
    result = subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout)[-1200:]
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{detail}")


def proof_env() -> dict[str, str]:
    return {
        **os.environ,
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
        "RH_TOPSTEP_READ_ONLY": "true",
        "RH_LIVE_EXECUTION_ENABLED": "false",
        "BILL_ALLOW_TOPSTEP_BROKER_SESSION_PROOF": "true",
        "RH_TOPSTEP_RECONCILE_ACCOUNT_ID": str(ACCOUNT_ID),
    }


def refresh_signal_bars() -> None:
    run_checked(
        [str(ROOT / ".venv/bin/python"), "scripts/topstep_readonly_bar_archive.py"],
        proof_env(),
    )


def refresh_read_only_proofs() -> None:
    env = proof_env()
    python = str(ROOT / ".venv/bin/python")
    run_checked([python, "scripts/verify_no_execution_enabled_processes.py"], env)
    run_checked([python, str(Path.home() / ".hermes/scripts/topstep_demo_fill_check.py")], env)
    run_checked([python, "scripts/topstep_lanes_monitor.py"], env)
    run_checked([
        python, "scripts/topstep_broker_local_bar_parity.py", "--local-csv",
        str(ROOT / ".rumbling-hedge/research/topstep-readonly-bars/NQ-1m-topstep-readonly.csv"),
    ], env)
    run_checked([
        python, "scripts/topstep_realtime_proof.py", "--duration-sec", "12",
        "--include-es", "--write-realtime-quote-state",
    ], env)
    run_checked([python, "scripts/data_freshness_gate.py"], env)
    run_checked([python, "scripts/realtime_data_preflight.py"], env)
    run_checked([python, "scripts/futures_broker_parity_plan.py"], env)


def news_blockers(now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    blockers: list[str] = []
    calendar = read_json(RED_FOLDER_STATUS)
    calendar_ts = parse_ts(calendar.get("generatedAt"))
    if calendar.get("status") != "PASS" or not calendar_ts or (now - calendar_ts).total_seconds() > 12 * 3600:
        blockers.append("red-folder calendar is missing, stale, or blocked")
    for event in calendar.get("todayEvents") or []:
        event_ts = parse_ts(event.get("ts")) if isinstance(event, dict) else None
        if not event_ts:
            continue
        delta_minutes = (now - event_ts).total_seconds() / 60
        impact = str(event.get("impact") or "").lower()
        window = 30 if impact == "high" else 15 if impact == "medium" else 0
        if window and -window <= delta_minutes <= window:
            blockers.append(
                f"{impact}-impact red-folder blackout: {event.get('headline')} at {event_ts.isoformat()}"
            )
    fomc = read_json(FOMC_STATUS)
    fomc_ts = parse_ts(fomc.get("timestamp"))
    if not fomc_ts or (now - fomc_ts).total_seconds() > 24 * 3600:
        blockers.append("FOMC gate is missing or stale")
    elif fomc.get("verdict") != "PASS":
        blockers.append(f"FOMC gate is {fomc.get('verdict')}: {fomc.get('reason')}")
    return blockers


def proof_blockers() -> list[str]:
    blockers: list[str] = []
    reconciliation = read_json(STATE / "topstep-broker-reconciliation.latest.json")
    if str(reconciliation.get("account_id")) != str(ACCOUNT_ID):
        blockers.append("reconciliation belongs to a different account")
    if reconciliation.get("broker_flat") is not True or int(reconciliation.get("open_positions") or 0) != 0:
        blockers.append("testbed-B is not broker-flat")
    if not parse_ts(reconciliation.get("ts")) or (datetime.now(timezone.utc) - parse_ts(reconciliation.get("ts"))).total_seconds() > 300:
        blockers.append("testbed-B reconciliation is stale")

    realtime = read_json(STATE / "realtime-data-preflight.latest.json")
    if realtime.get("readyForExecutionData") is not True or realtime.get("blockers"):
        blockers.append("ProjectX realtime data preflight is not ready")
    parity = (read_json(STATE / "futures-broker-parity-plan.latest.json").get("current") or {})
    if parity.get("topstepBrokerLocalBarParityPassed") is not True:
        blockers.append("ProjectX broker/local bar parity is not proven")
    if parity.get("topstepRealtimeReadyForExecutionDataProof") is not True:
        blockers.append("ProjectX realtime proof is not proven")
    lanes = read_json(STATE / "topstep-lanes.latest.json")
    lane = next((item for item in lanes.get("lanes") or [] if str(item.get("account_id")) == str(ACCOUNT_ID)), {})
    if lane.get("can_trade") is not True:
        blockers.append("testbed-B is not marked canTrade by ProjectX")
    if lane.get("is_visible") is not True:
        blockers.append("testbed-B is not visible in ProjectX")
    if lane.get("simulated") is not True:
        blockers.append("testbed-B is not confirmed simulated by ProjectX")
    blockers.extend(news_blockers())
    return blockers


def main() -> int:
    started = datetime.now(timezone.utc)
    controls = machine_control_lines()
    required = {
        "BILL_ROUTE_APPROVAL: APPROVED",
        "BROKER_RECONCILIATION: GREEN",
        "BILL_DEMO_CANARY: APPROVED",
        "BILL_TOPSTEP_SINGLE_API_SESSION: APPROVED",
        "BILL_TESTBED_B_ROUTE_APPROVAL: APPROVED",
        "BILL_CHALLENGE_PROFILE: APPROVED",
    }
    blockers = sorted(required - controls)
    if blockers:
        print(json.dumps({"status": "BLOCKED", "blockers": [f"daily plan lacks {item}" for item in blockers]}))
        return 2
    if trades_today() >= 1:
        print(json.dumps({"status": "DONE", "reason": "testbed-B canary trade cap already reached"}))
        return 0
    if not canary_window_open(started):
        print(json.dumps({"status": "WAIT", "reason": "NQ ORB canary window is 09:48-11:30 ET"}))
        return 0

    refresh_signal_bars()
    generator = ROOT / "scripts/orb3m_vt16_signal.py"
    generated = subprocess.run([str(ROOT / ".venv/bin/python"), str(generator)], cwd=ROOT, text=True, capture_output=True, timeout=90)
    if generated.returncode != 0:
        print(json.dumps({"status": "BLOCKED", "blockers": ["ORB generator failed", generated.stderr[-800:]]}))
        return 2
    signal = read_json(ORB_SIGNAL_PATH)
    blockers = signal_blockers(signal, started)
    if blockers:
        print(json.dumps({"status": "NO_TRADE", "blockers": blockers, "generator": generated.stdout.strip()}))
        return 0
    order, blockers = build_challenge_order(signal)
    if blockers:
        print(json.dumps({"status": "NO_TRADE", "blockers": blockers, "challenge_order": order}))
        return 0

    refresh_read_only_proofs()
    blockers = proof_blockers()
    if blockers:
        print(json.dumps({"status": "BLOCKED", "blockers": blockers}))
        return 2

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "signal": f"{signal['side']}@orb3m-vt16",
        "strategy": "orb3m-vt16",
        "side": order["side"],
        "entry": order["entry"],
        "stop": order["stop"],
        "target": order["target"],
        "rr": order["rr"],
        "contracts": order["contracts"],
        "route": "topstep_demo",
        "status": "pending_topstep_demo_submission",
        "submitted": None,
        "lane": "testbed-b-canary",
        "account_id": ACCOUNT_ID,
        "challenge_profile": {
            **order,
            "account_size": "50K",
            "instrument": "MNQ",
            "entry_and_stop_source": "locked-orb3m-vt16",
            "exit_overlay": "founder-approved-1.5R",
            "demo_only": True,
        },
        "execution_firewall": {
            "allowed": True,
            "blockers": [],
            "mode": "founder-approved-projectx-demo-canary",
            "approval_id": "founder-testbed-b-challenge-profile-v1",
        },
    }
    SIGNAL_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    route_env = {
        **os.environ,
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "true",
        "RH_TOPSTEP_READ_ONLY": "false",
        "RH_LIVE_EXECUTION_ENABLED": "false",
        "RH_TOPSTEP_DEMO_ONLY": "true",
        "BILL_FUTURES_DEMO_CANARY_ENABLED": "true",
        "BILL_FUTURES_DEMO_APPROVAL_ID": "founder-testbed-b-challenge-profile-v1",
        "BILL_FUTURES_DEMO_MAX_ORDERS_PER_RUN": "1",
        "BILL_CHALLENGE_RISK_USD": str(int(RISK_BUDGET_USD)),
        "BILL_CHALLENGE_TARGET_USD": str(int(TARGET_GOAL_USD)),
        "BILL_CHALLENGE_RR": str(TARGET_RR),
        "RH_MAX_CONTRACTS": str(order["contracts"]),
        "RH_TOPSTEP_RECONCILE_ACCOUNT_ID": str(ACCOUNT_ID),
        "RH_TOPSTEP_ROUTE_ACCOUNT_ID": str(ACCOUNT_ID),
        "RH_TOPSTEP_ROUTE_CONTRACT": CONTRACT_ID,
        "RH_TOPSTEP_ROUTE_SIGNAL_PATH": str(SIGNAL_PATH),
    }
    bridge = Path.home() / ".hermes/scripts/topstep_demo_bridge.py"
    result = subprocess.run([str(ROOT / ".venv/bin/python"), str(bridge)], cwd=ROOT, env=route_env, text=True, capture_output=True, timeout=120)
    receipt = read_json(RECEIPT_PATH)
    submitted = result.returncode == 0 and receipt.get("submitted") is True and receipt.get("account_id_numeric") == ACCOUNT_ID
    if submitted:
        record_trade()
    print(json.dumps({
        "status": "SUBMITTED" if submitted else "BLOCKED",
        "account_id": ACCOUNT_ID,
        "account_name": ACCOUNT_NAME,
        "contract": CONTRACT_ID,
        "signal": payload["signal"],
        "submitted": submitted,
        "receipt": receipt,
        "bridge_stdout": result.stdout[-2000:],
        "bridge_stderr": result.stderr[-1000:],
    }, indent=2))
    return 0 if submitted else 2


if __name__ == "__main__":
    raise SystemExit(main())
