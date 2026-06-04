#!/usr/bin/env python3
"""Summarize the Bill strategy-test framework recovery state.

This artifact exists because long-running strategy research can leave stale
handoffs behind. It does not run backtests, touch Topstep, place orders, or
approve routing. It makes the current evidence explicit so Hermes/Codex can
recover from a stuck walk-forward thread safely.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DATA = ROOT / "data" / "free"
HERMES = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "strategy-test-framework-status.latest.json"
DEFAULT_MARKDOWN = HERMES / "strategy-test-framework-status.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_hours(value: Any, now: datetime) -> float | None:
    generated = parse_dt(value)
    if generated is None:
        return None
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return round(max(0.0, (now - generated.astimezone(timezone.utc)).total_seconds() / 3600), 2)


def file_probe(path: Path) -> dict[str, Any]:
    exists = path.exists()
    row: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
    }
    if exists:
        stat = path.stat()
        row.update({
            "sizeBytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    return row


def matrix_summary(matrix: dict[str, Any], now: datetime) -> dict[str, Any]:
    configs = matrix.get("configs") if isinstance(matrix.get("configs"), list) else []
    windows = [
        int(config.get("windowsEvaluated") or 0)
        for config in configs
        if isinstance(config, dict)
    ]
    best_config = None
    comparison = matrix.get("comparison") if isinstance(matrix.get("comparison"), dict) else {}
    if comparison.get("bestConfigId"):
        best_config = comparison.get("bestConfigId")
    elif configs:
        best_config = configs[0].get("configId") if isinstance(configs[0], dict) else None
    failures = sorted({
        failure
        for config in configs
        if isinstance(config, dict)
        for failure in (config.get("failureModes") or [])
        if isinstance(failure, str)
    })
    return {
        "present": bool(matrix),
        "generatedAt": matrix.get("generatedAt"),
        "ageHours": age_hours(matrix.get("generatedAt"), now),
        "status": matrix.get("status", "missing"),
        "csvPath": matrix.get("csvPath"),
        "configCount": len(configs),
        "totalWindowsEvaluated": sum(windows),
        "maxWindowsEvaluated": max(windows) if windows else 0,
        "bestConfigId": best_config,
        "commonFailureModes": failures[:8],
        "recommendation": matrix.get("recommendation") if isinstance(matrix.get("recommendation"), list) else [],
    }


def build_status(
    *,
    now: datetime | None = None,
    matrix: dict[str, Any] | None = None,
    playbook: dict[str, Any] | None = None,
    factory: dict[str, Any] | None = None,
    goal: dict[str, Any] | None = None,
    futures_no_edge: dict[str, Any] | None = None,
    data_dir: Path = DATA,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    matrix = matrix if isinstance(matrix, dict) else read_json(STATE / "walkforward-matrix.latest.json")
    playbook = playbook if isinstance(playbook, dict) else read_json(STATE / "futures-strategy-playbook.latest.json")
    factory = factory if isinstance(factory, dict) else read_json(STATE / "strategy-factory.latest.json")
    goal = goal if isinstance(goal, dict) else read_json(STATE / "bill-goal-completion-audit.latest.json")
    futures_no_edge = futures_no_edge if isinstance(futures_no_edge, dict) else read_json(
        ROOT / ".rumbling-hedge" / "research" / "futures-no-edge-ledger" / "latest.json"
    )

    data_sets = {
        "currentDefaultMatrixCsv": file_probe(data_dir / "ALL-6MARKETS-60m-60d-normalized.csv"),
        "requestedThread90d1m": file_probe(data_dir / "ALL-6MARKETS-1m-90d-normalized.csv"),
        "requestedThread30dOos": file_probe(data_dir / "ALL-6MARKETS-1m-30d.csv"),
        "nqCurrent5m": file_probe(data_dir / "NQ-5m-5d.csv"),
        "nqResearch15m60d": file_probe(data_dir / "NQ-15m-60d.csv"),
    }
    matrix_state = matrix_summary(matrix, now)
    playbook_age = age_hours(playbook.get("generatedAt"), now)
    factory_walkforward_deployable = bool(factory.get("walkforwardDeployable"))
    goal_blocked = goal.get("blockedIds") if isinstance(goal.get("blockedIds"), list) else []
    no_edge_entries = futures_no_edge.get("entries") if isinstance(futures_no_edge.get("entries"), list) else []
    matrix_no_edge_entry = next((
        item for item in no_edge_entries
        if isinstance(item, dict) and item.get("id") == "six-market-walkforward-matrix-current-profile-family"
    ), None)
    legacy_data_requests = [
        {
            "id": "requested-90d-1m-normalized",
            "exists": data_sets["requestedThread90d1m"]["exists"],
            "path": data_sets["requestedThread90d1m"]["path"],
            "status": "optional-after-data-source-review" if matrix_no_edge_entry else "missing",
        },
        {
            "id": "requested-30d-oos-csv",
            "exists": data_sets["requestedThread30dOos"]["exists"],
            "path": data_sets["requestedThread30dOos"]["path"],
            "status": "optional-after-data-source-review" if matrix_no_edge_entry else "missing",
        },
    ]

    blockers: list[str] = []
    if not data_sets["currentDefaultMatrixCsv"]["exists"]:
        blockers.append("default-matrix-csv-missing")
    if not data_sets["requestedThread90d1m"]["exists"] and not matrix_no_edge_entry:
        blockers.append("requested-90d-1m-normalized-missing")
    if not data_sets["requestedThread30dOos"]["exists"] and not matrix_no_edge_entry:
        blockers.append("requested-30d-oos-csv-missing")
    if not matrix_state["present"]:
        blockers.append("walkforward-matrix-missing")
    if matrix_state.get("ageHours") is None or matrix_state.get("ageHours", 999) > 24:
        blockers.append("walkforward-matrix-stale")
    if matrix_state.get("status") != "robust-candidate":
        blockers.append("walkforward-matrix-not-robust")
    if matrix_state.get("status") == "reject" and not matrix_no_edge_entry:
        blockers.append("walkforward-matrix-rejection-not-recorded")
    if not factory_walkforward_deployable:
        blockers.append("strategy-factory-not-deployable")
    if goal_blocked:
        blockers.append("goal-audit-still-blocked")
    if playbook_age is None or playbook_age > 24:
        blockers.append("strategy-playbook-stale")

    next_commands = [
        {
            "id": "registration-and-matrix-smoke",
            "command": "npm run --silent test -- tests/walkforwardMatrix.test.ts tests/strategyRegistrationGuard.test.ts",
            "why": "Prove the framework and strategy registration still work before any large matrix run.",
            "touchesBroker": False,
            "writesOrders": False,
        },
        {
            "id": "refresh-current-default-matrix",
            "command": "npm run --silent bill:walkforward-matrix",
            "why": "Refresh the bounded 60m/60d six-market matrix already wired in package.json.",
            "touchesBroker": False,
            "writesOrders": False,
        },
        {
            "id": "refresh-strategy-playbook",
            "command": "npm run --silent bill:futures-strategy-playbook",
            "why": "Update Hermes/Codex strategy posture after the matrix and factory evidence change.",
            "touchesBroker": False,
            "writesOrders": False,
        },
    ]
    if not data_sets["requestedThread90d1m"]["exists"]:
        next_commands.append({
            "id": "optional-90d-1m-data-intake",
            "command": "npx tsx src/cli.ts fetch-free-universe 1m 90d",
            "why": "Only run after data-cost review; the current repo does not contain the requested 90d 1m normalized file.",
            "touchesBroker": False,
            "writesOrders": False,
            "operatorReviewRequired": True,
        })

    return {
        "command": "strategy-test-framework-status",
        "generatedAt": now.isoformat(),
        "decision": "research-only-strategy-framework-recovery-blocked" if blockers else "research-only-strategy-framework-watch",
        "researchOnly": True,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "blockedIds": blockers,
        "blockedCount": len(blockers),
        "operatorRead": (
            "Strategy framework evidence is research-only. A matrix refresh can improve readiness evidence, "
            "but it does not approve Topstep demo routing or live capital."
        ),
        "dataSets": data_sets,
        "legacyDataRequests": legacy_data_requests,
        "walkforwardMatrix": matrix_state,
        "strategyFactory": {
            "present": bool(factory),
            "walkforwardDeployable": factory_walkforward_deployable,
            "decision": factory.get("decision"),
            "status": factory.get("status"),
        },
        "futuresNoEdgeMemory": {
            "present": bool(futures_no_edge),
            "generatedAt": futures_no_edge.get("generatedAt"),
            "count": futures_no_edge.get("count", 0),
            "noEdgeCount": futures_no_edge.get("noEdgeCount", 0),
            "needsNewFeatureCount": futures_no_edge.get("needsNewFeatureCount", 0),
            "matrixRejectionRecorded": bool(matrix_no_edge_entry),
            "matrixEntryVerdict": matrix_no_edge_entry.get("verdict") if isinstance(matrix_no_edge_entry, dict) else None,
            "learningSummary": futures_no_edge.get("learningSummary") if isinstance(futures_no_edge.get("learningSummary"), list) else [],
        },
        "strategyPlaybook": {
            "present": bool(playbook),
            "generatedAt": playbook.get("generatedAt"),
            "ageHours": playbook_age,
            "decision": playbook.get("decision"),
            "strategyCount": len(playbook.get("strategies") or []) if isinstance(playbook.get("strategies"), list) else 0,
        },
        "goalAudit": {
            "decision": goal.get("decision"),
            "blockedIds": goal_blocked,
            "passCount": goal.get("passCount"),
            "checkCount": goal.get("checkCount"),
        },
        "nextCommands": next_commands,
        "staleThreadRule": (
            "Any old strategy-thread claim that Topstep demo routing is active is stale unless this artifact, "
            "the daily plan, broker reconciliation, Topstep session safety, source hygiene, and goal audit all clear."
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Strategy Test Framework Status",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        f"Generated: `{payload['generatedAt']}`",
        f"Decision: `{payload['decision']}`",
        f"Ready for execution: `{payload['readyForExecution']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in payload["blockedIds"])
    if not payload["blockedIds"]:
        lines.append("- none")
    lines.extend([
        "",
        "## Walk-Forward Matrix",
        "",
        f"- Status: `{payload['walkforwardMatrix']['status']}`",
        f"- CSV: `{payload['walkforwardMatrix']['csvPath']}`",
        f"- Age hours: `{payload['walkforwardMatrix']['ageHours']}`",
        f"- Total windows evaluated: `{payload['walkforwardMatrix']['totalWindowsEvaluated']}`",
        "",
        "## Data Sets",
        "",
    ])
    for key, row in payload["dataSets"].items():
        lines.append(f"- `{key}`: exists=`{row['exists']}` path=`{row['path']}`")
    lines.extend([
        "",
        "## Legacy Data Requests",
        "",
    ])
    for row in payload.get("legacyDataRequests", []):
        lines.append(f"- `{row['id']}`: `{row['status']}` exists=`{row['exists']}`")
    lines.extend([
        "",
        "## Futures No-Edge Memory",
        "",
        f"- Present: `{payload['futuresNoEdgeMemory']['present']}`",
        f"- Count: `{payload['futuresNoEdgeMemory']['count']}`",
        f"- No-edge count: `{payload['futuresNoEdgeMemory']['noEdgeCount']}`",
        f"- Matrix rejection recorded: `{payload['futuresNoEdgeMemory']['matrixRejectionRecorded']}`",
    ])
    lines.extend(["", "## Next Commands", ""])
    for item in payload["nextCommands"]:
        lines.append(f"- `{item['command']}`")
        lines.append(f"  - {item['why']}")
    lines.extend(["", "## Stale Thread Rule", "", payload["staleThreadRule"]])
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate strategy test framework recovery status.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_status()
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
            "blockedIds": payload["blockedIds"],
            "matrixStatus": payload["walkforwardMatrix"]["status"],
            "readyForExecution": payload["readyForExecution"],
        }, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
