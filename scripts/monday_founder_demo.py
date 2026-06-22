#!/usr/bin/env python3
"""Refresh and prove the Monday founder presentation without touching a broker.

This is a presentation/control-plane preflight. It forces every execution flag
off, refreshes read-only evidence, and fails unless the Command Center proves a
presentation-ready *and* execution-locked posture.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "monday-founder-demo.latest.json"
COMMAND_CENTER = "http://127.0.0.1:8766"

SAFE_ENV = {
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
    "RH_TOPSTEP_READ_ONLY": "true",
    "RH_LIVE_EXECUTION_ENABLED": "false",
}

STEPS = [
    ("signal-quality-producers", ["bash", str(Path.home() / ".hermes/scripts/signal_quality_producers.sh")], False),
    ("n8n-health", [str(ROOT / ".venv/bin/python"), "scripts/n8n_self_heal.py"], True),
    ("signal-quality-advisor", ["npm", "run", "--silent", "bill:signal-quality-advisor"], False),
    ("source-intake", ["npm", "run", "--silent", "bill:source-intake-manifest"], False),
    ("source-hygiene", ["npm", "run", "--silent", "bill:source-hygiene-plan"], False),
    ("goal-audit", ["npm", "run", "--silent", "bill:goal-completion-audit"], True),
    ("founder-metaprompt", ["npm", "run", "--silent", "bill:founder-quant-cto-metaprompt"], False),
    ("obsidian-sync", ["npm", "run", "--silent", "bill:obsidian-sync"], False),
    ("dashboard-artifacts", ["npm", "run", "--silent", "bill:dashboard"], False),
]


def safe_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(SAFE_ENV)
    return env


def run_step(step_id: str, argv: list[str], allow_nonzero: bool) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=ROOT,
        env=safe_environment(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    output = (result.stdout + "\n" + result.stderr).strip()
    return {
        "id": step_id,
        "argv": argv,
        "exitCode": result.returncode,
        "passed": result.returncode == 0 or allow_nonzero,
        "allowedNonzero": allow_nonzero,
        "durationSeconds": round(time.monotonic() - started, 2),
        "outputTail": output[-1200:],
    }


def fetch_json(path: str, timeout: float = 4) -> dict[str, Any]:
    with urllib.request.urlopen(f"{COMMAND_CENTER}{path}", timeout=timeout) as response:
        return json.loads(response.read())


def ensure_command_center() -> dict[str, Any]:
    try:
        return fetch_json("/api/system")
    except Exception:
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/ai.hermes.command-center"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        for _ in range(8):
            time.sleep(0.5)
            try:
                return fetch_json("/api/system")
            except Exception:
                continue
        raise RuntimeError("Command Center did not become reachable on 127.0.0.1:8766")


def assess_readiness(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if payload.get("readyForPresentationDemo") is not True:
        blockers.append("presentation readiness is not green")
    if payload.get("readyForExecution") is not False:
        blockers.append("readyForExecution must remain false")
    if payload.get("readyForDemoExpansion") is not False:
        blockers.append("readyForDemoExpansion must remain false")
    clearance = payload.get("tradeClearance") if isinstance(payload.get("tradeClearance"), dict) else {}
    if clearance.get("executionLocked") is not True:
        blockers.append("trade clearance does not prove executionLocked=true")
    return not blockers, blockers


def main() -> int:
    step_results = [run_step(*step) for step in STEPS]
    ensure_command_center()
    monday = fetch_json("/api/monday-readiness")
    live_readiness = fetch_json("/api/live-readiness-gate")
    ready, blockers = assess_readiness(monday)
    failed_steps = [step["id"] for step in step_results if not step["passed"]]
    if failed_steps:
        blockers.append(f"refresh steps failed: {', '.join(failed_steps)}")
        ready = False
    receipt = {
        "command": "monday-founder-demo",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "presentation-demo-ready-execution-locked" if ready else "presentation-demo-review-required-execution-locked",
        "readyForPresentationDemo": ready,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "readyForLive": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "safeEnv": SAFE_ENV,
        "blockers": blockers,
        "warnings": monday.get("presentationWarnings", []),
        "presentationChecks": monday.get("presentationChecks", []),
        "tradeClearance": monday.get("tradeClearance", {}),
        "liveReadiness": {
            "passCount": live_readiness.get("passCount"),
            "totalCount": live_readiness.get("totalCount"),
            "failedChecks": live_readiness.get("failedChecks", []),
        },
        "steps": step_results,
        "url": COMMAND_CENTER + "/",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "decision": receipt["decision"],
        "readyForPresentationDemo": ready,
        "executionLocked": receipt["tradeClearance"].get("executionLocked"),
        "liveReadiness": receipt["liveReadiness"],
        "warnings": receipt["warnings"],
        "receipt": str(OUT),
        "url": receipt["url"],
    }, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
