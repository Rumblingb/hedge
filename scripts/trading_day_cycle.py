#!/usr/bin/env python3
"""Deterministic Hermes-owned trading-day cycle for ProjectX testbed-B.

Premarket refreshes calendar/news/account/data proofs and writes daily controls;
market evaluates the one-order ORB demo; postmarket reconciles, journals, and
records futures/options/prediction research shadows. Only the market phase can
reach the guarded demo bridge, and no phase permits live money.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"
STATE = ROOT / ".rumbling-hedge/state"
VAULT = Path.home() / "Documents/memorybrain"
HERMES = VAULT / "Agent-Hermes"
POLICY_PATH = ROOT / "config/testbed-b-demo-challenge.json"
ACCOUNT_ID = 23536817
MANAGED_START = "<!-- TESTBED_B_CHALLENGE_CYCLE_START -->"
MANAGED_END = "<!-- TESTBED_B_CHALLENGE_CYCLE_END -->"


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def parse_ts(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except Exception:
        return None


def safe_env() -> dict[str, str]:
    return {
        **os.environ,
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
        "RH_TOPSTEP_READ_ONLY": "true",
        "RH_LIVE_EXECUTION_ENABLED": "false",
        "BILL_ALLOW_TOPSTEP_BROKER_SESSION_PROOF": "true",
        "RH_TOPSTEP_RECONCILE_ACCOUNT_ID": str(ACCOUNT_ID),
        "RH_TOPSTEP_ACCOUNT_ID": str(ACCOUNT_ID),
        "RH_TOPSTEP_ROUTE_ACCOUNT_ID": str(ACCOUNT_ID),
    }


def run_step(step_id: str, args: list[str], *, timeout: int = 180, required: bool = False) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    try:
        result = subprocess.run(args, cwd=ROOT, env=safe_env(), text=True, capture_output=True, timeout=timeout)
        return {
            "id": step_id,
            "required": required,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "returnCode": result.returncode,
            "durationSeconds": round((datetime.now(timezone.utc) - started).total_seconds(), 3),
            "stdoutTail": result.stdout[-1200:],
            "stderrTail": result.stderr[-1200:],
        }
    except Exception as exc:
        return {
            "id": step_id,
            "required": required,
            "status": "FAIL",
            "returnCode": None,
            "durationSeconds": round((datetime.now(timezone.utc) - started).total_seconds(), 3),
            "error": str(exc),
        }


def lane_state() -> dict[str, Any]:
    lanes = read_json(STATE / "topstep-lanes.latest.json")
    return next((item for item in lanes.get("lanes") or [] if str(item.get("account_id")) == str(ACCOUNT_ID)), {})


def premarket_blockers(steps: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    blockers = [f"required step failed: {step['id']}" for step in steps if step.get("required") and step.get("status") != "PASS"]
    policy = read_json(POLICY_PATH)
    if policy.get("enabled") is not True or policy.get("simulated_only") is not True:
        blockers.append("standing testbed-B simulated policy is not enabled")
    lane = lane_state()
    if lane.get("can_trade") is not True:
        blockers.append("testbed-B is not canTrade")
    if lane.get("is_visible") is not True:
        blockers.append("testbed-B is not visible")
    if lane.get("simulated") is not True:
        blockers.append("testbed-B is not confirmed simulated")
    reconciliation = read_json(STATE / "topstep-broker-reconciliation.latest.json")
    if str(reconciliation.get("account_id")) != str(ACCOUNT_ID) or reconciliation.get("broker_flat") is not True:
        blockers.append("exact testbed-B broker-flat reconciliation is not green")
    red_folder = read_json(STATE / "red-folder-calendar.latest.json")
    if red_folder.get("status") != "PASS":
        blockers.append("red-folder calendar is blocked")
    fomc = read_json(Path.home() / ".rumbling-hedge/state/fomc-gate.latest.json")
    if fomc.get("verdict") != "PASS":
        blockers.append(f"FOMC gate is {fomc.get('verdict', 'missing')}")
    preflight = read_json(STATE / "realtime-data-preflight.latest.json")
    if preflight.get("readyForExecutionData") is not True or preflight.get("blockers"):
        blockers.append("execution-grade realtime preflight is not ready")
    parity = (read_json(STATE / "futures-broker-parity-plan.latest.json").get("current") or {})
    if parity.get("topstepBrokerLocalBarParityPassed") is not True:
        blockers.append("broker/local bar parity is not proven")
    if parity.get("topstepRealtimeReadyForExecutionDataProof") is not True:
        blockers.append("ProjectX realtime proof is not proven")
    context = {"policy": policy, "lane": lane, "reconciliation": reconciliation, "redFolder": red_folder, "fomc": fomc, "realtimePreflight": preflight, "parity": parity}
    return sorted(set(blockers)), context


def replace_managed_block(text: str, block: str) -> str:
    if MANAGED_START in text and MANAGED_END in text:
        before, rest = text.split(MANAGED_START, 1)
        _, after = rest.split(MANAGED_END, 1)
        return before.rstrip() + "\n\n" + block + after
    return text.rstrip() + "\n\n" + block + "\n"


def remove_legacy_canary_block(text: str) -> str:
    legacy = "## Founder-Approved ProjectX Demo Canary"
    following = "## Gate State"
    if legacy in text and following in text:
        before, rest = text.split(legacy, 1)
        _, after = rest.split(following, 1)
        return before.rstrip() + "\n\n" + following + after
    return text


def write_daily_controls(blockers: list[str], context: dict[str, Any]) -> Path:
    stamp = date.today().isoformat()
    path = HERMES / "daily" / f"{stamp}-bill-trading-plan.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text() if path.exists() else f"# Bill Trading Plan - {stamp}\n"
    text = remove_legacy_canary_block(text)
    approved = not blockers
    lane = context.get("lane") or {}
    balance = lane.get("balance")
    nominal_eligible = isinstance(balance, (int, float)) and float(balance) > 48000.0
    lines = [
        MANAGED_START,
        "## Automated Testbed-B Demo Challenge Cycle",
        "",
        "Standing founder approval is constrained to ProjectX simulated testbed-B. Deterministic gates still decide every order.",
        "",
        f"- Cycle decision: `{'APPROVED' if approved else 'BLOCKED'}`",
        f"- Account: `{ACCOUNT_ID}` / `50KTC-V2-DLL-507159-71363980` (simulated only)",
        f"- Latest balance: `${float(balance):,.2f}`" if isinstance(balance, (int, float)) else "- Latest balance: `missing`",
        f"- Nominal pass-eligible 50K MLL check: `{'LIKELY' if nominal_eligible else 'PRACTICE_ONLY_OR_RESET_REQUIRED'}`",
        "- Strategy: locked `orb3m-vt16` entry/stop with founder-approved `1.5R` challenge exit overlay.",
        "- Risk: `$1,000` maximum initial bracket risk; integer sizing must use `$900-$1,000`.",
        "- Gross target: up to `$1,500`; exactly `1.5R` of actual bracket risk.",
        "- Limits: one entry/day, maximum `50 MNQ`, no copy trading, no other account, no live money.",
        "- Window: `09:48-11:30 America/New_York`; high-impact news ±30m and medium-impact news ±15m are blocked.",
        "- A no-signal/no-trade day is valid and must never be replaced by a manufactured trade.",
        "",
    ]
    if blockers:
        lines.extend(["### Blockers", ""] + [f"- {item}" for item in blockers] + [""])
    lines.extend([
        f"BILL_ROUTE_APPROVAL: {'APPROVED' if approved else 'BLOCKED'}",
        f"BROKER_RECONCILIATION: {'GREEN' if approved else 'BLOCKED'}",
        f"BILL_DEMO_CANARY: {'APPROVED' if approved else 'BLOCKED'}",
        f"BILL_TOPSTEP_SINGLE_API_SESSION: {'APPROVED' if approved else 'BLOCKED'}",
        f"BILL_TESTBED_B_ROUTE_APPROVAL: {'APPROVED' if approved else 'BLOCKED'}",
        f"BILL_CHALLENGE_PROFILE: {'APPROVED' if approved else 'BLOCKED'}",
        MANAGED_END,
    ])
    path.write_text(replace_managed_block(text, "\n".join(lines)), encoding="utf-8")
    return path


def write_cycle_state(phase: str, status: str, steps: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    payload = {"command": "trading-day-cycle", "phase": phase, "generatedAt": datetime.now(timezone.utc).isoformat(), "status": status, "accountId": ACCOUNT_ID, "demoOnly": True, "liveMoneyAllowed": False, "steps": steps, **extra}
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"trading-day-cycle.{phase}.latest.json").write_text(json.dumps(payload, indent=2) + "\n")
    (STATE / "trading-day-cycle.latest.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def premarket() -> tuple[int, dict[str, Any]]:
    steps = [
        run_step("red-folder-calendar", [str(PYTHON), "scripts/red_folder_calendar.py"], required=True),
        run_step("fomc-gate", [str(PYTHON), "scripts/fomc_gate.py"], required=True),
        run_step("execution-process-audit", [str(PYTHON), "scripts/verify_no_execution_enabled_processes.py"], required=True),
        run_step("exact-account-reconciliation", [str(PYTHON), str(Path.home() / ".hermes/scripts/topstep_demo_fill_check.py")], required=True),
        run_step("account-lane-proof", [str(PYTHON), "scripts/topstep_lanes_monitor.py"], required=True),
        run_step("broker-bar-archive", [str(PYTHON), "scripts/topstep_readonly_bar_archive.py"], required=True),
        run_step("broker-local-parity", [str(PYTHON), "scripts/topstep_broker_local_bar_parity.py", "--local-csv", str(ROOT / ".rumbling-hedge/research/topstep-readonly-bars/NQ-1m-topstep-readonly.csv")], required=True),
        run_step("projectx-realtime-proof", [str(PYTHON), "scripts/topstep_realtime_proof.py", "--duration-sec", "12", "--include-es", "--write-realtime-quote-state"], timeout=90, required=True),
        run_step("data-freshness", [str(PYTHON), "scripts/data_freshness_gate.py"], required=True),
        run_step("realtime-preflight", [str(PYTHON), "scripts/realtime_data_preflight.py"], required=True),
        run_step("broker-parity-plan", [str(PYTHON), "scripts/futures_broker_parity_plan.py"], required=True),
        run_step("finnhub-context", [str(PYTHON), "scripts/finnhub_news.py", "--compact"]),
        run_step("premarket-brief", ["npm", "run", "--silent", "bill:premarket-brief"]),
        run_step("session-shadow-premarket", [str(PYTHON), "scripts/session_shadow_premarket.py"]),
    ]
    blockers, context = premarket_blockers(steps)
    daily_path = write_daily_controls(blockers, context)
    steps.append(run_step("premarket-risk-brief", [str(PYTHON), "scripts/premarket_risk_brief.py"]))
    steps.append(run_step("obsidian-sync", ["npm", "run", "--silent", "bill:obsidian-sync"], timeout=240))
    status = "READY" if not blockers else "BLOCKED"
    return (0 if not blockers else 2), write_cycle_state("premarket", status, steps, blockers=blockers, dailyPlan=str(daily_path), context=context)


def market() -> tuple[int, dict[str, Any]]:
    calendar = read_json(STATE / "red-folder-calendar.latest.json")
    calendar_ts = parse_ts(calendar.get("generatedAt"))
    steps: list[dict[str, Any]] = []
    if not calendar_ts or (datetime.now(timezone.utc) - calendar_ts).total_seconds() > 3 * 3600:
        steps.append(run_step("red-folder-calendar-refresh", [str(PYTHON), "scripts/red_folder_calendar.py"], required=True))
    step = run_step("testbed-b-challenge-canary", [str(PYTHON), "scripts/nq_orb_testbed_b_canary.py"], timeout=240, required=True)
    steps.append(step)
    status = "PASS" if step.get("status") == "PASS" else "BLOCKED"
    return (0 if status == "PASS" else 2), write_cycle_state("market", status, steps)


def append_postmarket_note(payload: dict[str, Any]) -> Path:
    stamp = date.today().isoformat()
    path = HERMES / "daily" / f"{stamp}-bill-trading-plan.md"
    text = path.read_text() if path.exists() else f"# Bill Trading Plan - {stamp}\n"
    start, end = "<!-- TESTBED_B_POSTMARKET_START -->", "<!-- TESTBED_B_POSTMARKET_END -->"
    failed = [step["id"] for step in payload.get("steps") or [] if step.get("status") != "PASS"]
    block = "\n".join([start, "## Automated Post-Market Review", "", f"- Status: `{payload.get('status')}`", f"- Exact account reconciled: `{ACCOUNT_ID}`", f"- Failed steps: `{failed}`", "- Futures, options, and prediction outputs remain shadow/research-only and cannot override tomorrow's daily gates.", "- Next actions: see `bill-next-research-actions` and the refreshed Bill Control Hub.", end])
    if start in text and end in text:
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before.rstrip() + "\n\n" + block + after
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def postmarket() -> tuple[int, dict[str, Any]]:
    steps = [
        run_step("exact-account-reconciliation", [str(PYTHON), str(Path.home() / ".hermes/scripts/topstep_demo_fill_check.py")], required=True),
        run_step("trade-journal", [str(PYTHON), "scripts/trade_journal.py"], timeout=240, required=True),
        run_step("topstep-daily-learning", [str(PYTHON), "scripts/topstep_daily_learning.py"], timeout=180),
        run_step("session-shadow-postmarket", [str(PYTHON), "scripts/session_shadow_postmarket.py"]),
        run_step("futures-shadow-review", [str(PYTHON), "scripts/futures_nq_research_cycle.py"], timeout=240),
        run_step("options-shadow-review", ["npm", "run", "--silent", "bill:options-1dte-report"], timeout=180),
        run_step("prediction-shadow-review", [str(PYTHON), "scripts/prediction_event_capture_cycle.py"], timeout=240),
        run_step("next-research-actions", [str(PYTHON), "scripts/bill_next_research_actions.py"], timeout=240),
    ]
    failed_required = [step["id"] for step in steps if step.get("required") and step.get("status") != "PASS"]
    status = "PASS" if not failed_required else "BLOCKED"
    payload = write_cycle_state("postmarket", status, steps, blockers=failed_required)
    note = append_postmarket_note(payload)
    steps.append(run_step("obsidian-sync", ["npm", "run", "--silent", "bill:obsidian-sync"], timeout=240))
    return (0 if status == "PASS" else 2), write_cycle_state("postmarket", status, steps, blockers=failed_required, dailyPlan=str(note))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic testbed-B trading-day phase.")
    parser.add_argument("phase", choices=("premarket", "market", "postmarket", "status"))
    args = parser.parse_args()
    lock_path = ROOT / ".rumbling-hedge/run" / f"trading-day-cycle-{args.phase}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "SKIPPED", "reason": f"{args.phase} phase already running"}))
            return 0
        if args.phase == "status":
            print(json.dumps(read_json(STATE / "trading-day-cycle.latest.json"), indent=2))
            return 0
        code, payload = globals()[args.phase]()
        print(json.dumps(payload, indent=2))
        return code


if __name__ == "__main__":
    raise SystemExit(main())
