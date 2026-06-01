#!/usr/bin/env python3
"""One-variable sensitivity grid for prediction event-lag replay.

Research-only. This wraps the no-lookahead event-lag replay and changes one
parameter family at a time so weak agents can tell whether a blocked event
study is failing because of threshold choice, pre-window coverage, horizon
choice, or the captured market simply did not reprice.
"""

from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from prediction_event_lag_replay import (
        CLOB_DIR,
        MAPPING_PLAN,
        STATE,
        build_replay,
        read_json,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as package in tests
    from scripts.prediction_event_lag_replay import (
        CLOB_DIR,
        MAPPING_PLAN,
        STATE,
        build_replay,
        read_json,
    )


VAULT = Path.home() / "Documents" / "memorybrain"
OUT = STATE / "prediction-event-lag-sensitivity.latest.json"
OUT_MD = VAULT / "Agent-Hermes" / "prediction-event-lag-sensitivity-2026-05-31.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ints(text: str) -> list[int]:
    return [int(part.strip()) for part in text.split(",") if part.strip()]


def parse_floats(text: str) -> list[float]:
    return [float(part.strip()) for part in text.split(",") if part.strip()]


def compact_replay(label: str, variable: str, value: Any, replay: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "variable": variable,
        "value": value,
        "decision": replay.get("decision"),
        "completeEventCount": replay.get("completeEventCount", 0),
        "completeWindowCount": replay.get("completeWindowCount", 0),
        "repricedWindowCount": replay.get("repricedWindowCount", 0),
        "assetsWithQuotes": replay.get("assetsWithQuotes", 0),
        "assetQuoteCount": replay.get("assetQuoteCount", 0),
        "missingReasonCounts": replay.get("missingReasonCounts", {}),
        "byHorizon": replay.get("byHorizon", {}),
        "blockers": replay.get("blockers", []),
        "readyForPaper": False,
        "readyForExecution": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }


def build_sensitivity(
    *,
    mapping_plan: dict[str, Any],
    clob_paths: list[Path],
    baseline_pre_minutes: int,
    baseline_horizons: list[int],
    baseline_min_abs_move: float,
    pre_minutes_values: list[int],
    min_abs_move_values: list[float],
    horizon_sets: list[list[int]],
    min_events: int,
) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []

    baseline = build_replay(
        mapping_plan=mapping_plan,
        clob_paths=clob_paths,
        pre_minutes=baseline_pre_minutes,
        horizons_minutes=baseline_horizons,
        min_events=min_events,
        min_abs_move=baseline_min_abs_move,
    )
    scenarios.append(compact_replay("baseline", "none", None, baseline))

    for value in pre_minutes_values:
        replay = build_replay(
            mapping_plan=mapping_plan,
            clob_paths=clob_paths,
            pre_minutes=value,
            horizons_minutes=baseline_horizons,
            min_events=min_events,
            min_abs_move=baseline_min_abs_move,
        )
        scenarios.append(compact_replay(f"pre-{value}m", "preMinutes", value, replay))

    for value in min_abs_move_values:
        replay = build_replay(
            mapping_plan=mapping_plan,
            clob_paths=clob_paths,
            pre_minutes=baseline_pre_minutes,
            horizons_minutes=baseline_horizons,
            min_events=min_events,
            min_abs_move=value,
        )
        scenarios.append(compact_replay(f"min-move-{value}", "minimumAbsMove", value, replay))

    for horizons in horizon_sets:
        replay = build_replay(
            mapping_plan=mapping_plan,
            clob_paths=clob_paths,
            pre_minutes=baseline_pre_minutes,
            horizons_minutes=horizons,
            min_events=min_events,
            min_abs_move=baseline_min_abs_move,
        )
        scenarios.append(compact_replay("horizons-" + "-".join(str(item) for item in horizons), "horizonsMinutes", horizons, replay))

    best_repriced = max((int(item.get("repricedWindowCount") or 0) for item in scenarios), default=0)
    best_complete = max((int(item.get("completeWindowCount") or 0) for item in scenarios), default=0)
    watch_scenarios = [item for item in scenarios if item.get("decision") == "research-only-event-lag-replay-watch"]
    blockers: list[str] = []
    if best_complete < min_events:
        blockers.append("sensitivity-too-few-complete-event-windows")
    if best_repriced == 0:
        blockers.append("sensitivity-no-repricing-under-tested-one-variable-grid")
    if watch_scenarios:
        blockers.append("watch-only-scenario-found-manual-review-required")

    return {
        "command": "prediction-event-lag-sensitivity",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "watchReady": bool(watch_scenarios),
        "readyForPaper": False,
        "readyForExecution": False,
        "mappingDecision": mapping_plan.get("decision"),
        "clobPaths": [str(path) for path in clob_paths],
        "baseline": {
            "preMinutes": baseline_pre_minutes,
            "horizonsMinutes": baseline_horizons,
            "minimumAbsMove": baseline_min_abs_move,
            "minimumCompleteEvents": min_events,
        },
        "scenarioCount": len(scenarios),
        "bestCompleteWindowCount": best_complete,
        "bestRepricedWindowCount": best_repriced,
        "watchScenarioCount": len(watch_scenarios),
        "scenarios": scenarios,
        "blockers": blockers,
        "decision": "research-only-event-lag-sensitivity-watch" if watch_scenarios else "research-only-event-lag-sensitivity-blocked",
        "nextAction": (
            "Manually inspect watch scenarios, then require forward capture through future events before paper review."
            if watch_scenarios
            else "Keep standing forward CLOB capture running; current one-variable grid does not produce repricing evidence."
        ),
        "hardRules": [
            "No paper, funding, demo, live, sizing, or broker route is approved by this artifact.",
            "Only one variable family changes per scenario: pre window, repricing threshold, or horizon set.",
            "A watch scenario is not a trade signal; it only authorizes manual research review.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction Event Lag Sensitivity - 2026-05-31",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only one-variable sensitivity around the event-lag replay.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Scenarios: `{payload.get('scenarioCount')}`",
        f"- Best complete windows: `{payload.get('bestCompleteWindowCount')}`",
        f"- Best repriced windows: `{payload.get('bestRepricedWindowCount')}`",
        f"- Watch scenarios: `{payload.get('watchScenarioCount')}`",
        f"- Watch ready: `{payload.get('watchReady')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        f"- Next action: {payload.get('nextAction')}",
        "",
        "## Scenarios",
        "",
    ]
    for item in payload.get("scenarios") or []:
        lines.append(
            f"- `{item.get('label')}` variable `{item.get('variable')}` value `{item.get('value')}` "
            f"decision `{item.get('decision')}` complete `{item.get('completeWindowCount')}` "
            f"repriced `{item.get('repricedWindowCount')}` blockers `{item.get('blockers')}`"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run research-only prediction event-lag one-variable sensitivity.")
    parser.add_argument("--mapping-plan", default=str(MAPPING_PLAN))
    parser.add_argument("--clob-glob", default=str(CLOB_DIR / "*-market-channel.jsonl"))
    parser.add_argument("--baseline-pre-minutes", type=int, default=30)
    parser.add_argument("--baseline-horizons", default="15,30,60,120")
    parser.add_argument("--baseline-min-abs-move", type=float, default=0.01)
    parser.add_argument("--pre-minutes-values", default="15,30,60,120")
    parser.add_argument("--min-abs-move-values", default="0.0025,0.005,0.01,0.02")
    parser.add_argument("--horizon-sets", default="5|15|30|60|120|15,30,60,120")
    parser.add_argument("--min-events", type=int, default=3)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    args = parser.parse_args()

    horizon_sets = [parse_ints(item) for item in args.horizon_sets.split("|") if item.strip()]
    payload = build_sensitivity(
        mapping_plan=read_json(Path(args.mapping_plan)),
        clob_paths=[Path(path) for path in sorted(glob.glob(args.clob_glob))],
        baseline_pre_minutes=args.baseline_pre_minutes,
        baseline_horizons=parse_ints(args.baseline_horizons),
        baseline_min_abs_move=args.baseline_min_abs_move,
        pre_minutes_values=parse_ints(args.pre_minutes_values),
        min_abs_move_values=parse_floats(args.min_abs_move_values),
        horizon_sets=horizon_sets,
        min_events=args.min_events,
    )
    out = Path(args.output)
    md = Path(args.markdown_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
