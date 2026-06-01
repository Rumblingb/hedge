#!/usr/bin/env python3
"""Run or plan the prediction event-CLOB capture cycle.

Default mode is a dry-run plan. With ``--run-recorder`` this script runs only
public/read-only CLOB capture plus research follow-ups. It never touches
funding, orders, broker state, or execution routing.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"

CAPTURE_TARGETS = STATE / "prediction-event-clob-capture-targets.latest.json"
EVENT_NEWS_RSS = STATE / "prediction-event-news-rss.latest.json"
EVENT_MARKET_MAPPING = STATE / "prediction-event-market-mapping-plan.latest.json"
EVENT_TIMESTAMP_DATASET = STATE / "prediction-event-timestamp-dataset.latest.json"
EVENT_LAG_REQUIREMENTS = STATE / "prediction-event-lag-requirements.latest.json"
EVENT_LAG_REPLAY = STATE / "prediction-event-lag-replay.latest.json"
EVENT_LAG_SENSITIVITY = STATE / "prediction-event-lag-sensitivity.latest.json"
EVENT_LAG_WATCH_REVIEW = STATE / "prediction-event-lag-watch-review.latest.json"
RECORDER_LATEST = STATE / "polymarket-clob-recorder.latest.json"
CLOB_MICROSTRUCTURE = STATE / "prediction-clob-microstructure-feature-audit.latest.json"
OUT = STATE / "prediction-event-capture-cycle.latest.json"
DEFAULT_STANDING_TERMS = "fed,rate,cpi,inflation,iran,ceasefire,war,trump,tariff,bitcoin,btc,ethereum,eth,nvidia,tesla"
DEFAULT_MAX_OUTPUT_MB = 128
DEFAULT_MIN_FREE_GB = 20


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"prediction-event-capture-cycle-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def compact_output(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def token_targets(capture_targets: dict[str, Any], max_assets: int | None = None) -> list[str]:
    rows = capture_targets.get("targets") if isinstance(capture_targets.get("targets"), list) else []
    tokens = [
        str(item.get("tokenId"))
        for item in rows
        if isinstance(item, dict) and item.get("tokenId")
    ]
    if max_assets is not None:
        return tokens[:max(0, max_assets)]
    return tokens


def review_lead_token_targets(capture_targets: dict[str, Any], max_assets: int | None = None) -> list[str]:
    rows = (
        capture_targets.get("publicCaptureReviewLeads")
        if isinstance(capture_targets.get("publicCaptureReviewLeads"), list)
        else []
    )
    tokens = [
        str(item.get("tokenId"))
        for item in rows
        if isinstance(item, dict) and item.get("tokenId")
    ]
    if max_assets is not None:
        return tokens[:max(0, max_assets)]
    return tokens


def command_text(argv: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in argv)


def npm_cmd(script: str) -> list[str]:
    return ["npm", "run", "--silent", script]


def standing_terms(capture_targets: dict[str, Any]) -> str:
    value = capture_targets.get("standingTerms")
    return str(value).strip() if value else DEFAULT_STANDING_TERMS


def standing_max_assets(capture_targets: dict[str, Any], max_assets: int | None = None) -> int:
    if max_assets is not None:
        return max(1, max_assets)
    try:
        return max(1, int(capture_targets.get("standingMaxAssets") or 20))
    except Exception:
        return 20


def recorder_cmd(
    tokens: list[str],
    *,
    duration_sec: int,
    terms: str | None = None,
    max_assets: int | None = None,
    max_output_mb: int = DEFAULT_MAX_OUTPUT_MB,
    min_free_gb: int = DEFAULT_MIN_FREE_GB,
) -> list[str]:
    cmd = npm_cmd("bill:polymarket-clob-recorder") + [
        "--",
        "--duration-sec",
        str(duration_sec),
        "--max-assets",
        str(len(tokens) if tokens else standing_max_assets({}, max_assets)),
        "--max-output-mb",
        str(max_output_mb),
        "--min-free-gb",
        str(min_free_gb),
    ]
    if tokens:
        for token in tokens:
            cmd.extend(["--token-id", token])
    elif terms:
        cmd.extend(["--terms", terms])
    return cmd


def planned_steps(
    tokens: list[str],
    *,
    duration_sec: int,
    terms: str | None = None,
    max_assets: int | None = None,
    max_output_mb: int = DEFAULT_MAX_OUTPUT_MB,
    min_free_gb: int = DEFAULT_MIN_FREE_GB,
) -> list[dict[str, Any]]:
    recorder = recorder_cmd(
        tokens,
        duration_sec=duration_sec,
        terms=terms,
        max_assets=max_assets,
        max_output_mb=max_output_mb,
        min_free_gb=min_free_gb,
    ) if tokens or terms else []
    raw_steps = [
        ("refresh-news-before-capture", npm_cmd("bill:prediction-event-news-rss"), False),
        ("refresh-mapping-before-capture", npm_cmd("bill:prediction-event-market-mapping-plan"), False),
        ("refresh-timestamps-before-capture", npm_cmd("bill:prediction-event-timestamp-dataset"), False),
        ("refresh-requirements-before-capture", npm_cmd("bill:prediction-event-lag-requirements"), False),
        ("refresh-capture-targets", npm_cmd("bill:prediction-event-clob-capture-targets"), False),
        ("record-public-clob", recorder, True),
        ("refresh-news-after-capture", npm_cmd("bill:prediction-event-news-rss"), False),
        ("refresh-mapping-after-capture", npm_cmd("bill:prediction-event-market-mapping-plan"), False),
        ("refresh-timestamps-after-capture", npm_cmd("bill:prediction-event-timestamp-dataset"), False),
        ("refresh-requirements-after-capture", npm_cmd("bill:prediction-event-lag-requirements"), False),
        ("audit-clob-microstructure", npm_cmd("bill:prediction-clob-microstructure-audit"), False),
        ("replay-event-lag", npm_cmd("bill:prediction-event-lag-replay"), False),
        ("sensitivity-event-lag", npm_cmd("bill:prediction-event-lag-sensitivity"), False),
        ("review-event-lag-watch", npm_cmd("bill:prediction-event-lag-watch-review"), False),
        ("refresh-capture-targets-after-replay", npm_cmd("bill:prediction-event-clob-capture-targets"), False),
        ("refresh-label-gap-plan", npm_cmd("bill:prediction-event-label-gap-plan"), False),
        ("refresh-alpha-frontier", npm_cmd("bill:alpha-frontier-queue"), False),
        ("refresh-next-research-actions", npm_cmd("bill:next-research-actions"), False),
        ("refresh-clearance-evidence", npm_cmd("bill:clearance-evidence"), False),
        ("refresh-clearance-handoff", npm_cmd("bill:clearance-handoff"), False),
        ("sync-obsidian-memory", npm_cmd("bill:obsidian-sync"), False),
    ]
    return [
        {
            "id": step_id,
            "argv": argv,
            "command": command_text(argv) if argv else "",
            "publicMarketDataOnly": step_id == "record-public-clob",
            "network": bool(is_network),
            "writesOrders": False,
            "touchesBroker": False,
        }
        for step_id, argv, is_network in raw_steps
    ]


def safe_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
        "RH_TOPSTEP_READ_ONLY": "true",
        "RH_LIVE_EXECUTION_ENABLED": "false",
    })
    return env


def run_step(step: dict[str, Any], *, timeout_sec: int) -> dict[str, Any]:
    argv = step.get("argv") if isinstance(step.get("argv"), list) else []
    if not argv:
        return {**step, "status": "skipped", "reason": "empty-command"}
    try:
        proc = subprocess.run(
            [str(part) for part in argv],
            cwd=str(ROOT),
            env=safe_env(),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **step,
            "status": "timeout",
            "returnCode": None,
            "stdoutTail": compact_output(exc.stdout or ""),
            "stderrTail": compact_output(exc.stderr or ""),
        }
    return {
        **step,
        "status": "pass" if proc.returncode == 0 else "fail",
        "returnCode": proc.returncode,
        "stdoutTail": compact_output(proc.stdout),
        "stderrTail": compact_output(proc.stderr),
    }


def executed_recorder_summary(steps: list[dict[str, Any]] | None) -> dict[str, Any]:
    record_step = next(
        (step for step in (steps or []) if isinstance(step, dict) and step.get("id") == "record-public-clob"),
        {},
    )
    argv = [str(part) for part in record_step.get("argv", [])] if isinstance(record_step.get("argv"), list) else []
    token_ids: list[str] = []
    terms = ""
    max_assets = None
    for index, part in enumerate(argv):
        if part == "--token-id" and index + 1 < len(argv):
            token_ids.append(argv[index + 1])
        elif part == "--terms" and index + 1 < len(argv):
            terms = argv[index + 1]
        elif part == "--max-assets" and index + 1 < len(argv):
            try:
                max_assets = int(argv[index + 1])
            except ValueError:
                max_assets = argv[index + 1]
    if token_ids:
        mode = "token-targets"
    elif terms:
        mode = "standing-terms"
    elif record_step:
        mode = "no-targets"
    else:
        mode = "not-run"
    return {
        "present": bool(record_step),
        "status": record_step.get("status"),
        "command": record_step.get("command"),
        "mode": mode,
        "tokenIds": token_ids,
        "terms": terms,
        "maxAssets": max_assets,
        "publicMarketDataOnly": bool(record_step.get("publicMarketDataOnly")),
        "writesOrders": bool(record_step.get("writesOrders")),
        "touchesBroker": bool(record_step.get("touchesBroker")),
    }


def timeout_for_step(step: dict[str, Any], duration_sec: int) -> int:
    return duration_sec + 90 if step.get("id") == "record-public-clob" else 180


def build_cycle(
    *,
    capture_targets: dict[str, Any],
    event_news: dict[str, Any] | None = None,
    event_market_mapping: dict[str, Any] | None = None,
    event_timestamp_dataset: dict[str, Any] | None = None,
    event_lag_requirements: dict[str, Any] | None = None,
    event_lag_replay: dict[str, Any],
    event_lag_sensitivity: dict[str, Any] | None = None,
    event_lag_watch_review: dict[str, Any] | None = None,
    recorder_latest: dict[str, Any],
    clob_microstructure: dict[str, Any],
    duration_sec: int | None = None,
    max_assets: int | None = None,
    max_output_mb: int = DEFAULT_MAX_OUTPUT_MB,
    min_free_gb: int = DEFAULT_MIN_FREE_GB,
    run_recorder: bool = False,
    ran_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    event_news = event_news or {}
    event_market_mapping = event_market_mapping or {}
    event_timestamp_dataset = event_timestamp_dataset or {}
    event_lag_requirements = event_lag_requirements or {}
    event_lag_sensitivity = event_lag_sensitivity or {}
    event_lag_watch_review = event_lag_watch_review or {}
    duration = int(duration_sec or capture_targets.get("durationSec") or 900)
    tokens = token_targets(capture_targets, max_assets=max_assets)
    review_lead_tokens = [] if tokens else review_lead_token_targets(capture_targets, max_assets=max_assets)
    recorder_tokens = tokens or review_lead_tokens
    terms = standing_terms(capture_targets)
    terms_max_assets = standing_max_assets(capture_targets, max_assets=max_assets)
    steps = planned_steps(
        recorder_tokens,
        duration_sec=duration,
        terms=terms,
        max_assets=terms_max_assets,
        max_output_mb=max_output_mb,
        min_free_gb=min_free_gb,
    )
    blockers: list[str] = []
    if not tokens and not terms:
        blockers.append("no-event-clob-capture-targets")
    if capture_targets.get("decision") not in {
        "research-only-capture-targets-ready",
        "research-only-forward-capture-required",
        "research-only-forward-capture-review-leads-ready",
    }:
        blockers.append("capture-targets-not-ready")
    if not event_news:
        blockers.append("event-news-rss-missing")
    if (
        event_market_mapping.get("decision") != "research-only-event-market-mapping-candidates-ready"
        and capture_targets.get("mappingRefinementReadyForForwardCapture") is not True
    ):
        blockers.append("event-market-mapping-not-ready")
    if event_lag_requirements.get("decision") not in {
        "research-only-event-lag-requirements-cleared",
        "research-only-event-lag-requirements-not-cleared",
    }:
        blockers.append("event-lag-requirements-missing")
    event_lag_replay_blockers = (
        event_lag_replay.get("blockers")
        if isinstance(event_lag_replay.get("blockers"), list)
        else []
    )
    event_lag_replay_missing = (
        event_lag_replay.get("missingReasonCounts")
        if isinstance(event_lag_replay.get("missingReasonCounts"), dict)
        else {}
    )
    event_lag_replay_by_horizon = (
        event_lag_replay.get("byHorizon")
        if isinstance(event_lag_replay.get("byHorizon"), dict)
        else {}
    )
    if event_lag_replay.get("decision") != "research-only-event-lag-replay-watch":
        blockers.append("event-lag-replay-not-watch-ready")
    event_lag_sensitivity_blockers = (
        event_lag_sensitivity.get("blockers")
        if isinstance(event_lag_sensitivity.get("blockers"), list)
        else []
    )
    event_lag_sensitivity_watch_ready = (
        bool(event_lag_sensitivity.get("watchReady"))
        or event_lag_sensitivity.get("decision") == "research-only-event-lag-sensitivity-watch"
    )
    event_lag_watch_review_visible = (
        event_lag_watch_review.get("decision") == "research-only-event-lag-watch-review-visible"
    )
    event_lag_watch_review_ready = (
        bool(event_lag_watch_review.get("watchReady"))
        or event_lag_watch_review_visible
    )
    recorder_evidence_present = (
        recorder_latest.get("status") == "ok"
        and int(recorder_latest.get("messages") or recorder_latest.get("messageCount") or 0) > 0
    )
    if not run_recorder and not recorder_evidence_present:
        blockers.append("dry-run-only; pass --run-recorder to collect public CLOB data")
    failed_steps = [
        str(step.get("id"))
        for step in (ran_steps or [])
        if step.get("status") in {"fail", "timeout"}
    ]
    if failed_steps:
        blockers.append("cycle-step-failed")
    recorder_live_quality = (
        recorder_latest.get("liveQualityDiagnostics")
        if isinstance(recorder_latest.get("liveQualityDiagnostics"), dict)
        else {}
    )
    if (
        run_recorder
        and recorder_live_quality
        and int(recorder_live_quality.get("selectedAssetCount") or 0) > 0
        and int(recorder_live_quality.get("fillableLiveBookCount") or 0) <= 0
    ):
        blockers.append("recorder-live-quality-not-fillable")
    event_lag_replay_watch_ready = event_lag_replay.get("decision") == "research-only-event-lag-replay-watch"
    capture_cycle_evidence_passed = bool(run_recorder and recorder_tokens and not blockers)
    paper_promotion_blockers = [
        "paper-review-requires-separate-human-and-model-evidence-gate",
        "paper-review-requires-positive-fillability-and-spread-adjusted-replay",
        "paper-review-requires-no-lookahead-event-windows-with-resolved-outcome-labels",
    ]
    if recorder_live_quality and int(recorder_live_quality.get("fillableLiveBookCount") or 0) <= 0:
        paper_promotion_blockers.append("paper-review-requires-fillable-live-books")
    selected_assets = recorder_latest.get("selectedAssets")
    selected_asset_count = (
        len(selected_assets)
        if isinstance(selected_assets, list)
        else selected_assets
        if isinstance(selected_assets, int)
        else None
    )
    token_specific_candidate_count = int(capture_targets.get("tokenSpecificCandidateCount") or 0)
    excluded_mapping_candidate_count = int(capture_targets.get("excludedMappingCandidateCount") or 0)
    excluded_mapping_reason_counts = (
        capture_targets.get("excludedMappingReasonCounts")
        if isinstance(capture_targets.get("excludedMappingReasonCounts"), dict)
        else {}
    )
    forward_required = bool(
        capture_targets.get("decision") in {
            "research-only-forward-capture-required",
            "research-only-forward-capture-review-leads-ready",
        }
        or event_timestamp_dataset.get("forwardCaptureRequired")
        or token_specific_candidate_count
        or excluded_mapping_candidate_count
    )
    if tokens:
        capture_mode = "token-targets"
    elif review_lead_tokens:
        capture_mode = "review-lead-token"
    else:
        capture_mode = "standing-terms"
    executed_recorder = executed_recorder_summary(ran_steps)

    return {
        "command": "prediction-event-capture-cycle",
        "generatedAt": now_iso(),
        "mode": "run-recorder" if run_recorder else "dry-run",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "eventLagReplayWatchReady": event_lag_replay_watch_ready,
        "eventLagResearchWatchReady": bool(event_lag_sensitivity_watch_ready or event_lag_watch_review_ready),
        "captureCycleEvidencePassed": capture_cycle_evidence_passed,
        "paperPromotionEvidencePassed": False,
        "paperPromotionBlockers": paper_promotion_blockers,
        "readyForPaper": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "safeEnv": {
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
            "RH_TOPSTEP_READ_ONLY": "true",
            "RH_LIVE_EXECUTION_ENABLED": "false",
        },
        "targetCount": len(tokens),
        "reviewLeadTargetCount": len(review_lead_tokens),
        "targetDecision": capture_targets.get("decision"),
        "tokenSpecificCandidates": token_specific_candidate_count,
        "excludedMappingCandidates": excluded_mapping_candidate_count,
        "excludedReasons": excluded_mapping_reason_counts,
        "forwardRequired": forward_required,
        "tokenSpecificCandidateCount": token_specific_candidate_count,
        "excludedMappingCandidateCount": excluded_mapping_candidate_count,
        "excludedMappingReasonCounts": excluded_mapping_reason_counts,
        "mappingBlockers": (
            capture_targets.get("mappingBlockers")
            if isinstance(capture_targets.get("mappingBlockers"), list)
            else []
        ),
        "tokens": recorder_tokens,
        "captureMode": capture_mode,
        "executedRecorder": executed_recorder,
        "executedCaptureMode": executed_recorder.get("mode") if executed_recorder.get("present") else capture_mode,
        "standingTerms": terms if not recorder_tokens else "",
        "standingMaxAssets": terms_max_assets if not recorder_tokens else 0,
        "durationSec": duration,
        "maxOutputMb": max_output_mb,
        "minFreeGb": min_free_gb,
        "captureTargetsDecision": capture_targets.get("decision"),
        "coverageStatusCounts": capture_targets.get("coverageStatusCounts") if isinstance(capture_targets.get("coverageStatusCounts"), dict) else {},
        "staleContextTargetCount": capture_targets.get("staleContextTargetCount"),
        "eventNews": {
            "present": bool(event_news),
            "decision": event_news.get("decision"),
            "itemCount": event_news.get("itemCount") or event_news.get("articleCount") or event_news.get("newsCount"),
            "generatedAt": event_news.get("generatedAt"),
        },
        "eventMarketMapping": {
            "present": bool(event_market_mapping),
            "decision": event_market_mapping.get("decision"),
            "candidateCount": event_market_mapping.get("candidateCount"),
            "generatedAt": event_market_mapping.get("generatedAt"),
        },
        "eventTimestampDataset": {
            "present": bool(event_timestamp_dataset),
            "decision": event_timestamp_dataset.get("decision"),
            "candidateCount": event_timestamp_dataset.get("candidateCount"),
            "coverageStatusCounts": (
                event_timestamp_dataset.get("coverageStatusCounts")
                if isinstance(event_timestamp_dataset.get("coverageStatusCounts"), dict)
                else {}
            ),
            "completeWindowTargetCount": event_timestamp_dataset.get("completeWindowTargetCount"),
            "unrecoverablePreEventTargetCount": event_timestamp_dataset.get("unrecoverablePreEventTargetCount"),
            "forwardCaptureRequired": event_timestamp_dataset.get("forwardCaptureRequired"),
            "readyForPaper": event_timestamp_dataset.get("readyForPaper"),
            "generatedAt": event_timestamp_dataset.get("generatedAt"),
        },
        "eventLagRequirements": {
            "present": bool(event_lag_requirements),
            "decision": event_lag_requirements.get("decision"),
            "blockedCount": event_lag_requirements.get("blockedCount"),
            "passCount": event_lag_requirements.get("passCount"),
            "generatedAt": event_lag_requirements.get("generatedAt"),
        },
        "eventLagReplay": event_lag_replay.get("decision"),
        "eventLagReplayDecision": event_lag_replay.get("decision"),
        "eventLagReplayBlockers": event_lag_replay_blockers,
        "replayMissing": event_lag_replay_missing,
        "eventLagReplayMissingReasonCounts": event_lag_replay_missing,
        "eventLagReplayByHorizon": event_lag_replay_by_horizon,
        "eventLagSensitivity": {
            "present": bool(event_lag_sensitivity),
            "decision": event_lag_sensitivity.get("decision"),
            "watchReady": event_lag_sensitivity_watch_ready,
            "bestCompleteWindowCount": event_lag_sensitivity.get("bestCompleteWindowCount"),
            "bestRepricedWindowCount": event_lag_sensitivity.get("bestRepricedWindowCount"),
            "watchScenarioCount": event_lag_sensitivity.get("watchScenarioCount"),
            "blockers": event_lag_sensitivity_blockers,
            "readyForPaper": event_lag_sensitivity.get("readyForPaper", False),
            "readyForExecution": event_lag_sensitivity.get("readyForExecution", False),
        },
        "eventLagWatchReview": {
            "present": bool(event_lag_watch_review),
            "decision": event_lag_watch_review.get("decision"),
            "visible": event_lag_watch_review_visible,
            "watchReady": event_lag_watch_review_ready,
            "watchScenarioCount": event_lag_watch_review.get("watchScenarioCount"),
            "repricedWatchWindowCount": event_lag_watch_review.get("repricedWatchWindowCount"),
            "blockers": (
                event_lag_watch_review.get("blockers")
                if isinstance(event_lag_watch_review.get("blockers"), list)
                else []
            ),
            "readyForPaper": event_lag_watch_review.get("readyForPaper", False),
            "readyForExecution": event_lag_watch_review.get("readyForExecution", False),
        },
        "completeEvents": event_lag_replay.get("completeEventCount"),
        "completeWindows": event_lag_replay.get("completeWindowCount"),
        "repricedWindows": event_lag_replay.get("repricedWindowCount"),
        "completeEventCount": event_lag_replay.get("completeEventCount"),
        "completeWindowCount": event_lag_replay.get("completeWindowCount"),
        "repricedWindowCount": event_lag_replay.get("repricedWindowCount"),
        "latestRecorder": {
            "present": bool(recorder_latest),
            "evidencePresent": recorder_evidence_present,
            "status": recorder_latest.get("status"),
            "messages": recorder_latest.get("messages"),
            "selectedAssetCount": selected_asset_count,
            "selectedAssets": selected_assets if isinstance(selected_assets, list) else [],
            "selectionDiagnostics": (
                recorder_latest.get("selectionDiagnostics")
                if isinstance(recorder_latest.get("selectionDiagnostics"), dict)
                else {}
            ),
            "liveQualityDiagnostics": recorder_live_quality,
            "writesOrders": recorder_latest.get("writesOrders", False),
        },
        "clobMicrostructure": {
            "present": bool(clob_microstructure),
            "decision": clob_microstructure.get("decision"),
            "readyFeatureCount": clob_microstructure.get("readyFeatureCount"),
            "recordsRead": (
                (clob_microstructure.get("capture") or {}).get("recordsRead")
                if isinstance(clob_microstructure.get("capture"), dict)
                else None
            ),
        },
        "steps": ran_steps if ran_steps is not None else [
            {**step, "status": "planned" if step["id"] != "record-public-clob" or run_recorder else "skipped-dry-run"}
            for step in steps
        ],
        "failedStepIds": failed_steps,
        "blockers": blockers,
        "decision": (
            "research-only-capture-cycle-blocked"
            if not recorder_tokens
            else "research-only-capture-cycle-ran"
            if run_recorder and not blockers
            else "research-only-capture-cycle-ran-still-blocked"
            if run_recorder
            else "research-only-capture-cycle-dry-run-ready"
        ),
        "limitations": [
        "Future capture cannot create pre-event quotes for news that already happened.",
            "Fresh news/mapping refresh improves future-window chances but does not guarantee relevant news arrives during capture.",
            "This cycle uses public prediction-market data only; no funding, order, broker, or route path is called.",
            "Paper review remains blocked until event-lag replay has complete no-lookahead windows and positive post-spread evidence.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Event Capture Cycle - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only loop for news/event lag capture in prediction markets. This page does not approve paper, demo, live, funding, or orders.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Mode: `{payload.get('mode')}`",
        f"- Target count: `{payload.get('targetCount')}`",
        f"- Event news present: `{payload.get('eventNews', {}).get('present')}`",
        f"- Event mapping: `{payload.get('eventMarketMapping', {}).get('decision')}` candidates `{payload.get('eventMarketMapping', {}).get('candidateCount')}`",
        f"- Event timestamp dataset: `{payload.get('eventTimestampDataset', {}).get('decision')}` coverage `{payload.get('eventTimestampDataset', {}).get('coverageStatusCounts')}`",
        f"- Event-lag replay: `{payload.get('eventLagReplayDecision')}`",
        f"- Event-lag replay blockers: `{payload.get('eventLagReplayBlockers')}`",
        f"- Event-lag research watch ready: `{payload.get('eventLagResearchWatchReady')}`",
        f"- Event-lag sensitivity: `{payload.get('eventLagSensitivity', {}).get('decision')}` watch scenarios `{payload.get('eventLagSensitivity', {}).get('watchScenarioCount')}` best repriced `{payload.get('eventLagSensitivity', {}).get('bestRepricedWindowCount')}`",
        f"- Event-lag watch review: `{payload.get('eventLagWatchReview', {}).get('decision')}` watch ready `{payload.get('eventLagWatchReview', {}).get('watchReady')}` repriced watch windows `{payload.get('eventLagWatchReview', {}).get('repricedWatchWindowCount')}`",
        f"- Complete events: `{payload.get('completeEventCount')}`",
        f"- Complete windows: `{payload.get('completeWindowCount')}`",
        f"- Repriced windows: `{payload.get('repricedWindowCount')}`",
        f"- Replay missing reasons: `{payload.get('eventLagReplayMissingReasonCounts')}`",
        f"- Executed recorder: mode `{payload.get('executedCaptureMode')}` tokenIds `{payload.get('executedRecorder', {}).get('tokenIds', [])}`",
        f"- Recorder live fillable books: `{payload.get('latestRecorder', {}).get('liveQualityDiagnostics', {}).get('fillableLiveBookCount', 'missing')}` / `{payload.get('latestRecorder', {}).get('liveQualityDiagnostics', {}).get('selectedAssetCount', 'missing')}`",
        f"- Ready for paper: `{payload.get('readyForPaper')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        "",
        "## Steps",
        "",
    ]
    for step in payload.get("steps") or []:
        lines.append(f"- `{step.get('id')}`: `{step.get('status')}`")
        if step.get("command"):
            lines.append(f"  - `{step.get('command')}`")
    lines.extend(["", "## Blockers", ""])
    for blocker in payload.get("blockers") or ["none"]:
        lines.append(f"- {blocker}")
    lines.extend(["", "## Limitations", ""])
    for item in payload.get("limitations") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or run the prediction event CLOB capture cycle.")
    parser.add_argument("--capture-targets", default=str(CAPTURE_TARGETS))
    parser.add_argument("--event-news", default=str(EVENT_NEWS_RSS))
    parser.add_argument("--event-market-mapping", default=str(EVENT_MARKET_MAPPING))
    parser.add_argument("--event-timestamp-dataset", default=str(EVENT_TIMESTAMP_DATASET))
    parser.add_argument("--event-lag-requirements", default=str(EVENT_LAG_REQUIREMENTS))
    parser.add_argument("--event-lag-replay", default=str(EVENT_LAG_REPLAY))
    parser.add_argument("--event-lag-sensitivity", default=str(EVENT_LAG_SENSITIVITY))
    parser.add_argument("--event-lag-watch-review", default=str(EVENT_LAG_WATCH_REVIEW))
    parser.add_argument("--recorder-latest", default=str(RECORDER_LATEST))
    parser.add_argument("--clob-microstructure", default=str(CLOB_MICROSTRUCTURE))
    parser.add_argument("--duration-sec", type=int, default=None)
    parser.add_argument("--max-assets", type=int, default=None)
    parser.add_argument("--max-output-mb", type=int, default=DEFAULT_MAX_OUTPUT_MB)
    parser.add_argument("--min-free-gb", type=int, default=DEFAULT_MIN_FREE_GB)
    parser.add_argument("--run-recorder", action="store_true")
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(default_markdown_path()))
    args = parser.parse_args()

    capture_targets = read_json(Path(args.capture_targets))
    event_news = read_json(Path(args.event_news))
    event_market_mapping = read_json(Path(args.event_market_mapping))
    event_timestamp_dataset = read_json(Path(args.event_timestamp_dataset))
    event_lag_requirements = read_json(Path(args.event_lag_requirements))
    event_lag_replay = read_json(Path(args.event_lag_replay))
    event_lag_sensitivity = read_json(Path(args.event_lag_sensitivity))
    event_lag_watch_review = read_json(Path(args.event_lag_watch_review))
    recorder_latest = read_json(Path(args.recorder_latest))
    clob_microstructure = read_json(Path(args.clob_microstructure))
    initial = build_cycle(
        capture_targets=capture_targets,
        event_news=event_news,
        event_market_mapping=event_market_mapping,
        event_timestamp_dataset=event_timestamp_dataset,
        event_lag_requirements=event_lag_requirements,
        event_lag_replay=event_lag_replay,
        event_lag_sensitivity=event_lag_sensitivity,
        event_lag_watch_review=event_lag_watch_review,
        recorder_latest=recorder_latest,
        clob_microstructure=clob_microstructure,
        duration_sec=args.duration_sec,
        max_assets=args.max_assets,
        max_output_mb=args.max_output_mb,
        min_free_gb=args.min_free_gb,
        run_recorder=args.run_recorder,
    )

    ran_steps: list[dict[str, Any]] | None = None
    if args.run_recorder:
        duration = int(initial["durationSec"])
        ran_steps = []
        pre_refresh_ids = {
            "refresh-news-before-capture",
            "refresh-mapping-before-capture",
            "refresh-timestamps-before-capture",
            "refresh-requirements-before-capture",
            "refresh-capture-targets",
        }
        for step in initial["steps"]:
            if step["id"] in pre_refresh_ids:
                ran_steps.append(run_step(step, timeout_sec=timeout_for_step(step, duration)))

        capture_targets = read_json(Path(args.capture_targets))
        event_news = read_json(Path(args.event_news))
        event_market_mapping = read_json(Path(args.event_market_mapping))
        event_timestamp_dataset = read_json(Path(args.event_timestamp_dataset))
        event_lag_requirements = read_json(Path(args.event_lag_requirements))
        refreshed_tokens = token_targets(capture_targets, max_assets=args.max_assets)
        refreshed_review_lead_tokens = (
            [] if refreshed_tokens else review_lead_token_targets(capture_targets, max_assets=args.max_assets)
        )
        refreshed_recorder_tokens = refreshed_tokens or refreshed_review_lead_tokens
        refreshed_terms = standing_terms(capture_targets)
        refreshed_terms_max_assets = standing_max_assets(capture_targets, max_assets=args.max_assets)
        refreshed_steps = planned_steps(
            refreshed_recorder_tokens,
            duration_sec=duration,
            terms=refreshed_terms,
            max_assets=refreshed_terms_max_assets,
            max_output_mb=args.max_output_mb,
            min_free_gb=args.min_free_gb,
        )
        completed_pre_ids = {str(step.get("id")) for step in ran_steps}
        for step in refreshed_steps:
            if step["id"] in completed_pre_ids:
                continue
            if step["id"] == "record-public-clob" and not refreshed_recorder_tokens and not refreshed_terms:
                ran_steps.append({**step, "status": "skipped", "reason": "no-event-clob-capture-targets"})
                continue
            ran_steps.append(run_step(step, timeout_sec=timeout_for_step(step, duration)))

        recorder_latest = read_json(Path(args.recorder_latest))
        event_news = read_json(Path(args.event_news))
        event_market_mapping = read_json(Path(args.event_market_mapping))
        event_timestamp_dataset = read_json(Path(args.event_timestamp_dataset))
        event_lag_requirements = read_json(Path(args.event_lag_requirements))
        event_lag_replay = read_json(Path(args.event_lag_replay))
        event_lag_sensitivity = read_json(Path(args.event_lag_sensitivity))
        event_lag_watch_review = read_json(Path(args.event_lag_watch_review))
        capture_targets = read_json(Path(args.capture_targets))
        clob_microstructure = read_json(Path(args.clob_microstructure))

    payload = build_cycle(
        capture_targets=capture_targets,
        event_news=event_news,
        event_market_mapping=event_market_mapping,
        event_timestamp_dataset=event_timestamp_dataset,
        event_lag_requirements=event_lag_requirements,
        event_lag_replay=event_lag_replay,
        event_lag_sensitivity=event_lag_sensitivity,
        event_lag_watch_review=event_lag_watch_review,
        recorder_latest=recorder_latest,
        clob_microstructure=clob_microstructure,
        duration_sec=args.duration_sec,
        max_assets=args.max_assets,
        max_output_mb=args.max_output_mb,
        min_free_gb=args.min_free_gb,
        run_recorder=args.run_recorder,
        ran_steps=ran_steps,
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
