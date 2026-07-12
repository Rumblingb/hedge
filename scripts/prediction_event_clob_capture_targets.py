#!/usr/bin/env python3
"""Build targeted Polymarket CLOB capture commands for event-lag research.

Research-only. The event-lag replay can fail because captured CLOB data does
not overlap mapped event windows. This script turns those gaps into explicit
public-market recorder targets. It never touches keys, orders, funding, or
broker state.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prediction_event_lag_replay import clob_paths_from_glob

STATE = ROOT / ".rumbling-hedge" / "state"
CLOB_DIR = ROOT / ".rumbling-hedge" / "prediction" / "clob"
MAPPING_PLAN = STATE / "prediction-event-market-mapping-plan.latest.json"
MAPPING_REFINEMENT = STATE / "prediction-event-mapping-refinement.latest.json"
REPLAY = STATE / "prediction-event-lag-replay.latest.json"
OUT = STATE / "prediction-event-clob-capture-targets.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
STANDING_TERMS = "fed,rate,cpi,inflation,iran,ceasefire,war,trump,tariff,bitcoin,btc,ethereum,eth,nvidia,tesla"
DEFAULT_MAX_OUTPUT_MB = 128
DEFAULT_MIN_FREE_GB = 20


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-event-clob-capture-targets-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
    except FileNotFoundError:
        return []
    return rows


def to_float(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def parse_time_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return int(numeric if numeric > 10_000_000_000 else numeric * 1000)
    text = str(value).strip()
    if not text:
        return None
    numeric = to_float(text)
    if numeric is not None:
        return int(numeric if numeric > 10_000_000_000 else numeric * 1000)
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


def record_ts_ms(record: dict[str, Any]) -> int | None:
    for key in ("localTs", "timestamp", "ts", "exchangeTs"):
        ts = parse_time_ms(record.get(key))
        if ts is not None:
            return ts
    return None


def record_asset_ids(record: dict[str, Any]) -> list[str]:
    event = str(record.get("eventType") or record.get("event_type") or "")
    if event == "price_change":
        out = []
        for change in record.get("priceChanges") or []:
            if isinstance(change, dict) and (change.get("asset_id") or change.get("assetId")):
                out.append(str(change.get("asset_id") or change.get("assetId")))
        return out
    asset = record.get("assetId") or record.get("asset_id")
    return [str(asset)] if asset else []


def quote_ranges(paths: list[Path]) -> dict[str, dict[str, int]]:
    ranges: dict[str, dict[str, int]] = {}
    for path in paths:
        for record in read_jsonl(path):
            ts = record_ts_ms(record)
            if ts is None:
                continue
            for asset in record_asset_ids(record):
                current = ranges.setdefault(asset, {"firstTsMs": ts, "lastTsMs": ts, "records": 0})
                current["firstTsMs"] = min(current["firstTsMs"], ts)
                current["lastTsMs"] = max(current["lastTsMs"], ts)
                current["records"] += 1
    return ranges


def quote_timestamp_index(paths: list[Path]) -> dict[str, list[int]]:
    timestamps: dict[str, list[int]] = {}
    for path in paths:
        for record in read_jsonl(path):
            ts = record_ts_ms(record)
            if ts is None:
                continue
            for asset in record_asset_ids(record):
                timestamps.setdefault(asset, []).append(ts)
    for rows in timestamps.values():
        rows.sort()
    return timestamps


def candidate_rows(mapping_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = mapping_plan.get("candidates") if isinstance(mapping_plan.get("candidates"), list) else []
    return [row for row in rows if isinstance(row, dict) and row.get("clobTokenId")]


def mapping_exclusion_reasons(candidate: dict[str, Any]) -> list[str]:
    status = str(candidate.get("mappingStatus") or "")
    flags = [str(flag) for flag in (candidate.get("specificityFlags") or [])] if isinstance(candidate.get("specificityFlags"), list) else []
    reasons: list[str] = []
    if "ambiguous" in status:
        reasons.append("ambiguous-mapping-status")
    if "mismatch" in status:
        reasons.append("event-family-mismatch")
    if "counterparty" in status:
        reasons.append("counterparty-mapping-status")
    if "headline-has-multiple-event-families" in flags:
        reasons.append("headline-has-multiple-event-families")
    if "market-counterparty-not-explicit-in-headline" in flags:
        reasons.append("market-counterparty-not-explicit-in-headline")
    if "event-family-mismatch" in flags:
        reasons.append("event-family-mismatch")
    return list(dict.fromkeys(reasons))


def token_specific_candidate_rows(mapping_plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    usable: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in candidate_rows(mapping_plan):
        reasons = mapping_exclusion_reasons(row)
        if reasons:
            excluded.append({
                "externalId": row.get("externalId"),
                "clobTokenId": row.get("clobTokenId"),
                "headline": row.get("headline"),
                "question": row.get("question"),
                "mappingStatus": row.get("mappingStatus"),
                "specificityFlags": row.get("specificityFlags") if isinstance(row.get("specificityFlags"), list) else [],
                "exclusionReasons": reasons,
            })
        else:
            usable.append(row)
    return usable, excluded


def manual_selected_rows(
    mapping_plan: dict[str, Any],
    mapping_refinement: dict[str, Any],
) -> list[dict[str, Any]]:
    if mapping_refinement.get("readyForForwardCapture") is not True:
        return []
    selected: list[dict[str, Any]] = []
    reviews = mapping_refinement.get("headlineReviews") if isinstance(mapping_refinement.get("headlineReviews"), list) else []
    candidates = candidate_rows(mapping_plan)
    by_external = {str(row.get("externalId")): row for row in candidates if row.get("externalId")}
    by_token = {str(row.get("clobTokenId")): row for row in candidates if row.get("clobTokenId")}
    seen: set[str] = set()
    for review in reviews:
        if not isinstance(review, dict) or review.get("mappingQuality") != "manual-selected-forward-capture-watch":
            continue
        selected_external_id = str(review.get("manualSelectedExternalId") or "")
        selected_token_id = str(review.get("manualSelectedTokenId") or "")
        row = by_external.get(selected_external_id) or by_token.get(selected_token_id)
        if not row:
            specificity_rows = (
                review.get("candidateSpecificityRows")
                if isinstance(review.get("candidateSpecificityRows"), list)
                else []
            )
            row = next(
                (
                    item
                    for item in specificity_rows
                    if isinstance(item, dict)
                    and (
                        str(item.get("externalId") or "") == selected_external_id
                        or str(item.get("clobTokenId") or "") == selected_token_id
                    )
                ),
                {},
            )
        if not row and selected_token_id:
            row = {
                "externalId": selected_external_id,
                "clobTokenId": selected_token_id,
                "question": review.get("manualSelectedQuestion"),
                "headline": review.get("headline"),
                "articleDatetime": review.get("eventIso"),
                "score": 0,
            }
        if not row or not row.get("clobTokenId"):
            continue
        token = str(row["clobTokenId"])
        if token in seen:
            continue
        seen.add(token)
        selected.append({
            **row,
            "mappingStatus": "manual-selected-forward-capture-watch",
            "specificityFlags": [],
            "manualSelected": True,
            "manualSelectedReason": "clean keep-watch manual review selected this market for forward public CLOB capture only",
        })
    return selected


def coverage_status(
    candidate: dict[str, Any],
    ranges: dict[str, dict[str, int]],
    timestamps: dict[str, list[int]],
    *,
    pre_minutes: int,
    post_minutes: int,
) -> tuple[str, dict[str, Any]]:
    token = str(candidate.get("clobTokenId") or "")
    event_ts = parse_time_ms(candidate.get("articleDatetime") or candidate.get("published"))
    asset_range = ranges.get(token)
    if event_ts is None:
        return "invalid-event-timestamp", {}
    if not asset_range:
        return "no-quotes-for-clob-token", {}
    asset_timestamps = timestamps.get(token, [])
    pre_start = event_ts - pre_minutes * 60 * 1000
    post_target = event_ts + post_minutes * 60 * 1000
    has_pre = any(pre_start <= ts <= event_ts for ts in asset_timestamps)
    has_post = any(ts >= post_target for ts in asset_timestamps)
    if not has_pre and not has_post:
        status = "missing-pre-and-post-window"
    elif not has_pre:
        status = "missing-pre-event-window"
    elif not has_post:
        status = "missing-post-event-window"
    else:
        status = "window-range-present"
    return status, asset_range


def event_age_minutes(candidate: dict[str, Any], generated_ms: int) -> float | None:
    event_ts = parse_time_ms(candidate.get("articleDatetime") or candidate.get("published"))
    if event_ts is None:
        return None
    return round((generated_ms - event_ts) / 60_000, 3)


def pre_event_window_recoverable(candidate: dict[str, Any], generated_ms: int, pre_minutes: int) -> bool:
    event_ts = parse_time_ms(candidate.get("articleDatetime") or candidate.get("published"))
    if event_ts is None:
        return False
    return generated_ms <= event_ts - pre_minutes * 60 * 1000


def target_recordable(item: dict[str, Any], post_minutes: int) -> bool:
    status = str(item.get("coverageStatus") or "")
    if status in {"no-quotes-for-clob-token", "missing-pre-and-post-window", "missing-pre-event-window"}:
        return item.get("preEventWindowRecoverable") is True
    if status == "missing-post-event-window":
        age = to_float(item.get("eventAgeMinutes"))
        return age is None or age <= post_minutes
    return False


def build_targets(
    *,
    mapping_plan: dict[str, Any],
    replay: dict[str, Any],
    clob_paths: list[Path],
    mapping_refinement: dict[str, Any] | None = None,
    max_assets: int = 20,
    duration_sec: int = 900,
    pre_minutes: int = 30,
    post_minutes: int = 120,
) -> dict[str, Any]:
    ranges = quote_ranges(clob_paths)
    timestamps = quote_timestamp_index(clob_paths)
    generated_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    latest_by_token: dict[str, dict[str, Any]] = {}
    status_counts: Counter[str] = Counter()
    mapping_refinement = mapping_refinement or {}
    refinement_ready_for_forward_capture = mapping_refinement.get("readyForForwardCapture") is True
    token_candidates, excluded_candidates = token_specific_candidate_rows(mapping_plan)
    selected_rows = manual_selected_rows(mapping_plan, mapping_refinement)
    selected_tokens = {str(row.get("clobTokenId")) for row in selected_rows if row.get("clobTokenId")}
    if selected_rows:
        token_candidates.extend(selected_rows)
        excluded_candidates = [
            row
            for row in excluded_candidates
            if str(row.get("clobTokenId") or "") not in selected_tokens
        ]
    excluded_counts = Counter(
        reason
        for candidate in excluded_candidates
        for reason in (candidate.get("exclusionReasons") or [])
    )
    for candidate in token_candidates:
        token = str(candidate.get("clobTokenId"))
        status, asset_range = coverage_status(candidate, ranges, timestamps, pre_minutes=pre_minutes, post_minutes=post_minutes)
        status_counts[status] += 1
        current = latest_by_token.get(token)
        score = int(candidate.get("score") or 0)
        if current and int(current.get("score") or 0) >= score:
            continue
        latest_by_token[token] = {
            "tokenId": token,
            "externalId": candidate.get("externalId"),
            "question": candidate.get("question"),
            "headline": candidate.get("headline"),
            "source": candidate.get("source"),
            "articleDatetime": candidate.get("articleDatetime"),
            "published": candidate.get("published"),
            "price": candidate.get("price"),
            "bestBid": candidate.get("bestBid"),
            "bestAsk": candidate.get("bestAsk"),
            "spreadPct": candidate.get("spreadPct"),
            "topBookDepth": candidate.get("topBookDepth"),
            "score": score,
            "coverageStatus": status,
            "existingQuoteRange": asset_range,
            "eventAgeMinutes": event_age_minutes(candidate, generated_ms),
            "preEventWindowRecoverable": pre_event_window_recoverable(candidate, generated_ms, pre_minutes),
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        }
    priority = {
        "no-quotes-for-clob-token": 0,
        "missing-pre-and-post-window": 1,
        "missing-pre-event-window": 2,
        "missing-post-event-window": 3,
        "invalid-event-timestamp": 4,
        "window-range-present": 5,
    }
    all_targets = sorted(
        latest_by_token.values(),
        key=lambda item: (
            priority.get(str(item.get("coverageStatus")), 99),
            item.get("preEventWindowRecoverable") is False,
            -float(item.get("topBookDepth") or 0),
            -int(item.get("score") or 0),
            str(item.get("tokenId")),
        ),
    )
    recordable_targets = [item for item in all_targets if target_recordable(item, post_minutes)]
    stale_context_targets = [item for item in all_targets if not target_recordable(item, post_minutes)]
    complete_window_target_count = sum(1 for item in all_targets if item.get("coverageStatus") == "window-range-present")
    targets = recordable_targets[:max_assets]
    token_args = " ".join(f"--token-id '{item['tokenId']}'" for item in targets)
    review_leads = (
        mapping_refinement.get("publicCaptureReviewLeads")
        if isinstance(mapping_refinement.get("publicCaptureReviewLeads"), list)
        else []
    )
    deadline_ladder_leads = (
        mapping_refinement.get("deadlineLadderCaptureCandidates")
        if isinstance(mapping_refinement.get("deadlineLadderCaptureCandidates"), list)
        else []
    )
    review_lead_tokens: list[str] = []
    review_lead_rows: list[dict[str, Any]] = []
    active_review_leads = deadline_ladder_leads if deadline_ladder_leads and not refinement_ready_for_forward_capture else [*review_leads, *deadline_ladder_leads]
    for lead in active_review_leads:
        if not isinstance(lead, dict) or not lead.get("tokenId"):
            continue
        token = str(lead["tokenId"])
        if token in review_lead_tokens:
            continue
        review_lead_tokens.append(token)
        review_lead_rows.append({
            "tokenId": token,
            "question": lead.get("question"),
            "counterparty": lead.get("counterparty"),
            "deadlineText": lead.get("deadlineText"),
            "status": lead.get("status"),
            "bestBid": lead.get("bestBid"),
            "bestAsk": lead.get("bestAsk"),
            "spread": lead.get("spread"),
            "reviewUseOnly": lead.get("reviewUseOnly"),
            "leadType": "deadline-ladder-forward-capture" if lead in deadline_ladder_leads else "public-capture-review-lead",
        })
    if not review_lead_rows and selected_rows:
        for row in selected_rows:
            token = str(row.get("clobTokenId") or "")
            if not token or token in review_lead_tokens:
                continue
            review_lead_tokens.append(token)
            review_lead_rows.append({
                "tokenId": token,
                "externalId": row.get("externalId"),
                "question": row.get("question"),
                "counterparty": "/".join(sorted(str(actor) for actor in (row.get("marketActors") or []))) if isinstance(row.get("marketActors"), list) else None,
                "deadlineText": None,
                "status": "manual-selected-forward-capture-watch",
                "bestBid": row.get("bestBid"),
                "bestAsk": row.get("bestAsk"),
                "spread": row.get("spreadPct"),
                "reviewUseOnly": "manual-selected public-capture lead; not a mapping override, signal, paper approval, or execution approval",
            })
    review_lead_token_args = " ".join(f"--token-id '{token}'" for token in review_lead_tokens[:max_assets])
    standing_terms = STANDING_TERMS
    standing_recorder_command = (
        "npm run --silent bill:polymarket-clob-recorder -- "
        f"--duration-sec {duration_sec} --max-assets {max_assets} "
        f"--max-output-mb {DEFAULT_MAX_OUTPUT_MB} --min-free-gb {DEFAULT_MIN_FREE_GB} "
        f"--terms '{standing_terms}'"
    )
    recorder_command = (
        (
            "npm run --silent bill:polymarket-clob-recorder -- "
            f"--duration-sec {duration_sec} --max-assets {len(targets)} "
            f"--max-output-mb {DEFAULT_MAX_OUTPUT_MB} --min-free-gb {DEFAULT_MIN_FREE_GB} {token_args}"
        ).strip()
        if targets
        else standing_recorder_command
    )
    review_lead_recorder_command = (
        (
            "npm run --silent bill:polymarket-clob-recorder -- "
            f"--duration-sec {duration_sec} --max-assets {len(review_lead_tokens[:max_assets])} "
            f"--max-output-mb {DEFAULT_MAX_OUTPUT_MB} --min-free-gb {DEFAULT_MIN_FREE_GB} {review_lead_token_args}"
        ).strip()
        if review_lead_tokens
        else None
    )
    replay_command = "npm run --silent bill:prediction-event-lag-replay"
    blockers = []
    mapping_blockers = [str(item) for item in mapping_plan.get("blockers", [])] if isinstance(mapping_plan.get("blockers"), list) else []
    if mapping_blockers and not refinement_ready_for_forward_capture:
        blockers.append("event-market-mapping-not-token-specific")
    if excluded_candidates and not refinement_ready_for_forward_capture:
        blockers.append("ambiguous-mapping-candidates-excluded-from-token-capture")
    if replay.get("decision") != "research-only-event-lag-replay-watch":
        blockers.append("event-lag-replay-not-watch-ready")
    unrecoverable_pre_event_targets = [
        item for item in stale_context_targets
        if item.get("coverageStatus") in {"missing-pre-event-window", "missing-pre-and-post-window", "no-quotes-for-clob-token"}
        and item.get("preEventWindowRecoverable") is False
    ]
    if unrecoverable_pre_event_targets:
        blockers.append("past-event-pre-window-unrecoverable-use-forward-capture")
    return {
        "command": "prediction-event-clob-capture-targets",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "mappingDecision": mapping_plan.get("decision"),
        "mappingBlockers": mapping_blockers,
        "mappingRefinementDecision": mapping_refinement.get("decision"),
        "mappingRefinementReadyForForwardCapture": refinement_ready_for_forward_capture,
        "replayDecision": replay.get("decision"),
        "sourceClobPaths": [str(path) for path in clob_paths],
        "existingAssetQuoteCount": sum(item.get("records", 0) for item in ranges.values()),
        "existingAssetsWithQuotes": len(ranges),
        "candidateCount": len(candidate_rows(mapping_plan)),
        "tokenSpecificCandidateCount": len(token_candidates),
        "manualSelectedForwardCaptureCount": len(selected_rows),
        "excludedMappingCandidateCount": len(excluded_candidates),
        "excludedMappingReasonCounts": dict(excluded_counts),
        "excludedMappingCandidates": excluded_candidates[:max_assets],
        "publicCaptureReviewLeadCount": len(review_lead_rows),
        "publicCaptureReviewLeads": review_lead_rows[:max_assets],
        "deadlineLadderCaptureCandidateCount": len([lead for lead in deadline_ladder_leads if isinstance(lead, dict) and lead.get("tokenId")]),
        "targetCount": len(targets),
        "allCandidateTargetCount": len(all_targets),
        "staleContextTargetCount": len(stale_context_targets),
        "completeWindowTargetCount": complete_window_target_count,
        "coverageStatusCounts": dict(status_counts),
        "durationSec": duration_sec,
        "standingTerms": standing_terms,
        "standingMaxAssets": max_assets,
        "maxOutputMb": DEFAULT_MAX_OUTPUT_MB,
        "minFreeGb": DEFAULT_MIN_FREE_GB,
        "preMinutes": pre_minutes,
        "postMinutes": post_minutes,
        "pastEventTargetCount": sum(1 for item in targets if (item.get("eventAgeMinutes") is not None and float(item["eventAgeMinutes"]) > 0)),
        "preEventRecoverableTargetCount": sum(1 for item in targets if item.get("preEventWindowRecoverable") is True),
        "unrecoverablePreEventTargetCount": len(unrecoverable_pre_event_targets),
        "targets": targets,
        "staleContextTargets": stale_context_targets[:max_assets],
        "recorderCommand": recorder_command,
        "standingRecorderCommand": standing_recorder_command,
        "reviewLeadRecorderCommand": review_lead_recorder_command,
        "forwardCapturePlan": {
            "required": refinement_ready_for_forward_capture or bool(mapping_blockers) or bool(excluded_candidates) or bool(unrecoverable_pre_event_targets) or (not targets and complete_window_target_count == 0),
            "reason": (
                "Manual review selected a single watch market; run bounded forward public CLOB capture on the selected token, then replay with no-lookahead windows."
                if refinement_ready_for_forward_capture and review_lead_recorder_command
                else "Mapping remains ambiguous; run bounded forward public CLOB capture on the semantically closest deadline ladder as research-only coverage while mapping stays blocked."
                if deadline_ladder_leads and review_lead_recorder_command
                else "Event-to-market mapping is ambiguous; use standing term capture and improve mapping before token-specific capture."
                if mapping_blockers or excluded_candidates
                else
                "No recoverable token-specific event windows are available; use standing term capture before/through future news."
                if not targets and complete_window_target_count == 0
                else "Mapped headlines are already older than the required pre-event window; current-token recording can only help future replays."
                if unrecoverable_pre_event_targets
                else "Current targets still have recoverable or complete pre-event coverage."
            ),
            "command": standing_recorder_command,
            "reviewLeadCommand": review_lead_recorder_command,
            "followUp": [
                "Run the standing recorder before/through expected news windows.",
                "If a single mapping family/counterparty/deadline is selected, run the review-lead token recorder as bounded forward capture.",
                "Refresh news and event-market mapping after capture.",
                "Replay only with no-lookahead pre-event quotes present.",
            ],
        },
        "followUpCommands": [
            standing_recorder_command,
            review_lead_recorder_command or standing_recorder_command,
            recorder_command,
            "npm run --silent bill:prediction-clob-microstructure-audit",
            replay_command,
            "npm run --silent bill:alpha-frontier-queue",
            "npm run --silent bill:clearance-handoff",
            "npm run --silent bill:obsidian-sync",
        ],
        "blockers": blockers,
        "decision": (
            "research-only-forward-capture-review-leads-ready"
            if refinement_ready_for_forward_capture and review_lead_recorder_command
            else "research-only-capture-targets-ready"
            if targets
            else "research-only-forward-capture-required"
        ),
        "limitations": [
            "Future recording cannot create pre-event quotes for already-past headlines.",
            "A target with an unrecoverable pre-event window is useful for forward monitoring only, not current replay promotion.",
            "Ambiguous event-family or counterparty mappings are excluded from token-specific capture targets.",
            "Review-lead token commands are forward public-data capture helpers only; they do not override mapping ambiguity.",
            "Targets are public market-data subscriptions only; no keys, orders, funding, or broker state are touched.",
            "Recorder output must still be replayed with no-lookahead checks before any paper review.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Event CLOB Capture Targets - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only targeted public CLOB capture plan for mapped event-lag markets.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Replay decision: `{payload.get('replayDecision')}`",
        f"- Recordable target count: `{payload.get('targetCount')}`",
        f"- All candidate target count: `{payload.get('allCandidateTargetCount')}`",
        f"- Token-specific candidate count: `{payload.get('tokenSpecificCandidateCount')}`",
        f"- Excluded mapping candidates: `{payload.get('excludedMappingCandidateCount')}` reasons `{payload.get('excludedMappingReasonCounts')}`",
        f"- Public capture review leads: `{payload.get('publicCaptureReviewLeadCount')}`",
        f"- Stale context target count: `{payload.get('staleContextTargetCount')}`",
        f"- Existing assets with quotes: `{payload.get('existingAssetsWithQuotes')}`",
        f"- Coverage status counts: `{payload.get('coverageStatusCounts')}`",
        f"- Unrecoverable pre-event targets: `{payload.get('unrecoverablePreEventTargetCount')}`",
        f"- Ready for paper: `{payload.get('readyForPaper')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        "",
        "## Recorder Command",
        "",
        "```bash",
        str(payload.get("recorderCommand") or ""),
        "```",
        "",
        "## Forward Capture",
        "",
        f"- Required: `{(payload.get('forwardCapturePlan') or {}).get('required')}`",
        f"- Reason: {(payload.get('forwardCapturePlan') or {}).get('reason')}",
        "",
        "```bash",
        str(payload.get("standingRecorderCommand") or ""),
        "```",
        "",
        "## Review Lead Token Command",
        "",
        "Research-only helper for public CLOB books from the mapping repair queue. This does not approve paper or execution.",
        "",
        "```bash",
        str(payload.get("reviewLeadRecorderCommand") or ""),
        "```",
        "",
        "## Targets",
        "",
    ]
    for item in payload.get("targets") or []:
        lines.extend([
            f"### {item.get('externalId')}",
            "",
            f"- Token: `{item.get('tokenId')}`",
            f"- Coverage: `{item.get('coverageStatus')}`",
            f"- Event age minutes: `{item.get('eventAgeMinutes')}`",
            f"- Pre-event window recoverable: `{item.get('preEventWindowRecoverable')}`",
            f"- Question: {item.get('question')}",
            f"- Headline: {item.get('headline')}",
            f"- Source: {item.get('source')}",
            "",
        ])
    lines.extend(["## Limitations", ""])
    for item in payload.get("limitations") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build prediction event CLOB capture targets.")
    parser.add_argument("--mapping-plan", default=str(MAPPING_PLAN))
    parser.add_argument("--mapping-refinement", default=str(MAPPING_REFINEMENT))
    parser.add_argument("--replay", default=str(REPLAY))
    parser.add_argument("--clob-glob", default=str(CLOB_DIR / "*-market-channel.jsonl"))
    parser.add_argument("--max-assets", type=int, default=20)
    parser.add_argument("--duration-sec", type=int, default=900)
    parser.add_argument("--pre-minutes", type=int, default=30)
    parser.add_argument("--post-minutes", type=int, default=120)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(default_markdown_path()))
    args = parser.parse_args()
    payload = build_targets(
        mapping_plan=read_json(Path(args.mapping_plan)),
        replay=read_json(Path(args.replay)),
        clob_paths=clob_paths_from_glob(args.clob_glob),
        mapping_refinement=read_json(Path(args.mapping_refinement)),
        max_assets=args.max_assets,
        duration_sec=args.duration_sec,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
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
