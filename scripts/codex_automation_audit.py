#!/usr/bin/env python3
"""Audit Codex app automations that can affect Bill/Hermes research loops.

This is read-only. It exists because Codex app automations live outside the
Hermes cron registry, so they need their own visibility artifact before agents
can trust that storage-heavy capture loops are controlled.
"""
from __future__ import annotations

import argparse
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_AUTOMATION_ROOT = Path.home() / ".codex" / "automations"
DEFAULT_HERMES_JOBS = Path.home() / ".hermes" / "cron" / "jobs.json"
DEFAULT_HERMES_RECORDER_SCRIPT = Path.home() / ".hermes" / "scripts" / "polymarket_clob_recorder.sh"
DEFAULT_OUTPUT = STATE / "codex-automation-audit.latest.json"

TRADING_TERMS = (
    "bill",
    "hermes",
    "topstep",
    "futures",
    "prediction",
    "polymarket",
    "kalshi",
    "clob",
    "broker",
)
PREDICTION_CAPTURE_TERMS = (
    "prediction-event-capture-cycle",
    "polymarket-clob-recorder",
    "clob capture",
)
FUTURES_OPEN_SESSION_TERMS = (
    "open-session data proof",
    "open session data proof",
    "open-session-data-proof",
)
STORAGE_BOUND_TERMS = ("--max-output-mb", "--min-free-gb")
SAFE_LOCK_TERMS = (
    "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false",
    "RH_TOPSTEP_READ_ONLY=true",
    "RH_LIVE_EXECUTION_ENABLED=false",
)
FORBIDDEN_ACTIVE_APPROVAL_TERMS = (
    "enable demo/live",
    "approve paper/demo/live",
    "mark the goal complete unless",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_markdown_path() -> Path:
    audit_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"codex-automation-audit-{audit_date}.md"


def read_toml(path: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def automation_text(row: dict[str, Any]) -> str:
    return "\n".join(str(row.get(key) or "") for key in ("id", "name", "prompt")).lower()


def is_bill_related(row: dict[str, Any]) -> bool:
    text = automation_text(row)
    return any(term in text for term in TRADING_TERMS)


def is_active(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "").upper() == "ACTIVE"


def is_prediction_capture(row: dict[str, Any]) -> bool:
    text = automation_text(row)
    return any(term in text for term in PREDICTION_CAPTURE_TERMS)


def is_futures_open_session_proof(row: dict[str, Any]) -> bool:
    text = automation_text(row)
    return any(term in text for term in FUTURES_OPEN_SESSION_TERMS)


def rrule_text(row: dict[str, Any]) -> str:
    return str(row.get("rrule") or "")


def dtstart_value(row: dict[str, Any]) -> str | None:
    for line in rrule_text(row).splitlines():
        if line.startswith("DTSTART:"):
            return line.split(":", 1)[1].strip()
    return None


def dtstart_datetime(row: dict[str, Any]) -> datetime | None:
    value = dtstart_value(row)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def rrule_body(row: dict[str, Any]) -> str:
    for line in rrule_text(row).splitlines():
        if line.startswith("RRULE:"):
            return line.split(":", 1)[1].strip()
    return rrule_text(row).strip()


def rrule_parts(row: dict[str, Any]) -> dict[str, str]:
    parts: dict[str, str] = {}
    for chunk in rrule_body(row).split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parts[key.upper()] = value
    return parts


def weekly_rrule_matches_dtstart(row: dict[str, Any], dt: datetime) -> bool:
    parts = rrule_parts(row)
    weekday = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][dt.weekday()]
    return (
        parts.get("FREQ") == "WEEKLY"
        and parts.get("BYDAY") == weekday
        and int(parts.get("BYHOUR", "-1")) == dt.hour
        and int(parts.get("BYMINUTE", "-1")) == dt.minute
    )


def same_futures_proof_window(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_start = dtstart_datetime(left)
    right_start = dtstart_datetime(right)
    if left_start and right_start:
        return left_start == right_start
    if left_start and not right_start:
        return weekly_rrule_matches_dtstart(right, left_start)
    if right_start and not left_start:
        return weekly_rrule_matches_dtstart(left, right_start)
    return rrule_body(left) == rrule_body(right)


def active_futures_open_session_conflict_ids(rows: list[dict[str, Any]]) -> list[str]:
    conflicts: set[str] = set()
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            if same_futures_proof_window(left, right):
                conflicts.add(str(left["id"]))
                conflicts.add(str(right["id"]))
    return sorted(conflicts)


def is_storage_bounded(row: dict[str, Any]) -> bool:
    text = automation_text(row)
    return all(term in text for term in STORAGE_BOUND_TERMS)


def has_safe_locks(row: dict[str, Any]) -> bool:
    text = "\n".join(str(row.get(key) or "") for key in ("prompt", "id", "name"))
    return all(term in text for term in SAFE_LOCK_TERMS)


def forbids_execution(row: dict[str, Any]) -> bool:
    prompt = str(row.get("prompt") or "").lower()
    return (
        "do not submit orders" in prompt
        or "do not place orders" in prompt
        or "do not fund accounts" in prompt
    ) and (
        "do not" in prompt and ("enable demo" in prompt or "enable paper" in prompt or "mark the goal complete" in prompt)
    )


def summarize_automation(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    bill_related = is_bill_related(row)
    prediction_capture = is_prediction_capture(row)
    storage_bounded = is_storage_bounded(row)
    active = is_active(row)
    return {
        "id": row.get("id") or path.parent.name,
        "name": row.get("name"),
        "kind": row.get("kind"),
        "status": row.get("status"),
        "rrule": row.get("rrule"),
        "model": row.get("model"),
        "reasoningEffort": row.get("reasoning_effort") or row.get("reasoningEffort"),
        "cwds": row.get("cwds", []),
        "path": str(path),
        "billRelated": bill_related,
        "active": active,
        "predictionCapture": prediction_capture,
        "futuresOpenSessionProof": is_futures_open_session_proof(row),
        "storageHeavy": prediction_capture,
        "storageBounded": storage_bounded,
        "hasSafeLocks": has_safe_locks(row),
        "forbidsExecution": forbids_execution(row),
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForPaper": False,
        "readyForDemoExpansion": False,
    }


def build_audit(
    automation_root: Path,
    *,
    hermes_jobs_path: Path | None = None,
    hermes_recorder_script_path: Path | None = None,
) -> dict[str, Any]:
    paths = sorted(automation_root.glob("*/automation.toml")) if automation_root.exists() else []
    rows = [summarize_automation(path, read_toml(path)) for path in paths]
    bill_rows = [row for row in rows if row["billRelated"]]
    active_bill = [row for row in bill_rows if row["active"]]
    active_prediction_captures = [
        row for row in active_bill if row["predictionCapture"]
    ]
    active_futures_open_session_proofs = [
        row for row in active_bill if row["futuresOpenSessionProof"]
    ]
    active_futures_open_session_conflicts = active_futures_open_session_conflict_ids(active_futures_open_session_proofs)
    paused_prediction_captures = [
        row for row in bill_rows if row["predictionCapture"] and not row["active"]
    ]
    active_storage_unbounded = [
        row for row in active_prediction_captures if row["storageBounded"] is not True
    ]
    active_missing_locks = [
        row for row in active_bill if row["hasSafeLocks"] is not True
    ]
    active_missing_no_execution = [
        row for row in active_bill if row["forbidsExecution"] is not True
    ]
    duplicate_active_prediction_capture = len(active_prediction_captures) > 1
    duplicate_active_futures_open_session_proof = bool(active_futures_open_session_conflicts)
    hermes_jobs = read_json(hermes_jobs_path).get("jobs")
    hermes_rows = [row for row in hermes_jobs if isinstance(row, dict)] if isinstance(hermes_jobs, list) else []
    hermes_recorder = next((row for row in hermes_rows if row.get("name") == "prediction-clob-recorder"), {})
    hermes_analysis = next((row for row in hermes_rows if row.get("name") == "prediction-snapshot-refresh"), {})
    recorder_script_text = ""
    if hermes_recorder_script_path is not None:
        try:
            recorder_script_text = hermes_recorder_script_path.read_text()
        except Exception:
            recorder_script_text = ""
    recorder_prompt = str(hermes_recorder.get("prompt") or "").lower()
    analysis_prompt = str(hermes_analysis.get("prompt") or "").lower()
    hermes_recorder_safe = (
        hermes_recorder.get("enabled") is True
        and hermes_recorder.get("no_agent") is True
        and hermes_recorder.get("script") == "polymarket_clob_recorder.sh"
        and hermes_recorder.get("last_status") == "ok"
        and not hermes_recorder.get("last_error")
        and all(term in recorder_prompt for term in ("research-only", "orders", "fund", "broker"))
        and all(term in recorder_script_text for term in ("--duration-sec 90", "--max-output-mb", "--min-free-gb", "Seagate Expansion Drive"))
    )
    hermes_analysis_safe = (
        hermes_analysis.get("enabled") is True
        and hermes_analysis.get("no_agent") is True
        and hermes_analysis.get("script") == "bill_prediction_snapshot_refresh.sh"
        and hermes_analysis.get("last_status") == "ok"
        and not hermes_analysis.get("last_error")
        and all(term in analysis_prompt for term in ("research-only", "orders", "funds", "broker"))
    )
    hermes_prediction_loop_consolidated = hermes_recorder_safe and hermes_analysis_safe
    codex_prediction_loop_active = len(active_prediction_captures) == 1
    prediction_control_evaluated = bool(active_prediction_captures or paused_prediction_captures) or hermes_jobs_path is not None
    blockers: list[str] = []
    if duplicate_active_prediction_capture:
        blockers.append("multiple-active-prediction-clob-captures")
    if duplicate_active_futures_open_session_proof:
        blockers.append("multiple-active-futures-open-session-proofs")
    if active_storage_unbounded:
        blockers.append("active-prediction-capture-missing-storage-bounds")
    if active_missing_locks:
        blockers.append("active-bill-automation-missing-safe-lock-flags")
    if active_missing_no_execution:
        blockers.append("active-bill-automation-missing-no-execution-language")
    if codex_prediction_loop_active and hermes_recorder_safe:
        blockers.append("multiple-active-prediction-clob-captures-across-schedulers")
    if prediction_control_evaluated and not codex_prediction_loop_active and not hermes_prediction_loop_consolidated:
        blockers.append("no-validated-active-prediction-capture-loop")
    status = "PASS" if not blockers else "BLOCKED"
    return {
        "command": "codex-automation-audit",
        "generatedAt": now_iso(),
        "automationRoot": str(automation_root),
        "status": status,
        "decision": "codex-automations-visible-research-locked" if status == "PASS" else "codex-automation-review-required",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForPaper": False,
        "readyForDemoExpansion": False,
        "blockers": blockers,
        "automationCount": len(rows),
        "billAutomationCount": len(bill_rows),
        "activeBillAutomationCount": len(active_bill),
        "activePredictionCaptureCount": len(active_prediction_captures),
        "activeFuturesOpenSessionProofCount": len(active_futures_open_session_proofs),
        "activeFuturesOpenSessionProofConflictIds": active_futures_open_session_conflicts,
        "pausedPredictionCaptureCount": len(paused_prediction_captures),
        "activePredictionCaptureIds": [row["id"] for row in active_prediction_captures],
        "activeFuturesOpenSessionProofIds": [row["id"] for row in active_futures_open_session_proofs],
        "pausedPredictionCaptureIds": [row["id"] for row in paused_prediction_captures],
        "activeHermesPredictionCaptureIds": [str(hermes_recorder.get("id"))] if hermes_recorder_safe else [],
        "activeHermesPredictionAnalysisIds": [str(hermes_analysis.get("id"))] if hermes_analysis_safe else [],
        "hermesPredictionLoopConsolidated": hermes_prediction_loop_consolidated,
        "predictionCaptureAuthority": (
            "codex" if codex_prediction_loop_active and not hermes_recorder_safe
            else "hermes" if hermes_prediction_loop_consolidated and not codex_prediction_loop_active
            else "multiple" if codex_prediction_loop_active and hermes_recorder_safe
            else "none"
        ),
        "activeStorageUnboundedIds": [row["id"] for row in active_storage_unbounded],
        "activeMissingLockIds": [row["id"] for row in active_missing_locks],
        "activeMissingNoExecutionIds": [row["id"] for row in active_missing_no_execution],
        "automations": bill_rows,
        "hardRules": [
            "This audit is read-only and cannot approve paper, demo, live, funding, orders, or broker access.",
            "Only one storage-heavy prediction CLOB capture loop should be active while SSD pressure remains unresolved.",
            "Prediction capture authority may be Codex or Hermes, but never both; the inactive scheduler's duplicate loops stay paused.",
            "Only one futures open-session data proof should run for a given proof window.",
            "Active Bill/Hermes automations must carry safe lock flags and no-execution language.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or datetime.now(timezone.utc).date().isoformat())[:10]
    lines = [
        f"# Codex Automation Audit - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Read-only audit of Codex app automations related to Bill/Hermes.",
        "",
        "## Decision",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Decision: `{payload.get('decision')}`",
        f"- Active Bill automations: `{payload.get('activeBillAutomationCount')}`",
        f"- Active prediction captures: `{payload.get('activePredictionCaptureIds')}`",
        f"- Active futures open-session proofs: `{payload.get('activeFuturesOpenSessionProofIds')}`",
        f"- Paused prediction captures: `{payload.get('pausedPredictionCaptureIds')}`",
        f"- Hermes prediction capture: `{payload.get('activeHermesPredictionCaptureIds')}`",
        f"- Hermes prediction analysis: `{payload.get('activeHermesPredictionAnalysisIds')}`",
        f"- Prediction capture authority: `{payload.get('predictionCaptureAuthority')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        "",
        "## Automations",
        "",
    ]
    for row in payload.get("automations") or []:
        lines.append(f"- `{row.get('id')}` status `{row.get('status')}` kind `{row.get('kind')}` storageBounded `{row.get('storageBounded')}` safeLocks `{row.get('hasSafeLocks')}` noExecution `{row.get('forbidsExecution')}`")
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Codex app automations for Bill/Hermes.")
    parser.add_argument("--automation-root", default=str(DEFAULT_AUTOMATION_ROOT))
    parser.add_argument("--hermes-jobs", default=str(DEFAULT_HERMES_JOBS))
    parser.add_argument("--hermes-recorder-script", default=str(DEFAULT_HERMES_RECORDER_SCRIPT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = build_audit(
        Path(args.automation_root).expanduser(),
        hermes_jobs_path=Path(args.hermes_jobs).expanduser(),
        hermes_recorder_script_path=Path(args.hermes_recorder_script).expanduser(),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown) if args.markdown else default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
