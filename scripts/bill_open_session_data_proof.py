#!/usr/bin/env python3
"""Run or dry-run the Bill/Hermes open-session futures data proof.

This is a data-only helper for the Sunday/Globex proof window. It deliberately
keeps execution flags locked and does not perform broker/order/funding actions.
By default it only prints the plan. Passing --run-data-only runs the market-data
proof commands and regenerates the clearance artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "bill-open-session-data-proof.latest.json"

SAFE_ENV = {
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
    "RH_TOPSTEP_READ_ONLY": "true",
    "RH_LIVE_EXECUTION_ENABLED": "false",
}
DATABENTO_DATA_ENV = {
    "BILL_DATABENTO_REALTIME_ENABLED": "true",
    "BILL_DATABENTO_DATASET": "GLBX.MDP3",
    "BILL_DATABENTO_SCHEMA": "mbp-1",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_markdown_path() -> Path:
    proof_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"bill-open-session-data-proof-{proof_date}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def command_args(script: str, *extra: str) -> list[str]:
    return ["npm", "run", "--silent", script, *extra]


def locked_step_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(SAFE_ENV)
    if extra:
        env.update(extra)
    return env


def format_command(step: dict[str, Any]) -> str:
    env = step.get("env") if isinstance(step.get("env"), dict) else {}
    prefix = " ".join(f"{key}={value}" for key, value in sorted(env.items()))
    command = " ".join(str(part) for part in step["argv"])
    return f"{prefix} {command}".strip()


def proof_steps(timeout_sec: float) -> list[dict[str, Any]]:
    return [
        {
            "id": "refresh-broker-parity-plan-before",
            "kind": "state-refresh",
            "argv": command_args("bill:futures-broker-parity-plan"),
            "env": locked_step_env(),
            "required": True,
        },
        {
            "id": "refresh-current-local-parity",
            "kind": "state-refresh",
            "argv": command_args("bill:futures-nq-current-data-parity"),
            "env": locked_step_env(),
            "required": True,
        },
        {
            "id": "refresh-realtime-preflight",
            "kind": "data-preflight",
            "argv": command_args("bill:realtime-data-preflight"),
            "env": locked_step_env(),
            "required": False,
        },
        {
            "id": "databento-open-session-smoke",
            "kind": "market-data-proof",
            "argv": command_args("bill:databento-realtime-smoke", "--", "--timeout-sec", str(timeout_sec)),
            "env": locked_step_env(),
            "required": True,
        },
        {
            "id": "databento-orderflow-feature-smoke",
            "kind": "market-data-feature-proof",
            "argv": command_args("bill:databento-orderflow-feature-smoke", "--", "--timeout-sec", str(timeout_sec)),
            "env": locked_step_env(),
            "required": True,
        },
        {
            "id": "databento-open-session-bridge-write",
            "kind": "market-data-proof",
            "argv": [".venv/bin/python", "scripts/realtime_data_bridge.py", "--quiet", "--databento-only"],
            "env": locked_step_env(DATABENTO_DATA_ENV),
            "required": False,
        },
        {
            "id": "refresh-data-freshness",
            "kind": "data-preflight",
            "argv": command_args("bill:data-freshness-gate"),
            "env": locked_step_env(),
            "required": False,
        },
        {
            "id": "refresh-data-requirements",
            "kind": "gate-regeneration",
            "argv": command_args("bill:futures-data-requirements"),
            "env": locked_step_env(),
            "required": True,
        },
        {
            "id": "refresh-broker-parity-plan-after",
            "kind": "gate-regeneration",
            "argv": command_args("bill:futures-broker-parity-plan"),
            "env": locked_step_env(),
            "required": True,
        },
        {
            "id": "refresh-clearance-handoff",
            "kind": "gate-regeneration",
            "argv": command_args("bill:clearance-handoff"),
            "env": locked_step_env(),
            "required": True,
        },
        {
            "id": "refresh-goal-completion-audit",
            "kind": "completion-audit",
            "argv": command_args("bill:goal-completion-audit"),
            "env": locked_step_env(),
            "required": True,
        },
        {
            "id": "sync-obsidian",
            "kind": "memory-sync",
            "argv": command_args("bill:obsidian-sync"),
            "env": locked_step_env(),
            "required": True,
        },
    ]


def safe_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(SAFE_ENV)
    return env


def run_step(step: dict[str, Any], *, env: dict[str, str]) -> dict[str, Any]:
    started = now_iso()
    step_env = dict(env)
    if isinstance(step.get("env"), dict):
        step_env.update({str(key): str(value) for key, value in step["env"].items()})
    proc = subprocess.run(
        [str(part) for part in step["argv"]],
        cwd=ROOT,
        env=step_env,
        text=True,
        capture_output=True,
        timeout=180,
    )
    return {
        "id": step["id"],
        "kind": step["kind"],
        "argv": step["argv"],
        "env": step.get("env") if isinstance(step.get("env"), dict) else {},
        "command": format_command(step),
        "required": bool(step.get("required")),
        "startedAt": started,
        "finishedAt": now_iso(),
        "returncode": proc.returncode,
        "passed": proc.returncode == 0 or not step.get("required"),
        "stdoutTail": proc.stdout[-4000:],
        "stderrTail": proc.stderr[-4000:],
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
    }


def summarize_state() -> dict[str, Any]:
    broker_plan = read_json(STATE / "futures-broker-parity-plan.latest.json")
    data_requirements = read_json(STATE / "futures-data-requirements.latest.json")
    realtime_preflight = read_json(STATE / "realtime-data-preflight.latest.json")
    databento_smoke = read_json(STATE / "databento-realtime-smoke.latest.json")
    databento_orderflow = read_json(STATE / "databento-orderflow-feature-smoke.latest.json")
    goal_audit = read_json(STATE / "bill-goal-completion-audit.latest.json")
    handoff = read_json(STATE / "bill-clearance-handoff.latest.json")
    return {
        "brokerParityDecision": broker_plan.get("decision"),
        "missingProofs": broker_plan.get("missingProofs", []),
        "nextOpenSessionProofWindow": broker_plan.get("nextOpenSessionProofWindow", {}),
        "dataRequirementsDecision": data_requirements.get("decision"),
        "dataRequirementsBlockedCount": data_requirements.get("blockedCount"),
        "realtimePreflightDecision": realtime_preflight.get("decision"),
        "readyForExecutionData": realtime_preflight.get("readyForExecutionData"),
        "databentoStatus": databento_smoke.get("status"),
        "databentoReadyForExecutionDataProof": databento_smoke.get("readyForExecutionDataProof"),
        "databentoOrderflowFeatureStatus": databento_orderflow.get("status"),
        "databentoOrderflowCompleteBidAsk": databento_orderflow.get("completeBidAsk"),
        "databentoOrderflowCompleteDepthSize": databento_orderflow.get("completeDepthSize"),
        "databentoOrderflowDomProxyReplacementReady": databento_orderflow.get("domProxyReplacementReady"),
        "handoffDecision": handoff.get("decision"),
        "goalDecision": goal_audit.get("decision"),
        "goalBlockedIds": goal_audit.get("blockedIds", []),
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    steps = proof_steps(args.timeout_sec)
    mode = "run-data-only" if args.run_data_only else "dry-run"
    executed: list[dict[str, Any]] = []
    env = safe_env()
    if args.run_data_only:
        for step in steps:
            executed.append(run_step(step, env=env))
    failed = [step for step in executed if not step.get("passed")]
    state_summary = summarize_state()
    execution_grade_data_proof_passed = bool(
        state_summary.get("readyForExecutionData") is True
        and state_summary.get("databentoReadyForExecutionDataProof") is True
    )
    next_window = (
        state_summary.get("nextOpenSessionProofWindow")
        if isinstance(state_summary.get("nextOpenSessionProofWindow"), dict)
        else {}
    )
    planned_commands = [format_command(step) for step in steps]
    top_level_risks = [
        "execution-grade data proof is not yet passed",
        "allCommandsPassed does not imply route approval",
        "broker read-only reconciliation is intentionally separate from this data-only runner",
    ]
    if state_summary.get("databentoStatus") == "NO_QUOTES_MARKET_CLOSED":
        top_level_risks.append("Databento smoke ran while CME Globex was closed; use the next open-session proof window.")
    if state_summary.get("databentoOrderflowDomProxyReplacementReady") is not True:
        top_level_risks.append("Databento order-flow feature smoke has not proved depth/imbalance features for DOM-proxy replacement.")
    return {
        "command": "bill-open-session-data-proof",
        "generatedAt": now_iso(),
        "decision": "execution-grade-data-proof-passed" if execution_grade_data_proof_passed else "data-only-proof-visible-execution-locked",
        "mode": mode,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "safeEnv": dict(SAFE_ENV),
        "brokerReadOnlyStepIncluded": False,
        "brokerReadOnlyStepSkippedReason": "This runner proves execution-grade market data only; broker read-only reconciliation stays separate.",
        "nextOpenUtc": next_window.get("nextOpenUtc"),
        "recommendedProofStartUtc": next_window.get("recommendedProofStartUtc"),
        "recommendedProofEndUtc": next_window.get("recommendedProofEndUtc"),
        "commands": planned_commands,
        "risks": top_level_risks,
        "plannedStepIds": [step["id"] for step in steps],
        "plannedSteps": [
            {
                "id": step["id"],
                "kind": step["kind"],
                "argv": step["argv"],
                "env": step.get("env") if isinstance(step.get("env"), dict) else {},
                "command": format_command(step),
                "required": step["required"],
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
            }
            for step in steps
        ],
        "executedSteps": executed,
        "allCommandsPassed": not failed,
        "failedStepIds": [step["id"] for step in failed],
        "executionGradeDataProofPassed": execution_grade_data_proof_passed,
        "stateSummary": state_summary,
        "hardRules": [
            "This runner never submits orders, changes route approval, funds accounts, or enables demo/live execution.",
            "allCommandsPassed means commands returned successfully; executionGradeDataProofPassed is the data-proof flag.",
            "A successful Databento smoke is not strategy approval.",
            "Goal completion still depends on the goal-completion audit having zero blockers.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or datetime.now(timezone.utc).date().isoformat())[:10]
    lines = [
        f"# Bill Open-Session Data Proof - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only market-data proof runner. This does not approve orders, Topstep demo, live trading, funding, or broker writes.",
        "",
        "## Automation Contract",
        "",
        "- `bill-open-session-data-proof` is the reusable weekly Codex cron for this proof.",
        "- It should run during the open-session proof window with execution locks set: `BILL_ENABLE_FUTURES_DEMO_EXECUTION=false`, `RH_TOPSTEP_READ_ONLY=true`, and `RH_LIVE_EXECUTION_ENABLED=false`.",
        "- It must collect evidence only: Databento realtime smoke, Databento order-flow feature smoke, data freshness, futures requirements, broker/current parity plan, goal audit, and Obsidian sync.",
        "- It must not submit orders, route signals, move funds, enable demo/live execution, or mark the goal complete while blockers remain.",
        "",
        "## Summary",
        "",
        f"- Mode: `{payload.get('mode')}`",
        f"- All commands passed: `{payload.get('allCommandsPassed')}`",
        f"- Execution-grade data proof passed: `{payload.get('executionGradeDataProofPassed')}`",
        f"- Failed step ids: `{payload.get('failedStepIds')}`",
        f"- Safe env: `{payload.get('safeEnv')}`",
        f"- State summary: `{payload.get('stateSummary')}`",
        "",
        "## Planned Steps",
        "",
    ]
    for step in payload.get("plannedSteps") or []:
        lines.append(f"- `{step.get('id')}`: `{step.get('command') or ' '.join(step.get('argv') or [])}`")
    if payload.get("executedSteps"):
        lines.extend(["", "## Executed Steps", ""])
        for step in payload.get("executedSteps") or []:
            lines.append(f"- `{step.get('id')}` returncode `{step.get('returncode')}` passed `{step.get('passed')}`")
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run/dry-run the Bill open-session futures market-data proof.")
    parser.add_argument("--run-data-only", action="store_true", help="Run the data-only proof commands. Default is dry-run.")
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = build_payload(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown) if args.markdown else default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["allCommandsPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
