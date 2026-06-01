#!/usr/bin/env python3
"""Run safe Bill/Hermes clearance evidence commands and persist the result.

This is a control-plane verifier, not a trading gate. It runs local tests and
firewall checks, records their outputs, and never touches broker APIs, funds, or
order routes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE / "bill-clearance-evidence.latest.json"
DEFAULT_MARKDOWN = STATE / "bill-clearance-evidence.latest.md"
LOCKED_ENV_FLAGS = {
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
    "RH_TOPSTEP_READ_ONLY": "true",
    "RH_LIVE_EXECUTION_ENABLED": "false",
}


@dataclass(frozen=True)
class CommandSpec:
    id: str
    lane: str
    command: list[str]
    timeoutSec: int
    expectedReturnCodes: tuple[int, ...] = (0,)
    notes: str = ""


def default_commands(include_slow_tests: bool = True) -> list[CommandSpec]:
    commands = [
        CommandSpec(
            id="typecheck",
            lane="governance-risk",
            command=["npm", "run", "--silent", "typecheck"],
            timeoutSec=120,
            notes="Governance lane TypeScript compile check.",
        ),
    ]
    if include_slow_tests:
        commands.append(CommandSpec(
            id="test",
            lane="governance-risk",
            command=["npm", "run", "--silent", "test"],
            timeoutSec=180,
            notes="Full local Vitest suite.",
        ))
    commands.extend([
        CommandSpec(
            id="focused-bill-control-python-tests",
            lane="governance-risk",
            command=[
                ".venv/bin/python",
                "-m",
                "unittest",
                "tests.test_bill_open_session_data_proof",
                "tests.test_bill_source_hygiene_plan",
                "tests.test_bill_source_packet_review",
                "tests.test_bill_next_research_actions",
                "tests.test_bill_goal_completion_audit",
                "tests.test_codex_automation_audit",
                "tests.test_bill_clearance_evidence",
                "-v",
            ],
            timeoutSec=90,
            notes="Focused control-plane tests for data proof, source hygiene, next actions, and goal audit.",
        ),
        CommandSpec(
            id="verify-master-bridge-firewall",
            lane="execution-live",
            command=["npm", "run", "--silent", "bill:verify-master-bridge-firewall"],
            timeoutSec=60,
        ),
        CommandSpec(
            id="verify-60m-bridge-firewall",
            lane="execution-live",
            command=["npm", "run", "--silent", "bill:verify-60m-bridge-firewall"],
            timeoutSec=60,
        ),
        CommandSpec(
            id="verify-topstep-demo-bridge-firewall",
            lane="execution-live",
            command=["npm", "run", "--silent", "bill:verify-topstep-demo-bridge-firewall"],
            timeoutSec=60,
        ),
        CommandSpec(
            id="verify-signal-router-firewall",
            lane="execution-live",
            command=["npm", "run", "--silent", "bill:verify-signal-router-firewall"],
            timeoutSec=60,
        ),
        CommandSpec(
            id="verify-prediction-funding-firewall",
            lane="execution-live",
            command=["npm", "run", "--silent", "bill:verify-prediction-funding-firewall"],
            timeoutSec=60,
        ),
        CommandSpec(
            id="verify-execution-quarantine",
            lane="execution-live",
            command=["npm", "run", "--silent", "bill:verify-execution-quarantine"],
            timeoutSec=60,
            notes="Source/runtime quarantine proof for manual execution-adjacent files.",
        ),
        CommandSpec(
            id="source-intake-manifest",
            lane="source-hygiene",
            command=["npm", "run", "--silent", "bill:source-intake-manifest"],
            timeoutSec=60,
            notes="Refreshes visible source-intake classes without cleanup/staging.",
        ),
        CommandSpec(
            id="source-hygiene-plan",
            lane="source-hygiene",
            command=["npm", "run", "--silent", "bill:source-hygiene-plan"],
            timeoutSec=60,
            notes="Refreshes source-hygiene blockers, bundle counts, and reduction plan.",
        ),
        CommandSpec(
            id="source-packet-review",
            lane="source-hygiene",
            command=["npm", "run", "--silent", "bill:source-packet-review"],
            timeoutSec=60,
            notes="Reviews futures and prediction source-hygiene packets without staging or routing.",
        ),
        CommandSpec(
            id="stale-strategy-claim-guard",
            lane="source-hygiene",
            command=["npm", "run", "--silent", "bill:stale-strategy-claim-guard"],
            timeoutSec=60,
            notes="Fails stale trade-now/paper-now research claims unless they are explicitly superseded or blocked nearby.",
        ),
        CommandSpec(
            id="open-session-data-proof-data-only",
            lane="data",
            command=[
                "npm",
                "run",
                "--silent",
                "bill:open-session-data-proof",
                "--",
                "--run-data-only",
            ],
            timeoutSec=120,
            notes="Data-only proof runner; must not submit orders or call broker write paths.",
        ),
        CommandSpec(
            id="next-research-actions",
            lane="control-plane",
            command=["npm", "run", "--silent", "bill:next-research-actions"],
            timeoutSec=60,
            notes="Refreshes the locked research/action queue for futures and prediction-market blockers.",
        ),
        CommandSpec(
            id="codex-automation-audit",
            lane="control-plane",
            command=["npm", "run", "--silent", "bill:codex-automation-audit"],
            timeoutSec=60,
            notes="Verifies Codex app automations are visible, locked, storage-bounded, and non-duplicative.",
        ),
        CommandSpec(
            id="goal-completion-audit",
            lane="control-plane",
            command=["npm", "run", "--silent", "bill:goal-completion-audit"],
            timeoutSec=60,
            notes="Verifies that unresolved blockers keep the goal and execution gates locked.",
        ),
        CommandSpec(
            id="live-readiness-gate",
            lane="control-plane",
            command=["npm", "run", "--silent", "bill:live-readiness-gate"],
            timeoutSec=90,
            expectedReturnCodes=(0, 2),
            notes="Expected to execute successfully while still reporting readiness blockers.",
        ),
    ])
    return commands


def tail_text(value: str, max_chars: int = 5000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def run_command(spec: CommandSpec) -> dict[str, Any]:
    started = time.monotonic()
    env = {**os.environ, **LOCKED_ENV_FLAGS}
    try:
        proc = subprocess.run(
            spec.command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=spec.timeoutSec,
        )
        duration = round(time.monotonic() - started, 3)
        passed = proc.returncode in spec.expectedReturnCodes
        return {
            **asdict(spec),
            "commandText": " ".join(spec.command),
            "returncode": proc.returncode,
            "durationSec": duration,
            "passed": passed,
            "stdoutTail": tail_text(proc.stdout),
            "stderrTail": tail_text(proc.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - started, 3)
        return {
            **asdict(spec),
            "commandText": " ".join(spec.command),
            "returncode": None,
            "durationSec": duration,
            "passed": False,
            "timeout": True,
            "stdoutTail": tail_text((exc.stdout or "") if isinstance(exc.stdout, str) else ""),
            "stderrTail": tail_text((exc.stderr or "") if isinstance(exc.stderr, str) else ""),
        }


def summarize_live_readiness(path: Path = STATE / "live-readiness-gate.latest.json") -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {"path": str(path), "present": False}
    return {
        "path": str(path),
        "present": True,
        "readyForLive": data.get("readyForLive"),
        "readyForDemoExpansion": data.get("readyForDemoExpansion"),
        "blockers": data.get("blockers", []),
        "warnings": data.get("warnings", []),
    }


def build_report(include_slow_tests: bool = True) -> dict[str, Any]:
    results = [run_command(spec) for spec in default_commands(include_slow_tests)]
    failed = [item for item in results if item.get("passed") is not True]
    return {
        "command": "bill-clearance-evidence",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "envFlags": LOCKED_ENV_FLAGS,
        "status": "PASS" if not failed else "BLOCKED",
        "allCommandsPassed": not failed,
        "failedCommandIds": [item["id"] for item in failed],
        "results": results,
        "liveReadiness": summarize_live_readiness(),
        "hardRules": [
            "Passing clearance evidence does not approve trading.",
            "Live/demo remains blocked until Obsidian route approval, broker reconciliation, realtime data, source cleanliness, and strategy gates pass.",
            "This verifier must not call broker, exchange, wallet, or order-submit APIs.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Bill/Hermes Clearance Evidence",
        "",
        f"Generated: `{report['generatedAt']}`",
        f"Status: `{report['status']}`",
        f"Ready for execution: `{report['readyForExecution']}`",
        "",
        "## Commands",
        "",
        "| Lane | Command | Result | Duration |",
        "|---|---|---:|---:|",
    ]
    for item in report["results"]:
        result = "PASS" if item.get("passed") else "FAIL"
        lines.append(
            f"| {item['lane']} | `{item['commandText']}` | `{result}` | `{item['durationSec']}s` |"
        )
    live = report.get("liveReadiness") or {}
    env_flags = report.get("envFlags") or {}
    lines.extend([
        "",
        "## Live Readiness Snapshot",
        "",
        f"- Ready for live: `{live.get('readyForLive')}`",
        f"- Ready for demo expansion: `{live.get('readyForDemoExpansion')}`",
        f"- Blockers: `{live.get('blockers', [])}`",
        "",
        "## Locked Env",
        "",
        f"- BILL_ENABLE_FUTURES_DEMO_EXECUTION: `{env_flags.get('BILL_ENABLE_FUTURES_DEMO_EXECUTION')}`",
        f"- RH_TOPSTEP_READ_ONLY: `{env_flags.get('RH_TOPSTEP_READ_ONLY')}`",
        f"- RH_LIVE_EXECUTION_ENABLED: `{env_flags.get('RH_LIVE_EXECUTION_ENABLED')}`",
        "",
        "## Hard Rules",
        "",
    ])
    for rule in report["hardRules"]:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-slow-tests", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(include_slow_tests=not args.skip_slow_tests)
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown.write_text(render_markdown(report))
    print(json.dumps({
        "status": report["status"],
        "allCommandsPassed": report["allCommandsPassed"],
        "failedCommandIds": report["failedCommandIds"],
        "json": str(output),
        "markdown": str(markdown),
    }, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
