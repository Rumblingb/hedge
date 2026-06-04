#!/usr/bin/env python3
"""Build a fail-closed Topstep session-safety clearance checklist."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_no_execution_enabled_processes import classify, process_rows

STATE = ROOT / ".rumbling-hedge" / "state"
OBSIDIAN = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "topstep-session-safety-clearance.latest.json"
DEFAULT_MARKDOWN = OBSIDIAN / f"topstep-session-safety-clearance-{datetime.now(timezone.utc).date().isoformat()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def automation_safe(audit: dict[str, Any]) -> bool:
    if audit.get("blockers"):
        return False
    rows = audit.get("automations") if isinstance(audit.get("automations"), list) else []
    active_bill = [row for row in rows if isinstance(row, dict) and row.get("billRelated") and row.get("active")]
    return all(
        row.get("forbidsExecution")
        and row.get("hasSafeLocks")
        and not row.get("writesOrders")
        and not row.get("touchesBroker")
        and not row.get("movesFunds")
        for row in active_bill
    )


def cron_safe(validator: dict[str, Any]) -> bool:
    if validator.get("blockingIssueCount") not in (None, 0):
        return False
    broker_refs = validator.get("activeTopstepBrokerSessionCronRefs")
    if broker_refs not in (None, 0, []):
        return False
    if validator.get("activeTradingAgentBacked") not in (None, 0):
        return False
    return True


def build_clearance(
    *,
    session_safety: dict[str, Any] | None = None,
    automation_audit: dict[str, Any] | None = None,
    cron_validator: dict[str, Any] | None = None,
    no_execution_processes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session_safety = session_safety if isinstance(session_safety, dict) else read_json(STATE / "topstep-session-safety.latest.json")
    automation_audit = automation_audit if isinstance(automation_audit, dict) else read_json(STATE / "codex-automation-audit.latest.json")
    cron_validator = cron_validator if isinstance(cron_validator, dict) else read_json(STATE / "cron-state-validator.latest.json")
    no_execution_processes = no_execution_processes if isinstance(no_execution_processes, dict) else classify(process_rows())

    pause_active = bool_value(session_safety.get("pauseBrokerTouchingProofs")) or bool_value(session_safety.get("topstepMultipleSessionsDetected"))
    operator_confirmed = bool_value(session_safety.get("operatorConfirmedTopstepWarningCleared"))
    checks = [
        {
            "id": "no-execution-processes",
            "status": "pass" if no_execution_processes.get("ok") else "blocked",
            "evidence": {
                "candidateCount": no_execution_processes.get("candidateCount"),
                "unsafeCount": no_execution_processes.get("unsafeCount"),
            },
        },
        {
            "id": "automation-safe-locks",
            "status": "pass" if automation_safe(automation_audit) else "blocked",
            "evidence": {
                "activeBillAutomationCount": automation_audit.get("activeBillAutomationCount"),
                "blockers": automation_audit.get("blockers", []),
            },
        },
        {
            "id": "cron-broker-session-quiet",
            "status": "pass" if cron_safe(cron_validator) else "blocked",
            "evidence": {
                "blockingIssueCount": cron_validator.get("blockingIssueCount"),
                "activeTopstepBrokerSessionCronRefs": cron_validator.get("activeTopstepBrokerSessionCronRefs"),
                "activeTradingAgentBacked": cron_validator.get("activeTradingAgentBacked"),
            },
        },
        {
            "id": "operator-confirms-topstep-warning-cleared",
            "status": "pass" if operator_confirmed and not pause_active else "blocked",
            "evidence": {
                "pauseBrokerTouchingProofs": session_safety.get("pauseBrokerTouchingProofs"),
                "topstepMultipleSessionsDetected": session_safety.get("topstepMultipleSessionsDetected"),
                "operatorConfirmedTopstepWarningCleared": session_safety.get("operatorConfirmedTopstepWarningCleared"),
                "safeUntil": session_safety.get("safeUntil"),
            },
        },
    ]
    machine_checks_passed = all(row["status"] == "pass" for row in checks if row["id"] != "operator-confirms-topstep-warning-cleared")
    operator_required = checks[-1]["status"] != "pass"
    ready_for_proof_window = machine_checks_passed and not operator_required
    blockers = [row["id"] for row in checks if row["status"] != "pass"]
    return {
        "command": "topstep-session-safety-clearance",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "operator-confirmation-required" if operator_required else "proof-window-checklist-ready",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "machineChecksPassed": machine_checks_passed,
        "operatorConfirmationRequired": operator_required,
        "readyForReadOnlyProofWindow": ready_for_proof_window,
        "mayOpenBrokerSession": False,
        "blockers": blockers,
        "checks": checks,
        "nextSafeActions": [
            "Keep BILL_ENABLE_FUTURES_DEMO_EXECUTION=false, RH_TOPSTEP_READ_ONLY=true, and RH_LIVE_EXECUTION_ENABLED=false.",
            "Verify no unsafe execution processes before any read-only proof window.",
            "Close extra TopstepX/ProjectX browser/API sessions and have the operator confirm the warning is cleared.",
            "Only after operator confirmation, run a deliberately bounded read-only proof window; this artifact still does not approve orders.",
        ],
        "sessionSafety": {
            "pauseBrokerTouchingProofs": session_safety.get("pauseBrokerTouchingProofs"),
            "reason": session_safety.get("reason"),
            "safeUntil": session_safety.get("safeUntil"),
            "lastMitigation": session_safety.get("lastMitigation"),
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Topstep Session Safety Clearance",
        "",
        f"Generated: `{payload['generatedAt']}`",
        f"Decision: `{payload['decision']}`",
        "",
        "## Checks",
        "",
    ]
    for check in payload["checks"]:
        lines.append(f"- `{check['id']}`: `{check['status']}`")
    lines.extend(["", "## Next Safe Actions", ""])
    lines.extend(f"- {item}" for item in payload["nextSafeActions"])
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Topstep session-safety clearance checklist.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_clearance()
    if not args.dry_run:
        output = Path(args.output)
        markdown = Path(args.markdown)
        output.parent.mkdir(parents=True, exist_ok=True)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        markdown.write_text(render_markdown(payload))
    if args.compact:
        print(json.dumps({
            "decision": payload["decision"],
            "machineChecksPassed": payload["machineChecksPassed"],
            "operatorConfirmationRequired": payload["operatorConfirmationRequired"],
            "readyForReadOnlyProofWindow": payload["readyForReadOnlyProofWindow"],
            "blockers": payload["blockers"],
        }, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
