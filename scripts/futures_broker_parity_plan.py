#!/usr/bin/env python3
"""Build a research-only proof plan for current futures broker/data parity.

This does not call Topstep, Databento, TradingView, or any order route. It
reads the existing state artifacts and turns the remaining blockers into an
open-session checklist with safe environment flags.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"

FUTURES_DATA_REQUIREMENTS = STATE / "futures-data-requirements.latest.json"
CURRENT_DATA_PARITY = STATE / "futures-nq-current-data-parity.latest.json"
REALTIME_PREFLIGHT = STATE / "realtime-data-preflight.latest.json"
DATABENTO_SMOKE = STATE / "databento-realtime-smoke.latest.json"
TOPSTEP_MONITOR = STATE / "topstep-100k-monitor.latest.json"

OUT = STATE / "futures-broker-parity-plan.latest.json"


SAFE_ENV = {
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
    "RH_TOPSTEP_READ_ONLY": "true",
    "RH_LIVE_EXECUTION_ENABLED": "false",
}

EASTERN = ZoneInfo("America/New_York")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_daily_plan_path() -> Path:
    return HERMES / "daily" / f"{current_utc_date()}-bill-trading-plan.md"


def default_markdown_path() -> Path:
    return HERMES / f"futures-broker-parity-plan-{current_utc_date()}.md"


def globex_equity_index_session(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    eastern = now.astimezone(EASTERN)
    weekday = eastern.weekday()
    local_t = eastern.time()

    likely_open = True
    reason = "within normal Globex equity-index session"
    if weekday == 5:
        likely_open = False
        reason = "Saturday Globex closure"
    elif weekday == 6 and local_t < time(18, 0):
        likely_open = False
        reason = "Sunday before the usual 18:00 ET Globex open"
    elif weekday == 4 and local_t >= time(17, 0):
        likely_open = False
        reason = "Friday after the usual 17:00 ET Globex close"
    elif weekday in {0, 1, 2, 3, 6} and time(17, 0) <= local_t < time(18, 0):
        likely_open = False
        reason = "daily Globex maintenance break around 17:00-18:00 ET"

    return {
        "market": "CME Globex equity-index futures",
        "timezone": "America/New_York",
        "utcTimestamp": now.astimezone(timezone.utc).isoformat(),
        "easternTimestamp": eastern.isoformat(),
        "likelyOpen": likely_open,
        "reason": reason,
        "holidayCalendarApplied": False,
    }


def next_globex_open(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    session = globex_equity_index_session(now)
    if session["likelyOpen"]:
        open_utc = now.astimezone(timezone.utc)
        reason = "market-likely-open-now"
    else:
        eastern = now.astimezone(EASTERN)
        weekday = eastern.weekday()
        local_t = eastern.time()
        if weekday == 5 or (weekday == 6 and local_t < time(18, 0)):
            days_until_sunday = (6 - weekday) % 7
            open_et = (eastern + timedelta(days=days_until_sunday)).replace(hour=18, minute=0, second=0, microsecond=0)
            reason = "next Sunday 18:00 ET Globex open"
        elif weekday == 4 and local_t >= time(17, 0):
            open_et = (eastern + timedelta(days=2)).replace(hour=18, minute=0, second=0, microsecond=0)
            reason = "next Sunday 18:00 ET Globex open after Friday close"
        elif weekday in {0, 1, 2, 3, 6} and time(17, 0) <= local_t < time(18, 0):
            open_et = eastern.replace(hour=18, minute=0, second=0, microsecond=0)
            reason = "after daily 17:00-18:00 ET maintenance break"
        else:
            open_et = eastern
            reason = "market-likely-open-now"
        open_utc = open_et.astimezone(timezone.utc)

    recommended_start = open_utc + timedelta(minutes=5)
    recommended_end = recommended_start + timedelta(minutes=30)
    return {
        "session": session,
        "nextOpenUtc": open_utc.isoformat(),
        "recommendedProofStartUtc": recommended_start.isoformat(),
        "recommendedProofEndUtc": recommended_end.isoformat(),
        "reason": reason,
        "commandsAreDataOnly": True,
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def extract_blocked_requirement_ids(data: dict[str, Any]) -> list[str]:
    requirements = data.get("requirements") if isinstance(data.get("requirements"), list) else []
    return [
        str(item.get("id"))
        for item in requirements
        if isinstance(item, dict) and item.get("id") and item.get("status") != "pass"
    ]


def topstep_summary(monitor: dict[str, Any]) -> dict[str, Any]:
    recon = monitor.get("broker_reconciliation") if isinstance(monitor.get("broker_reconciliation"), dict) else {}
    return {
        "present": bool(monitor),
        "status": monitor.get("status"),
        "brokerFlat": recon.get("broker_flat"),
        "openPositions": recon.get("open_positions"),
        "fillsToday": recon.get("fills_today"),
        "matchedTrades": recon.get("matched_trades"),
        "reconciliationTs": recon.get("ts"),
        "monitorTs": monitor.get("ts"),
    }


def wrapper_is_safe(preflight: dict[str, Any]) -> bool:
    wrapper = ((preflight.get("runtime") or {}).get("cronWrapper") or {}) if isinstance(preflight.get("runtime"), dict) else {}
    return all(
        wrapper.get(key) is True
        for key in ["usesVenvPython", "forcesFuturesDemoDisabled", "forcesTopstepReadOnly", "forcesLiveExecutionDisabled"]
    )


def safe_commands(preflight: dict[str, Any]) -> dict[str, list[str]]:
    databento = ((preflight.get("dataSources") or {}).get("databentoLive") or {}) if isinstance(preflight.get("dataSources"), dict) else {}
    safe_data_only = databento.get("safeDataOnlyCommand")
    commands = {
        "stateRefresh": [
            "npm run --silent bill:futures-nq-current-data-parity",
            "npm run --silent bill:futures-data-requirements",
            "npm run --silent bill:realtime-data-preflight || true",
        ],
        "openSessionDataOnly": [
            "npm run --silent bill:databento-realtime-smoke -- --timeout-sec 20",
            "npm run --silent bill:data-freshness-gate || true",
        ],
        "readOnlyBrokerReconciliation": [
            "RH_TOPSTEP_READ_ONLY=true BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false python3 /Users/brain/.hermes/scripts/topstep_demo_fill_check.py",
            "npm run --silent bill:obsidian-sync",
        ],
        "postProofRegeneration": [
            "npm run --silent bill:futures-data-requirements",
            "npm run --silent bill:clearance-handoff",
            "npm run --silent bill:obsidian-sync",
        ],
    }
    if isinstance(safe_data_only, str) and safe_data_only:
        commands["openSessionDataOnly"].insert(1, safe_data_only)
    return commands


def build_plan(
    *,
    futures_data_requirements: dict[str, Any],
    current_data_parity: dict[str, Any],
    realtime_preflight: dict[str, Any],
    databento_smoke: dict[str, Any],
    topstep_monitor: dict[str, Any],
    daily_plan_text: str,
    daily_plan_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    blocked_ids = extract_blocked_requirement_ids(futures_data_requirements)
    topstep = topstep_summary(topstep_monitor)
    data_only_ready = bool(databento_smoke.get("readyForExecutionDataProof") and realtime_preflight.get("readyForExecutionData"))
    broker_flat = topstep.get("brokerFlat") is True and topstep.get("openPositions") == 0
    local_parity_ready = current_data_parity.get("decision") == "research-only-current-local-parity-ready"
    route_blocked = "BILL_ROUTE_APPROVAL: BLOCKED" in daily_plan_text
    next_window = next_globex_open(now)

    missing_proofs: list[str] = []
    if "nq-current-local-or-broker-parity" in blocked_ids:
        missing_proofs.append("broker-reconciled-current-nq-bars")
    if "nq-current-session-depth-for-demo" in blocked_ids:
        missing_proofs.append("current-session-depth-from-broker-relevant-source")
    if "futures-execution-grade-realtime" in blocked_ids:
        missing_proofs.append("open-session-execution-grade-realtime-proof")
    if not broker_flat:
        missing_proofs.append("read-only-broker-flat-reconciliation")
    if not wrapper_is_safe(realtime_preflight):
        missing_proofs.append("safe-realtime-wrapper")
    if not route_blocked:
        missing_proofs.append("daily-plan-route-lock-not-confirmed")
    commands = safe_commands(realtime_preflight)
    daily_plan_path = daily_plan_path or default_daily_plan_path()

    return {
        "command": "futures-broker-parity-plan",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "decision": "research-only-futures-broker-parity-not-cleared" if missing_proofs else "research-only-futures-broker-parity-proof-plan-clear",
        "sourceArtifacts": {
            "futuresDataRequirements": str(FUTURES_DATA_REQUIREMENTS),
            "currentDataParity": str(CURRENT_DATA_PARITY),
            "realtimePreflight": str(REALTIME_PREFLIGHT),
            "databentoSmoke": str(DATABENTO_SMOKE),
            "topstepMonitor": str(TOPSTEP_MONITOR),
            "dailyPlan": str(daily_plan_path),
        },
        "safeEnv": dict(SAFE_ENV),
        "current": {
            "blockedRequirementIds": blocked_ids,
            "localCurrentParityReady": local_parity_ready,
            "brokerParityChecked": bool(current_data_parity.get("brokerParityChecked")),
            "realtimePreflightDecision": realtime_preflight.get("decision"),
            "realtimeReadyForExecutionData": bool(realtime_preflight.get("readyForExecutionData")),
            "databentoStatus": databento_smoke.get("status"),
            "databentoReadyForExecutionDataProof": bool(databento_smoke.get("readyForExecutionDataProof")),
            "dataOnlyReady": data_only_ready,
            "topstep": topstep,
            "dailyRouteBlocked": route_blocked,
            "safeWrapper": wrapper_is_safe(realtime_preflight),
        },
        "nextOpenSessionProofWindow": next_window,
        "missingProofs": missing_proofs,
        "validationCommandSets": {
            "parityStateRefresh": commands["stateRefresh"],
            "openSessionDataOnlyProof": commands["openSessionDataOnly"],
            "readOnlyBrokerReconciliation": commands["readOnlyBrokerReconciliation"],
            "postProofRegeneration": commands["postProofRegeneration"],
            "operatorRead": "These commands collect data and read-only reconciliation evidence only. They do not approve demo/live routing.",
        },
        "proofSequence": [
            {
                "step": "refresh-state-with-locks",
                "when": "anytime",
                "goal": "Regenerate current state without changing execution flags.",
                "commands": commands["stateRefresh"],
            },
            {
                "step": "open-session-data-only-smoke",
                "when": (
                    "CME Globex equity-index session open, outside 17:00-18:00 ET maintenance. "
                    f"Next recommended start: {next_window['recommendedProofStartUtc']}"
                ),
                "goal": "Prove NQ/ES Databento live data can produce source=databento_realtime and execution_grade=true.",
                "commands": commands["openSessionDataOnly"],
            },
            {
                "step": "read-only-broker-reconciliation",
                "when": "after data-only smoke, still with route approval blocked",
                "goal": "Confirm Topstep account is flat and orders/fills are reconciled without submitting any order.",
                "commands": commands["readOnlyBrokerReconciliation"],
            },
            {
                "step": "regenerate-clearance-artifacts",
                "when": "after the read-only proofs",
                "goal": "Let futures-data-requirements and clearance handoff decide; do not manually promote.",
                "commands": commands["postProofRegeneration"],
            },
        ],
        "promotionRules": [
            "This plan never approves demo/live routing.",
            "Broker read-only reconciliation is not broker/local OHLCV parity by itself.",
            "Databento smoke must happen while the market is open and must be followed by data-freshness PASS before any execution-data gate can clear.",
            "Closed-market NO_QUOTES_MARKET_CLOSED is not failure of the data vendor; it schedules the next open-session data-only proof.",
            "Futures demo expansion still requires source cleanliness, OOS/walk-forward/cost gates, daily route approval, and deterministic firewall checks.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Futures Broker Parity Plan - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only proof plan for current NQ broker/data parity. This page does not approve Topstep demo or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Missing proofs: `{payload.get('missingProofs')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Ready for demo expansion: `{payload.get('readyForDemoExpansion')}`",
        f"- Next open-session proof window: `{payload.get('nextOpenSessionProofWindow')}`",
        "",
        "## Current",
        "",
        f"- Current: `{payload.get('current')}`",
        "",
        "## Proof Sequence",
        "",
    ]
    for step in payload.get("proofSequence") or []:
        lines.extend([
            f"### {step.get('step')}",
            "",
            f"- When: {step.get('when')}",
            f"- Goal: {step.get('goal')}",
            "- Commands:",
        ])
        for command in step.get("commands") or []:
            lines.append(f"  - `{command}`")
        lines.append("")
    lines.extend(["## Promotion Rules", ""])
    for rule in payload.get("promotionRules") or []:
        lines.append(f"- {rule}")
    validation = payload.get("validationCommandSets") if isinstance(payload.get("validationCommandSets"), dict) else {}
    if validation:
        lines.extend(["", "## Validation Command Sets", ""])
        for key, commands in validation.items():
            if isinstance(commands, list):
                lines.append(f"### `{key}`")
                for command in commands:
                    lines.append(f"- `{command}`")
                lines.append("")
        if validation.get("operatorRead"):
            lines.append(f"- Operator read: {validation.get('operatorRead')}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    daily_plan = default_daily_plan_path()
    payload = build_plan(
        futures_data_requirements=read_json(FUTURES_DATA_REQUIREMENTS),
        current_data_parity=read_json(CURRENT_DATA_PARITY),
        realtime_preflight=read_json(REALTIME_PREFLIGHT),
        databento_smoke=read_json(DATABENTO_SMOKE),
        topstep_monitor=read_json(TOPSTEP_MONITOR),
        daily_plan_text=read_text(daily_plan),
        daily_plan_path=daily_plan,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
