#!/usr/bin/env python3
"""Materialize prediction event-lag watch scenarios for manual review.

This is research-only. It reruns only sensitivity scenarios that reached
`research-only-event-lag-replay-watch` and extracts the repriced windows so a
human or weaker agent can inspect the exact mapped event, token, horizon, and
quote movement before any paper-review discussion.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from prediction_event_lag_replay import MAPPING_PLAN, STATE, build_replay, read_json
except ModuleNotFoundError:  # pragma: no cover - package import in tests
    from scripts.prediction_event_lag_replay import MAPPING_PLAN, STATE, build_replay, read_json


VAULT = Path.home() / "Documents" / "memorybrain"
SENSITIVITY = STATE / "prediction-event-lag-sensitivity.latest.json"
OUT = STATE / "prediction-event-lag-watch-review.latest.json"
OUT_MD = VAULT / "Agent-Hermes" / "prediction-event-lag-watch-review-2026-05-31.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_ms(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def scenario_params(baseline: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    params = {
        "pre_minutes": int(baseline.get("preMinutes") or 30),
        "horizons_minutes": list(baseline.get("horizonsMinutes") or [15, 30, 60, 120]),
        "min_abs_move": float(baseline.get("minimumAbsMove") or 0.01),
        "min_events": int(baseline.get("minimumCompleteEvents") or 3),
    }
    variable = scenario.get("variable")
    value = scenario.get("value")
    if variable == "preMinutes":
        params["pre_minutes"] = int(value)
    elif variable == "minimumAbsMove":
        params["min_abs_move"] = float(value)
    elif variable == "horizonsMinutes" and isinstance(value, list):
        params["horizons_minutes"] = [int(item) for item in value]
    return params


def compact_window(scenario: dict[str, Any], window: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenarioLabel": scenario.get("label"),
        "variable": scenario.get("variable"),
        "value": scenario.get("value"),
        "externalId": window.get("externalId"),
        "clobTokenId": window.get("clobTokenId"),
        "headline": window.get("headline"),
        "question": window.get("question"),
        "source": window.get("source"),
        "eventIso": iso_ms(window.get("eventTsMs")),
        "preQuoteIso": iso_ms(window.get("preQuoteTsMs")),
        "postQuoteIso": iso_ms(window.get("postQuoteTsMs")),
        "preAgeSec": window.get("preAgeSec"),
        "postDelaySec": window.get("postDelaySec"),
        "horizonMinutes": window.get("horizonMinutes"),
        "preMid": window.get("preMid"),
        "postMid": window.get("postMid"),
        "midMove": window.get("midMove"),
        "absMidMove": window.get("absMidMove"),
        "preSpread": window.get("preSpread"),
        "absMoveAfterHalfSpread": window.get("absMoveAfterHalfSpread"),
        "repriced": bool(window.get("repriced")),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }


def build_review(
    *,
    sensitivity: dict[str, Any],
    mapping_plan: dict[str, Any],
    clob_paths: list[Path],
) -> dict[str, Any]:
    baseline = sensitivity.get("baseline") if isinstance(sensitivity.get("baseline"), dict) else {}
    scenarios = sensitivity.get("scenarios") if isinstance(sensitivity.get("scenarios"), list) else []
    watch_scenarios = [
        item for item in scenarios
        if isinstance(item, dict) and item.get("decision") == "research-only-event-lag-replay-watch"
    ]

    scenario_reviews: list[dict[str, Any]] = []
    watch_windows: list[dict[str, Any]] = []
    for scenario in watch_scenarios:
        params = scenario_params(baseline, scenario)
        replay = build_replay(mapping_plan=mapping_plan, clob_paths=clob_paths, **params)
        repriced_windows = [
            compact_window(scenario, window)
            for window in replay.get("sampleWindows", [])
            if isinstance(window, dict) and window.get("repriced")
        ]
        watch_windows.extend(repriced_windows)
        scenario_reviews.append({
            "label": scenario.get("label"),
            "variable": scenario.get("variable"),
            "value": scenario.get("value"),
            "decision": replay.get("decision"),
            "completeWindowCount": replay.get("completeWindowCount"),
            "repricedWindowCount": replay.get("repricedWindowCount"),
            "repricedWindows": repriced_windows,
            "blockers": replay.get("blockers", []),
            "readyForPaper": False,
            "readyForExecution": False,
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        })

    unique_windows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for window in watch_windows:
        key = (
            window.get("externalId"),
            window.get("clobTokenId"),
            window.get("eventIso"),
            window.get("preQuoteIso"),
            window.get("postQuoteIso"),
            window.get("horizonMinutes"),
        )
        unique_windows_by_key.setdefault(key, window)
    unique_watch_windows = list(unique_windows_by_key.values())

    blockers: list[str] = []
    if not watch_scenarios:
        blockers.append("no-watch-scenarios-from-sensitivity")
    if not unique_watch_windows:
        blockers.append("no-repriced-watch-windows-materialized")
    blockers.append("manual-review-required-before-forward-capture-or-paper-discussion")

    return {
        "command": "prediction-event-lag-watch-review",
        "generatedAt": now_iso(),
        "decision": "research-only-event-lag-watch-review-visible" if watch_windows else "research-only-event-lag-watch-review-blocked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "watchReady": bool(unique_watch_windows),
        "readyForPaper": False,
        "readyForExecution": False,
        "sensitivityDecision": sensitivity.get("decision"),
        "watchScenarioCount": len(watch_scenarios),
        "scenarioRepricedWindowCount": len(watch_windows),
        "repricedWatchWindowCount": len(unique_watch_windows),
        "duplicateScenarioWindowCount": max(0, len(watch_windows) - len(unique_watch_windows)),
        "scenarioReviews": scenario_reviews,
        "watchWindows": unique_watch_windows,
        "blockers": blockers,
        "nextAction": "Manually review each watch window, then continue forward public CLOB capture through future mapped events.",
        "hardRules": [
            "This artifact is manual research review only.",
            "No paper, funding, demo, live, sizing, or broker route is approved.",
            "A repriced watch window is not a trade signal and does not imply direction or expectancy.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction Event Lag Watch Review - 2026-05-31",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only manual review packet for sensitivity watch scenarios.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Watch scenarios: `{payload.get('watchScenarioCount')}`",
        f"- Repriced watch windows: `{payload.get('repricedWatchWindowCount')}`",
        f"- Watch ready: `{payload.get('watchReady')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        f"- Next action: {payload.get('nextAction')}",
        "",
        "## Watch Windows",
        "",
    ]
    for item in payload.get("watchWindows") or []:
        lines.append(
            f"- Scenario `{item.get('scenarioLabel')}` token `{item.get('clobTokenId')}` "
            f"horizon `{item.get('horizonMinutes')}`m event `{item.get('eventIso')}` "
            f"move `{item.get('midMove')}` abs `{item.get('absMidMove')}` "
            f"question `{item.get('question')}`"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build research-only event-lag watch review packet.")
    parser.add_argument("--sensitivity", default=str(SENSITIVITY))
    parser.add_argument("--mapping-plan", default=str(MAPPING_PLAN))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    args = parser.parse_args()

    sensitivity = read_json(Path(args.sensitivity))
    clob_paths = [Path(path) for path in sensitivity.get("clobPaths", []) if path]
    payload = build_review(
        sensitivity=sensitivity,
        mapping_plan=read_json(Path(args.mapping_plan)),
        clob_paths=clob_paths,
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
