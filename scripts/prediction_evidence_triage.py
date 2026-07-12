#!/usr/bin/env python3
"""Summarize prediction-market research blockers into a next-test queue.

This is research-only. It reads Bill prediction review/calibration/watchlist
and Polymarket CLOB evidence artifacts, then writes a compact handoff for the
closed-loop researcher. It never writes orders, fills, approvals, or promotion.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
OUT = STATE / "prediction-evidence-triage.latest.json"
PREDICTION_NO_EDGE = ROOT / ".rumbling-hedge/research/prediction-no-edge-ledger/latest.json"
MACRO_RATES_REQUIREMENTS = STATE / "prediction-macro-rates-requirements.latest.json"
MACRO_RATES_REPLAY = STATE / "prediction-macro-rates-cross-source-replay.latest.json"
EVENT_CAPTURE_TARGETS = STATE / "prediction-event-clob-capture-targets.latest.json"
EVENT_CAPTURE_CYCLE = STATE / "prediction-event-capture-cycle.latest.json"
EVENT_TIMESTAMP_DATASET = STATE / "prediction-event-timestamp-dataset.latest.json"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def review_payload(data: dict[str, Any]) -> dict[str, Any]:
    return data.get("review") if isinstance(data.get("review"), dict) else data


def spread_bucket(item: dict[str, Any]) -> str:
    spread = item.get("spread")
    if not isinstance(spread, (int, float)):
        return "unknown"
    if spread <= 0.01:
        return "tight"
    if spread <= 0.03:
        return "usable"
    return "wide"


def watchlist_blockers(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        for blocker in item.get("blockers") or []:
            counts[str(blocker)] += 1
    return dict(counts.most_common())


def fillability_summary(fillability: dict[str, Any]) -> dict[str, Any]:
    top = fillability.get("topExecutable") if isinstance(fillability.get("topExecutable"), list) else []
    series_counts: Counter[str] = Counter()
    for item in top:
        if not isinstance(item, dict):
            continue
        series = str(item.get("seriesTicker") or "unknown")
        series_counts[series] += 1
    return {
        "present": bool(fillability),
        "marketsInspected": fillability.get("marketsInspected", 0),
        "executablePublicQuotes": fillability.get("executablePublicQuotes", 0),
        "bucketCounts": fillability.get("bucketCounts") or {},
        "topSeries": dict(series_counts.most_common(8)),
        "readyForPaper": False,
        "researchOnly": fillability.get("researchOnly", True),
        "writesOrders": fillability.get("writesOrders", False),
        "decision": "research-only; use to select narrow categories, not to trade",
    }


def macro_rates_summary(requirements: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    rows = replay.get("rows") if isinstance(replay.get("rows"), list) else []
    paper_blockers: Counter[str] = Counter()
    watch_count = 0
    max_yes_edge = None
    max_no_edge = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("watchResearchOnly") is True:
            watch_count += 1
        for blocker in row.get("blockers") or []:
            paper_blockers[str(blocker)] += 1
        yes_edge = row.get("yesEdgePctVsAsk")
        no_edge = row.get("noEdgePctVsNoAsk")
        if isinstance(yes_edge, (int, float)):
            max_yes_edge = yes_edge if max_yes_edge is None else max(max_yes_edge, yes_edge)
        if isinstance(no_edge, (int, float)):
            max_no_edge = no_edge if max_no_edge is None else max(max_no_edge, no_edge)
    requirements_cleared = (
        bool(requirements)
        and requirements.get("decision") == "research-only-macro-rates-requirements-cleared"
        and int(requirements.get("blockedCount") or 0) == 0
    )
    replay_complete = (
        bool(replay)
        and replay.get("decision") == "research-only-macro-rates-cross-source-replay-complete"
    )
    return {
        "present": bool(requirements or replay),
        "requirementsDecision": requirements.get("decision", "missing"),
        "requirementsCleared": requirements_cleared,
        "requirementsBlockedCount": int(requirements.get("blockedCount") or 0),
        "requirementsPassCount": int(requirements.get("passCount") or 0),
        "replayDecision": replay.get("decision", "missing"),
        "replayComplete": replay_complete,
        "rowCount": len(rows),
        "watchResearchOnlyCount": watch_count,
        "maxYesEdgePctVsAsk": max_yes_edge,
        "maxNoEdgePctVsNoAsk": max_no_edge,
        "paperBlockerCounts": dict(paper_blockers.most_common()),
        "readyForPaper": False,
        "readyForExecution": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "decision": "research-only macro/rates parser and cross-source replay evidence; not paper-ready",
        "requiredNextEvidence": [
            "larger sample replay across comparable resolved macro/rates markets",
            "fee, spread, and fillability stress",
            "prediction review candidate marked paper-ready",
            "promotion stage agreement and no active no-edge memory conflict",
        ],
    }


def event_forward_capture_summary(
    targets: dict[str, Any],
    cycle: dict[str, Any],
    timestamp_dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = targets.get("forwardCapturePlan") if isinstance(targets.get("forwardCapturePlan"), dict) else {}
    timestamp_dataset = timestamp_dataset or {}
    follow_up = plan.get("followUp") if isinstance(plan.get("followUp"), list) else []
    blockers = [str(item) for item in (targets.get("blockers") or [])]
    cycle_blockers = [str(item) for item in (cycle.get("blockers") or [])]
    cycle_watch_review = (
        cycle.get("eventLagWatchReview")
        if isinstance(cycle.get("eventLagWatchReview"), dict)
        else {}
    )
    command = str(plan.get("command") or targets.get("standingRecorderCommand") or targets.get("recorderCommand") or "")
    return {
        "present": bool(targets or cycle),
        "targetsDecision": targets.get("decision", "missing"),
        "cycleDecision": cycle.get("decision", "missing"),
        "forwardCaptureRequired": bool(plan.get("required")),
        "reason": plan.get("reason", "missing"),
        "recordableTargetCount": int(targets.get("targetCount") or 0),
        "tokenSpecificCandidateCount": int(targets.get("tokenSpecificCandidateCount") or 0),
        "excludedMappingCandidateCount": int(targets.get("excludedMappingCandidateCount") or 0),
        "excludedMappingReasonCounts": (
            targets.get("excludedMappingReasonCounts")
            if isinstance(targets.get("excludedMappingReasonCounts"), dict)
            else {}
        ),
        "publicCaptureReviewLeadCount": int(targets.get("publicCaptureReviewLeadCount") or 0),
        "reviewLeadRecorderCommand": targets.get("reviewLeadRecorderCommand"),
        "staleContextTargetCount": int(targets.get("staleContextTargetCount") or 0),
        "unrecoverablePreEventTargetCount": int(targets.get("unrecoverablePreEventTargetCount") or 0),
        "completeWindowTargetCount": int(targets.get("completeWindowTargetCount") or 0),
        "coverageStatusCounts": targets.get("coverageStatusCounts") if isinstance(targets.get("coverageStatusCounts"), dict) else {},
        "timestampDataset": {
            "present": bool(timestamp_dataset),
            "decision": timestamp_dataset.get("decision", "missing"),
            "candidateCount": timestamp_dataset.get("candidateCount", 0),
            "coverageStatusCounts": (
                timestamp_dataset.get("coverageStatusCounts")
                if isinstance(timestamp_dataset.get("coverageStatusCounts"), dict)
                else {}
            ),
            "completeWindowTargetCount": timestamp_dataset.get("completeWindowTargetCount", 0),
            "unrecoverablePreEventTargetCount": timestamp_dataset.get("unrecoverablePreEventTargetCount", 0),
            "forwardCaptureRequired": timestamp_dataset.get("forwardCaptureRequired", False),
            "readyForPaper": timestamp_dataset.get("readyForPaper", False),
        },
        "standingTerms": targets.get("standingTerms", "missing"),
        "durationSec": int(targets.get("durationSec") or 0),
        "maxOutputMb": int(targets.get("maxOutputMb") or 0),
        "minFreeGb": int(targets.get("minFreeGb") or 0),
        "standingRecorderCommand": command,
        "followUp": follow_up,
        "blockers": blockers,
        "cycleBlockers": cycle_blockers,
        "eventLagResearchWatchReady": bool(cycle.get("eventLagResearchWatchReady")),
        "eventLagReplayWatchReady": bool(cycle.get("eventLagReplayWatchReady")),
        "eventLagWatchReview": {
            "present": bool(cycle_watch_review),
            "decision": cycle_watch_review.get("decision"),
            "watchReady": bool(cycle_watch_review.get("watchReady")),
            "repricedWatchWindowCount": cycle_watch_review.get("repricedWatchWindowCount"),
            "blockers": (
                cycle_watch_review.get("blockers")
                if isinstance(cycle_watch_review.get("blockers"), list)
                else []
            ),
        },
        "readyForPaper": False,
        "readyForExecution": False,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "decision": "research-only forward CLOB capture plan; stale event windows cannot promote paper",
        "requiredNextEvidence": [
            "standing public CLOB capture before and through future news windows",
            "refreshed event-market mapping after capture",
            "no-lookahead event-lag replay with pre-event quotes present",
            "fillable live books, spread/fee stress, resolved labels, and paper review gate",
        ],
    }


def current_cross_venue_universe_rejected(no_edge: dict[str, Any]) -> bool:
    entries = no_edge.get("entries") if isinstance(no_edge.get("entries"), list) else []
    by_id = {str(entry.get("id")): entry for entry in entries if isinstance(entry, dict)}
    narrow = by_id.get("narrow-category-cross-venue-current-universe") or {}
    broad = by_id.get("broad-cross-venue-prediction-scan-current-normalization") or {}
    crypto = by_id.get("crypto-settlement-horizon-parser-current-form") or {}
    macro = by_id.get("macro-rates-line-parser-current-form") or {}
    return bool(
        (narrow.get("currentFormRejected") or broad.get("currentFormRejected"))
        and crypto.get("verdict") == "no-edge"
        and macro.get("verdict") == "no-edge"
    )


def current_clob_drift_rejected(no_edge: dict[str, Any]) -> bool:
    entries = no_edge.get("entries") if isinstance(no_edge.get("entries"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") == "polymarket-clob-drift-persistence-current-thresholds":
            return entry.get("verdict") == "no-edge"
    return False


def current_resolved_outcome_review_rejected(no_edge: dict[str, Any]) -> bool:
    entries = no_edge.get("entries") if isinstance(no_edge.get("entries"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") == "resolved-outcome-current-watchlist-context-only":
            return bool(entry.get("currentFormRejected"))
    return False


def next_tests(args: dict[str, Any]) -> list[dict[str, Any]]:
    review = args["review"]
    watch_items = args["watchItems"]
    clob = args["clob"]
    blocker_counts = args["watchBlockers"]
    resolved_join = args["resolvedJoin"]
    fillability = args.get("fillability") or {}
    event_forward_capture = args.get("eventForwardCapture") or {}
    no_edge = args.get("noEdge") or {}
    current_universe_rejected = current_cross_venue_universe_rejected(no_edge)
    clob_drift_rejected = current_clob_drift_rejected(no_edge)
    resolved_outcome_rejected = current_resolved_outcome_review_rejected(no_edge)
    tests: list[dict[str, Any]] = []

    if event_forward_capture.get("forwardCaptureRequired"):
        command = str(event_forward_capture.get("standingRecorderCommand") or "")
        tests.append({
            "id": "prediction-forward-event-clob-capture",
            "track": "prediction-markets",
            "priority": 0,
            "oneVariable": "forward public CLOB capture window",
            "hypothesis": "Prediction event-lag research is blocked by missing pre-event quotes and ambiguous mapping; standing public CLOB capture before future news windows can create usable no-lookahead evidence.",
            "commandHint": command,
            "blockedBy": event_forward_capture.get("blockers") or [],
            "promotionRule": "Capture creates research data only; paper remains blocked until clean event-market mapping, no-lookahead replay, resolved labels, spread/fee stress, and paper-promotion review all pass.",
            "researchOnly": True,
            "readyForPaper": False,
            "readyForExecution": False,
            "writesOrders": False,
            "touchesBroker": False,
        })

    if fillability.get("executablePublicQuotes", 0) and not current_universe_rejected:
        tests.append({
            "id": "kalshi-fillability-guided-rates-scan",
            "track": "prediction-markets",
            "priority": 0,
            "oneVariable": "fillable public quote universe",
            "hypothesis": "Kalshi currently has tight/usable two-sided public quotes concentrated in a small set of macro/rates markets; start cross-venue matching there before broad scans.",
            "commandHint": "Run the Kalshi fillability snapshot first, then restrict category drilldown to the top fillable macro/rates-style series before comparing blocker mix.",
            "promotionRule": "Fillability is necessary but not sufficient; require same-horizon settlement, resolved-history, fees/spread stress, and CLOB/persistence evidence before paper.",
        })

    if (review.get("counts") or {}).get("watch", 0) == 0 and not current_universe_rejected:
        tests.append({
            "id": "narrow-cross-venue-normalization",
            "track": "prediction-markets",
            "priority": 1,
            "oneVariable": "market universe",
            "hypothesis": "The broad cross-venue scan has enough venue coverage but no semantically/fillably comparable candidates; narrowing to repeated categories should improve match quality.",
            "commandHint": "Run the scanner on a small category set such as BTC up/down, Fed/rates, elections, or same-event sports outrights; compare watch count and blocker mix.",
            "promotionRule": "Only continue if watch candidates appear with same-horizon settlement and clear wording.",
        })

    joined_count = int(resolved_join.get("joinedResearchOnlyCount") or 0)
    if blocker_counts.get("not-joined-to-market-specific-resolution-history") and joined_count == 0 and not resolved_outcome_rejected:
        tests.append({
            "id": "join-watchlist-to-resolution-history",
            "track": "prediction-markets",
            "priority": 2,
            "oneVariable": "resolved-outcome evidence",
            "hypothesis": "The current calibration edge is broad by-price prior only; market-specific history may remove false edges before CLOB capture.",
            "commandHint": "Run npm run bill:prediction-resolved-outcome-join, then inspect whether any watchlist item has enough comparable resolved markets.",
            "promotionRule": "No candidate reaches paper unless market-family calibration remains positive after spread, fee, and settlement review.",
        })
    elif blocker_counts.get("not-joined-to-market-specific-resolution-history") and not resolved_outcome_rejected:
        tests.append({
            "id": "resolved-outcome-join-review",
            "track": "prediction-markets",
            "priority": 2,
            "oneVariable": "resolved-outcome evidence",
            "hypothesis": "Some market-family resolved history exists, but paper still needs fillability, fees, settlement wording, and promotion review.",
            "commandHint": "Inspect .rumbling-hedge/state/prediction-resolved-outcome-join.latest.json and remove broad-prior candidates that have thin or irrelevant matches.",
            "promotionRule": "Only continue if resolvedMatchCount is substantial, top matches are semantically comparable, and calibrated edge survives spread/fees.",
        })

    if watch_items and not clob_drift_rejected:
        eligible = [
            {
                "externalId": item.get("externalId"),
                "question": item.get("question"),
                "tokenId": item.get("clobTokenId"),
                "spread": item.get("spread"),
                "bucket": spread_bucket(item),
                "blockers": item.get("blockers") or [],
            }
            for item in watch_items
            if item.get("clobCaptureEligible")
        ]
        tests.append({
            "id": "targeted-clob-persistence-capture",
            "track": "prediction-markets",
            "priority": 3,
            "oneVariable": "observation time",
            "hypothesis": "If any watchlist edge is real, quote/trade persistence should improve with longer read-only capture on targeted tokens.",
            "commandHint": "Run the CLOB recorder only on eligible watchlist token IDs, then rerun persistence and edge gate with the same thresholds.",
            "promotionRule": "Paper remains blocked unless CLOB edge gate reports watchResearchGroups > 0, spread acceptable, and directional hit rate >= threshold.",
            "eligibleTokens": eligible[:5],
        })

    if (clob.get("blockerCounts") or {}).get("net-drift-below-threshold") and not clob_drift_rejected:
        tests.append({
            "id": "reject-current-clob-drift-hypothesis",
            "track": "prediction-markets",
            "priority": 4,
            "oneVariable": "hypothesis family",
            "hypothesis": "The first CLOB drift/persistence hypothesis is not showing edge under current thresholds.",
            "commandHint": "Write the rejected CLOB drift hypothesis to the no-edge ledger and test a different microstructure feature, not looser thresholds.",
            "promotionRule": "Do not lower CLOB thresholds to create paper candidates; require fresh evidence from a new feature or longer capture.",
        })

    return tests


def resolved_outcome_review(
    resolved_items: list[dict[str, Any]],
    watch_items: list[dict[str, Any]],
    resolved_join: dict[str, Any],
) -> dict[str, Any]:
    watch_blockers = watchlist_blockers(watch_items)
    item_reviews: list[dict[str, Any]] = []
    for item in resolved_items:
        status = str(item.get("status") or "missing")
        resolved_count = int(item.get("resolvedMatchCount") or 0)
        subject_count = int(item.get("subjectSpecificMatchCount") or 0)
        if status == "joined-research-only":
            decision = "context-only-not-paper"
        elif resolved_count <= 0:
            decision = "insufficient-market-family-history"
        elif subject_count < int(resolved_join.get("minSpecificMatches") or 0):
            decision = "insufficient-subject-specific-history"
        else:
            decision = "not-paper-ready"
        item_reviews.append({
            "externalId": item.get("externalId"),
            "question": item.get("question"),
            "status": status,
            "resolvedMatchCount": resolved_count,
            "subjectSpecificMatchCount": subject_count,
            "subjectSpecificWinRate": item.get("subjectSpecificWinRate"),
            "decision": decision,
        })
    joined_count = int(resolved_join.get("joinedResearchOnlyCount") or 0)
    return {
        "status": "research-only",
        "decision": "do-not-promote-resolved-history-without-paper-review-and-fillability",
        "joinedResearchOnlyCount": joined_count,
        "readyForPaper": bool(resolved_join.get("readyForPaper")) is True,
        "broadPriorRisk": "high" if watch_blockers.get("broad-by-price-prior-only") else "normal",
        "marketSpecificCoverage": {
            "watchCount": int(resolved_join.get("watchCount") or len(watch_items)),
            "historicalRowsLoaded": int(resolved_join.get("historicalRowsLoaded") or 0),
            "minSpecificMatches": resolved_join.get("minSpecificMatches"),
            "statusCounts": resolved_join.get("statusCounts") or {},
        },
        "items": item_reviews,
        "requiredNextEvidence": [
            "candidate must be paper-ready in prediction review",
            "promotion stage must agree with paper readiness",
            "resolved outcomes must be semantically comparable and subject-specific",
            "spread, fees, CLOB persistence, directional hit rate, and fillability must pass",
            "no active no-edge memory without explicit retestPassed or supersededBy",
        ],
    }


def main() -> int:
    review_artifact = read_json(STATE / "prediction-review.latest.json")
    cycle = read_json(STATE / "prediction-cycle.latest.json")
    calibration = read_json(STATE / "prediction-calibration-gate.latest.json")
    watchlist = read_json(STATE / "prediction-research-watchlist.latest.json")
    clob = read_json(STATE / "polymarket-clob-edge-gate.latest.json")
    resolved_join = read_json(STATE / "prediction-resolved-outcome-join.latest.json")
    fillability = read_json(STATE / "kalshi-fillability-snapshot.latest.json")
    macro_rates_requirements = read_json(MACRO_RATES_REQUIREMENTS)
    macro_rates_replay = read_json(MACRO_RATES_REPLAY)
    event_capture_targets = read_json(EVENT_CAPTURE_TARGETS)
    event_capture_cycle = read_json(EVENT_CAPTURE_CYCLE)
    event_timestamp_dataset = read_json(EVENT_TIMESTAMP_DATASET)
    event_capture_summary = event_forward_capture_summary(
        event_capture_targets,
        event_capture_cycle,
        event_timestamp_dataset,
    )
    no_edge = read_json(PREDICTION_NO_EDGE)
    resolved_items = resolved_join.get("items") if isinstance(resolved_join.get("items"), list) else []
    subject_specific_counts = [
        {
            "externalId": item.get("externalId"),
            "status": item.get("status"),
            "resolvedMatchCount": item.get("resolvedMatchCount"),
            "subjectSpecificMatchCount": item.get("subjectSpecificMatchCount"),
            "subjectSpecificWinRate": item.get("subjectSpecificWinRate"),
        }
        for item in resolved_items
        if isinstance(item, dict)
    ]

    review = review_payload(review_artifact)
    watch_items = watchlist.get("items") if isinstance(watchlist.get("items"), list) else []
    blocker_counts = watchlist_blockers(watch_items)
    tests = next_tests({
        "review": review,
        "watchItems": watch_items,
        "clob": clob,
        "watchBlockers": blocker_counts,
        "resolvedJoin": resolved_join,
        "fillability": fillability_summary(fillability),
        "eventForwardCapture": event_capture_summary,
        "noEdge": no_edge,
    })

    payload = {
        "command": "prediction-evidence-triage",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForPaper": False,
        "decision": "research-only; no prediction-market candidate is paper-ready",
        "review": {
            "readyForPaper": review.get("readyForPaper", False),
            "counts": review.get("counts") or {},
            "venueCounts": review.get("venueCounts") or {},
            "blockers": review.get("blockers") or [],
            "recommendation": review.get("recommendation", ""),
        },
        "cycle": {
            "ts": cycle.get("ts"),
            "posture": cycle.get("posture"),
            "execute": cycle.get("execute") or {},
        },
        "calibration": {
            "status": calibration.get("status", "missing"),
            "watchResearchCandidates": calibration.get("watchResearchCandidates", 0),
            "readyForPaper": calibration.get("readyForPaper", False),
        },
        "watchlist": {
            "watchCount": watchlist.get("watchCount", len(watch_items)),
            "readyForPaper": watchlist.get("readyForPaper", False),
            "blockerCounts": blocker_counts,
            "spreadBuckets": dict(Counter(spread_bucket(item) for item in watch_items)),
        },
        "clobEdgeGate": {
            "status": clob.get("status", "missing"),
            "rowsRead": clob.get("rowsRead", 0),
            "scoredGroups": clob.get("scoredGroups", 0),
            "watchResearchGroups": clob.get("watchResearchGroups", 0),
            "readyForPaper": clob.get("readyForPaper", False),
            "blockerCounts": clob.get("blockerCounts") or {},
        },
        "resolvedOutcomeJoin": {
            "statusCounts": resolved_join.get("statusCounts") or {},
            "historicalRowsLoaded": resolved_join.get("historicalRowsLoaded", 0),
            "watchCount": resolved_join.get("watchCount", 0),
            "joinedResearchOnlyCount": resolved_join.get("joinedResearchOnlyCount", 0),
            "minSpecificMatches": resolved_join.get("minSpecificMatches", "missing"),
            "subjectSpecificCounts": subject_specific_counts,
            "readyForPaper": resolved_join.get("readyForPaper", False),
        },
        "resolvedOutcomeReview": resolved_outcome_review(resolved_items, watch_items, resolved_join),
        "kalshiFillability": fillability_summary(fillability),
        "macroRates": macro_rates_summary(macro_rates_requirements, macro_rates_replay),
        "eventForwardCapture": event_capture_summary,
        "nextTests": tests,
        "hardRules": [
            "Prediction markets stay research-only until review.readyForPaper and promotion recommendedStage agree.",
            "Broad by-price priors are not paper-trade evidence without market-specific resolved outcomes.",
            "CLOB snapshots are evidence only after spread, persistence, directional hit rate, and fillability gates pass.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
