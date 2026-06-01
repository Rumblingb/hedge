#!/usr/bin/env python3
"""Build the daily Bill/Hermes current alpha watch note.

Research-only. This note is the human-facing synthesis of the current futures
and prediction-market research frontier. It deliberately mirrors gate blockers
so new sources and "gold" ideas cannot be mistaken for execution evidence.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "current-alpha-watch.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"current-alpha-watch-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def action_summary(action: dict[str, Any]) -> dict[str, Any]:
    commands = action.get("commands") if isinstance(action.get("commands"), list) else []
    return {
        "id": action.get("id"),
        "lane": action.get("lane"),
        "priority": action.get("priority"),
        "oneVariable": action.get("oneVariable"),
        "firstCommand": action.get("firstCommand") or (commands[0] if commands else None),
        "promotionGate": action.get("promotionGate"),
        "promotionBlockers": action.get("promotionBlockers") if isinstance(action.get("promotionBlockers"), list) else [],
        "researchOnly": action.get("researchOnly", True),
        "writesOrders": action.get("writesOrders", False),
        "touchesBroker": action.get("touchesBroker", False),
    }


def top_actions(next_actions: dict[str, Any], lane: str, limit: int = 3) -> list[dict[str, Any]]:
    matches = [
        action_summary(action)
        for action in rows(next_actions.get("actions"))
        if action.get("lane") == lane
    ]
    return sorted(matches, key=lambda item: item.get("priority") or 999)[:limit]


def fillable_live_book_count(prediction_capture: dict[str, Any]) -> Any:
    if "fillableLiveBookCount" in prediction_capture:
        return prediction_capture.get("fillableLiveBookCount")
    diagnostics = prediction_capture.get("liveQualityDiagnostics")
    if isinstance(diagnostics, dict) and "fillableLiveBookCount" in diagnostics:
        return diagnostics.get("fillableLiveBookCount")
    latest = prediction_capture.get("latestRecorder")
    latest_diagnostics = latest.get("liveQualityDiagnostics") if isinstance(latest, dict) else None
    if isinstance(latest_diagnostics, dict):
        return latest_diagnostics.get("fillableLiveBookCount")
    return None


def build_watch(
    *,
    alpha_direction: dict[str, Any],
    alpha_tooling: dict[str, Any],
    next_actions: dict[str, Any],
    paper_cards: dict[str, Any],
    seed_triage: dict[str, Any],
    futures_cycle: dict[str, Any],
    prediction_capture: dict[str, Any],
    prediction_gate: dict[str, Any],
    automation_audit: dict[str, Any],
    goal_audit: dict[str, Any],
) -> dict[str, Any]:
    paper_rows = rows(paper_cards.get("cards"))
    futures_papers = [
        {
            "id": card.get("id"),
            "decision": card.get("decision"),
            "tradableVariable": card.get("tradableVariable"),
            "oneVariableTest": card.get("oneVariableTest"),
        }
        for card in paper_rows
        if card.get("lane") == "futures" and card.get("decision") in {"candidate", "candidate-with-caution"}
    ]
    queued_youtube = seed_triage.get("queuedYT")
    if queued_youtube is None:
        summary = seed_triage.get("summary") if isinstance(seed_triage.get("summary"), dict) else {}
        queued_youtube = summary.get("queuedYouTubeSeeds")

    return {
        "command": "current-alpha-watch",
        "generatedAt": now_iso(),
        "decision": "research-only-alpha-watch-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "goalBlockedIds": goal_audit.get("blockedIds") if isinstance(goal_audit.get("blockedIds"), list) else [],
        "goalDecision": goal_audit.get("decision"),
        "readyForResearchLoop": alpha_direction.get("readyForResearchLoop") is True,
        "tooling": {
            "status": alpha_tooling.get("status"),
            "readyForResearchLoop": alpha_tooling.get("readyForResearchLoop") is True,
            "blockers": alpha_tooling.get("blockers") if isinstance(alpha_tooling.get("blockers"), list) else [],
            "warnings": alpha_tooling.get("warnings") if isinstance(alpha_tooling.get("warnings"), list) else [],
            "requiredCommandsMissing": [
                item.get("command")
                for item in rows((alpha_tooling.get("commands") or {}).get("required") if isinstance(alpha_tooling.get("commands"), dict) else [])
                if not item.get("ok")
            ],
            "requiredModulesMissing": [
                item.get("package")
                for item in rows(alpha_tooling.get("pythonModules"))
                if not item.get("ok")
            ],
        },
        "continueLanes": alpha_direction.get("continueLanes") if isinstance(alpha_direction.get("continueLanes"), list) else [],
        "retireOrQuarantineLanes": (
            alpha_direction.get("retireOrQuarantineLanes")
            if isinstance(alpha_direction.get("retireOrQuarantineLanes"), list)
            else []
        ),
        "nextOneVariableTest": alpha_direction.get("nextOneVariableTest") if isinstance(alpha_direction.get("nextOneVariableTest"), dict) else {},
        "futures": {
            "cycleDecision": futures_cycle.get("decision"),
            "cycleBlockers": futures_cycle.get("blockers") if isinstance(futures_cycle.get("blockers"), list) else [],
            "topActions": top_actions(next_actions, "futures"),
            "paperSeeds": futures_papers,
        },
        "predictionMarkets": {
            "captureDecision": prediction_capture.get("decision"),
            "captureBlockers": prediction_capture.get("blockers") if isinstance(prediction_capture.get("blockers"), list) else [],
            "paperGateDecision": prediction_gate.get("decision"),
            "paperGateBlockedIds": prediction_gate.get("blockedIds") if isinstance(prediction_gate.get("blockedIds"), list) else [],
            "fillableLiveBookCount": fillable_live_book_count(prediction_capture),
            "topActions": top_actions(next_actions, "prediction-markets"),
        },
        "seedTriage": {
            "totalSeeds": seed_triage.get("totalSeeds"),
            "queuedYT": queued_youtube,
            "candidateRetest": seed_triage.get("candidateRetest"),
            "executable": seed_triage.get("executable"),
            "decision": seed_triage.get("decision"),
        },
        "automations": {
            "decision": automation_audit.get("decision"),
            "status": automation_audit.get("status"),
            "activePredictionCaptureIds": automation_audit.get("activePredictionCaptureIds") or [],
            "activeFuturesOpenSessionProofIds": automation_audit.get("activeFuturesOpenSessionProofIds") or [],
            "blockers": automation_audit.get("blockers") or [],
        },
        "hardRules": [
            "This watchlist is not execution evidence.",
            "Gold YT/web/paper inputs are hypothesis seeds until translated into one-variable local tests.",
            "Futures demo expansion requires source hygiene, execution-grade realtime data, broker/current parity, OOS, walk-forward, and cost gates.",
            "Prediction-market paper requires no-lookahead event windows, clean mapping, resolved labels, fillable books, and post-spread edge.",
            "LLMs and Obsidian can remember and propose; deterministic gated code routes, and current gates route nothing.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Current Alpha Watch - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only. This page summarizes where Bill/Hermes should look for edge today; it does not approve orders, sizing, demo routing, funding, or prediction-market paper trading.",
        "",
        "## Gate Snapshot",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Goal decision: `{payload.get('goalDecision')}`",
        f"- Goal blockers: `{payload.get('goalBlockedIds')}`",
        f"- Ready for research loop: `{payload.get('readyForResearchLoop')}`",
        f"- Ready for execution/demo/live: `{payload.get('readyForExecution')}` / `{payload.get('readyForDemoExpansion')}` / `{payload.get('readyForLive')}`",
        "",
        "## Tooling",
        "",
    ]
    tooling = payload.get("tooling") or {}
    lines.extend([
        f"- Status: `{tooling.get('status')}`",
        f"- Ready for research loop: `{tooling.get('readyForResearchLoop')}`",
        f"- Blockers: `{tooling.get('blockers')}`",
        f"- Warnings: `{tooling.get('warnings')}`",
        f"- Missing required commands: `{tooling.get('requiredCommandsMissing')}`",
        f"- Missing required modules: `{tooling.get('requiredModulesMissing')}`",
        "",
        "## Continue",
        "",
    ])
    for lane in payload.get("continueLanes") or []:
        lines.append(f"- `{lane.get('id')}`: {lane.get('reason')} One variable: `{lane.get('oneVariable')}`. First command: `{lane.get('firstCommand')}`")

    lines.extend(["", "## Retire Or Quarantine", ""])
    for lane in payload.get("retireOrQuarantineLanes") or []:
        lines.append(f"- `{lane.get('id')}`: {lane.get('reason')}")

    next_test = payload.get("nextOneVariableTest") or {}
    lines.extend([
        "",
        "## Next One-Variable Test",
        "",
        f"- ID: `{next_test.get('id')}`",
        f"- Lane: `{next_test.get('lane')}`",
        f"- One variable: `{next_test.get('oneVariable')}`",
        f"- Command: `{next_test.get('command')}`",
        f"- Success criteria: `{next_test.get('successCriteria')}`",
        f"- Rejection criteria: `{next_test.get('rejectionCriteria')}`",
        "",
        "## Futures",
        "",
    ])
    futures = payload.get("futures") or {}
    lines.append(f"- Cycle decision: `{futures.get('cycleDecision')}`")
    lines.append(f"- Cycle blockers: `{futures.get('cycleBlockers')}`")
    lines.append("- Top actions:")
    for action in futures.get("topActions") or []:
        lines.append(f"  - `{action.get('id')}` one variable `{action.get('oneVariable')}` first command `{action.get('firstCommand')}`")
    lines.append("- Paper-derived seeds:")
    for seed in futures.get("paperSeeds") or []:
        lines.append(f"  - `{seed.get('id')}` `{seed.get('decision')}`: {seed.get('oneVariableTest')}")

    prediction = payload.get("predictionMarkets") or {}
    lines.extend([
        "",
        "## Prediction Markets",
        "",
        f"- Capture decision: `{prediction.get('captureDecision')}`",
        f"- Capture blockers: `{prediction.get('captureBlockers')}`",
        f"- Paper gate: `{prediction.get('paperGateDecision')}`",
        f"- Paper gate blockers: `{prediction.get('paperGateBlockedIds')}`",
        f"- Fillable live books: `{prediction.get('fillableLiveBookCount')}`",
        "- Top actions:",
    ])
    for action in prediction.get("topActions") or []:
        lines.append(f"  - `{action.get('id')}` one variable `{action.get('oneVariable')}` first command `{action.get('firstCommand')}`")

    lines.extend([
        "",
        "## Seeds And Automations",
        "",
        f"- Seed triage: `{payload.get('seedTriage')}`",
        f"- Automations: `{payload.get('automations')}`",
        "",
        "## Hard Rules",
        "",
    ])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_json(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(payload), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the daily Bill/Hermes current alpha watch.")
    parser.add_argument("--alpha-direction", default=str(STATE / "alpha-research-direction-audit.latest.json"))
    parser.add_argument("--alpha-tooling", default=str(STATE / "alpha-research-tooling-check.latest.json"))
    parser.add_argument("--next-actions", default=str(STATE / "bill-next-research-actions.latest.json"))
    parser.add_argument("--paper-cards", default=str(STATE / "paper-source-cards.latest.json"))
    parser.add_argument("--seed-triage", default=str(STATE / "research-seed-triage.latest.json"))
    parser.add_argument("--futures-cycle", default=str(STATE / "futures-nq-research-cycle.latest.json"))
    parser.add_argument("--prediction-capture", default=str(STATE / "prediction-event-capture-cycle.latest.json"))
    parser.add_argument("--prediction-gate", default=str(STATE / "prediction-event-paper-promotion-gate.latest.json"))
    parser.add_argument("--automation-audit", default=str(STATE / "codex-automation-audit.latest.json"))
    parser.add_argument("--goal-audit", default=str(STATE / "bill-goal-completion-audit.latest.json"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_watch(
        alpha_direction=read_json(Path(args.alpha_direction)),
        alpha_tooling=read_json(Path(args.alpha_tooling)),
        next_actions=read_json(Path(args.next_actions)),
        paper_cards=read_json(Path(args.paper_cards)),
        seed_triage=read_json(Path(args.seed_triage)),
        futures_cycle=read_json(Path(args.futures_cycle)),
        prediction_capture=read_json(Path(args.prediction_capture)),
        prediction_gate=read_json(Path(args.prediction_gate)),
        automation_audit=read_json(Path(args.automation_audit)),
        goal_audit=read_json(Path(args.goal_audit)),
    )
    write_json(payload, Path(args.output))
    write_markdown(payload, Path(args.markdown))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
