#!/usr/bin/env python3
"""Build a refresh plan for stale Bill/Hermes research seed targets.

Research-only. This turns a degraded queued YouTube run into a concrete
operator/agent handoff so the same zero-yield targets are not retried forever.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_TRIAGE = STATE / "research-seed-triage.latest.json"
DEFAULT_TARGETS = STATE / "research-seed-youtube-targets.latest.json"
DEFAULT_OUTPUT = STATE / "research-seed-target-refresh-plan.latest.json"


def default_markdown_path() -> Path:
    return HERMES / f"research-seed-target-refresh-plan-{datetime.now(timezone.utc).date().isoformat()}.md"


def read_json(path: Path, default: Any | None = None) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {} if default is None else default


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def target_id_set(targets: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("id")) for item in targets if item.get("id")}


def latest_run_target_results(latest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in list_of_dicts(latest.get("targetResults"))
        if str(item.get("targetId") or "").startswith("youtube-queue-")
    ]


def latest_run_is_zero_yield_for_targets(latest: dict[str, Any], targets: list[dict[str, Any]]) -> bool:
    ids = target_id_set(targets)
    result_ids = {str(item.get("targetId")) for item in latest_run_target_results(latest) if item.get("targetId")}
    return (
        bool(ids)
        and latest.get("present") is True
        and str(latest.get("status") or "") == "degraded"
        and int(latest.get("chunksCollected") or 0) == 0
        and int(latest.get("strategyHypothesesCount") or 0) == 0
        and ids.issubset(result_ids)
    )


def source_lookup(triage: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in list_of_dicts(triage.get("items")):
        source_id = str(item.get("sourceId") or item.get("id") or "")
        if source_id:
            lookup[source_id] = item
    return lookup


def target_decisions(
    *,
    targets: list[dict[str, Any]],
    triage: dict[str, Any],
    latest: dict[str, Any],
) -> list[dict[str, Any]]:
    lookup = source_lookup(triage)
    result_by_id = {
        str(item.get("targetId")): item
        for item in latest_run_target_results(latest)
        if item.get("targetId")
    }
    zero_yield_same_targets = latest_run_is_zero_yield_for_targets(latest, targets)
    decisions: list[dict[str, Any]] = []
    for target in targets:
        target_id = str(target.get("id") or "missing")
        seed = lookup.get(target_id, {})
        result = result_by_id.get(target_id, {})
        error = result.get("error")
        videos = target.get("videos") if isinstance(target.get("videos"), list) else []
        if error:
            action = "manual-review-url-or-transcript-source"
            rerun_allowed = False
            reason = "latest researcher run reported an error for this target"
        elif zero_yield_same_targets:
            action = "retire-or-manual-convert"
            rerun_allowed = False
            reason = "same queued target already produced zero chunks and zero strategy hypotheses"
        elif not latest.get("present"):
            action = "extract-transcript-once"
            rerun_allowed = True
            reason = "no queued-video researcher run has been observed yet"
        else:
            action = "review-before-rerun"
            rerun_allowed = False
            reason = "target has ambiguous prior extraction evidence"
        decisions.append({
            "targetId": target_id,
            "title": seed.get("title") or target_id,
            "videos": videos,
            "sourceDecision": seed.get("decision"),
            "action": action,
            "rerunAllowed": rerun_allowed,
            "reason": reason,
            "latestResult": {
                "videosProcessed": result.get("videosProcessed"),
                "collected": result.get("collected"),
                "kept": result.get("kept"),
                "error": error,
            } if result else {},
            "manualConversionChecklist": [
                "write explicit market, instrument, timeframe, session, and venue",
                "write entry, invalidation/stop, target/exit, risk, and no-trade rules",
                "write the contrary case and the one variable being tested",
                "link the source URL and mark any narrative claims as unverified",
                "do not run Backtrader/OOS until the rules are machine-testable",
            ],
        })
    return decisions


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    triage = read_json(Path(args.triage))
    target_manifest = read_json(Path(args.targets))
    manifest_targets = list_of_dicts(target_manifest.get("targets"))
    queued_targets = list_of_dicts(triage.get("queuedYouTubeResearcherTargets"))
    targets = manifest_targets or queued_targets
    latest = triage.get("queuedYouTubeLatestRun") if isinstance(triage.get("queuedYouTubeLatestRun"), dict) else {}
    decisions = target_decisions(targets=targets, triage=triage, latest=latest)
    zero_yield = latest_run_is_zero_yield_for_targets(latest, targets)
    retire_count = sum(1 for item in decisions if item.get("action") == "retire-or-manual-convert")
    rerunnable_count = sum(1 for item in decisions if item.get("rerunAllowed") is True)
    decision = "refresh-required-current-targets-exhausted" if zero_yield else "review-targets-before-extraction"
    return {
        "command": "research-seed-target-refresh-plan",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "sourceArtifacts": [
            str(Path(args.triage)),
            str(Path(args.targets)),
        ],
        "latestQueuedRun": {
            "present": bool(latest.get("present")),
            "runId": latest.get("runId"),
            "status": latest.get("status"),
            "chunksCollected": latest.get("chunksCollected"),
            "strategyHypothesesCount": latest.get("strategyHypothesesCount"),
            "blockers": latest.get("blockers") if isinstance(latest.get("blockers"), list) else [],
        },
        "summary": {
            "queuedTargetCount": len(targets),
            "retireOrManualConvertCount": retire_count,
            "rerunnableTargetCount": rerunnable_count,
            "zeroYieldSameTargets": zero_yield,
        },
        "targetDecisions": decisions,
        "newTargetRequirements": [
            "futures or prediction-market source only unless explicitly tagged adjacent-research",
            "source must expose rules or enough detail to write rules without guesswork",
            "one changed variable must be named before implementation",
            "must include contrary/no-trade conditions and failure mode",
            "must have a local dataset or public capture path before replay",
            "must remain research-only until OOS/fillability/cost gates pass",
        ],
        "nextCommands": [
            "npm run --silent bill:research-seed-triage",
            "npm run --silent bill:research-seed-target-refresh-plan",
            "npm run --silent bill:next-research-actions",
        ],
        "hardRules": [
            "Do not rerun a zero-yield queued target without a new transcript source or manual conversion.",
            "Do not treat founder/Hermes gold labels as edge evidence.",
            "Do not create execution, funding, sizing, paper, demo, or live actions from this plan.",
        ],
    }


def render_markdown(plan: dict[str, Any]) -> str:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    latest = plan.get("latestQueuedRun") if isinstance(plan.get("latestQueuedRun"), dict) else {}
    lines = [
        f"# Research Seed Target Refresh Plan - {datetime.now(timezone.utc).date().isoformat()}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only. This note prevents stale YouTube/paper/web seeds from being retried without new evidence.",
        "",
        "## Decision",
        "",
        f"- Decision: `{plan.get('decision')}`",
        f"- Research-only: `{plan.get('researchOnly')}`",
        f"- Writes orders: `{plan.get('writesOrders')}`",
        f"- Touches broker: `{plan.get('touchesBroker')}`",
        f"- Queued targets: `{summary.get('queuedTargetCount', 0)}`",
        f"- Retire or manual-convert: `{summary.get('retireOrManualConvertCount', 0)}`",
        f"- Rerunnable targets: `{summary.get('rerunnableTargetCount', 0)}`",
        f"- Latest run: `{latest.get('runId')}` status `{latest.get('status')}` chunks `{latest.get('chunksCollected')}` hypotheses `{latest.get('strategyHypothesesCount')}`",
        "",
        "## Target Decisions",
        "",
    ]
    decisions = list_of_dicts(plan.get("targetDecisions"))
    if not decisions:
        lines.append("- No queued targets found.")
    for item in decisions:
        videos = item.get("videos") if isinstance(item.get("videos"), list) else []
        lines.append(
            f"- `{item.get('targetId')}` `{item.get('action')}` rerun `{item.get('rerunAllowed')}` - {item.get('title')} - {videos[0] if videos else 'missing-url'}"
        )
        lines.append(f"  - reason: {item.get('reason')}")
    lines.extend(["", "## New Target Requirements", ""])
    for requirement in plan.get("newTargetRequirements") or []:
        lines.append(f"- {requirement}")
    lines.extend(["", "## Next Commands", ""])
    for command in plan.get("nextCommands") or []:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Hard Rules", ""])
    for rule in plan.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a research-only refresh plan for stale Bill/Hermes seed targets.")
    parser.add_argument("--triage", default=str(DEFAULT_TRIAGE))
    parser.add_argument("--targets", default=str(DEFAULT_TARGETS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    plan = build_plan(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown) if args.markdown else default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(plan))
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
