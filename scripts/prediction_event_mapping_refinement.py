#!/usr/bin/env python3
"""Refine prediction event-to-market mappings after manual watch review.

Research-only. The goal is to stop threshold chasing after a manual review
rejects or downgrades event-lag windows, then identify whether the next single
variable should be mapping specificity, source timing, or forward CLOB capture.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
MANUAL_REVIEW = STATE / "prediction-event-lag-manual-review.latest.json"
MAPPING_PLAN = STATE / "prediction-event-market-mapping-plan.latest.json"
RECORDER = STATE / "polymarket-clob-recorder.latest.json"
OUT = STATE / "prediction-event-mapping-refinement.latest.json"


def default_markdown_path() -> Path:
    review_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"prediction-event-mapping-refinement-{review_date}.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def normalized_headline(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _rows_by_headline(rows: list[Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        headline = normalized_headline(row.get("headline"))
        if headline:
            grouped[headline].append(row)
    return dict(grouped)


def question_profile(question: Any) -> dict[str, Any]:
    text = normalized_headline(question)
    actors: list[str] = []
    for actor in ("us", "israel", "iran", "fed"):
        if actor in text.split() or f"{actor} " in text or f" {actor}" in text:
            actors.append(actor)
    if "interest rate" in text or "rates" in text or "bps" in text or "fed" in actors:
        event_family = "macro-rates"
    elif "peace deal" in text or "ceasefire" in text or "agreement" in text:
        event_family = "geopolitical-agreement"
    else:
        event_family = "unknown"
    deadline = None
    for marker in (" by ", " after "):
        if marker in text:
            deadline = text.split(marker, 1)[1].strip(" ?")
            break
    return {
        "question": question,
        "actors": actors,
        "eventFamily": event_family,
        "deadlineText": deadline,
    }


def headline_profile(headline: Any) -> dict[str, Any]:
    text = normalized_headline(headline)
    actors = [actor for actor in ("us", "israel", "iran", "fed") if actor in text.split() or f"{actor} " in text or f" {actor}" in text]
    event_families: list[str] = []
    if "peace deal" in text or "ceasefire" in text or "agreement" in text:
        event_families.append("geopolitical-agreement")
    if "rate hike" in text or "interest rate" in text or "inflation" in text or "fed" in actors:
        event_families.append("macro-rates")
    if not event_families:
        event_families.append("unknown")
    return {
        "headline": headline,
        "actors": actors,
        "eventFamily": event_families[0],
        "eventFamilies": event_families,
    }


def candidate_specificity_rows(headline: Any, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    head = headline_profile(headline)
    headline_families = set(head.get("eventFamilies") or [head["eventFamily"]])
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        question = candidate.get("question") or candidate.get("title")
        profile = question_profile(question)
        actor_overlap = sorted(set(head["actors"]) & set(profile["actors"]))
        family_match = (
            profile["eventFamily"] in headline_families
            or "unknown" in headline_families
            or profile["eventFamily"] == "unknown"
        )
        rows.append({
            "externalId": candidate.get("externalId"),
            "question": question,
            "actors": profile["actors"],
            "marketActors": (
                candidate.get("marketActors")
                if isinstance(candidate.get("marketActors"), list)
                else profile["actors"]
            ),
            "actorOverlap": actor_overlap,
            "eventFamily": profile["eventFamily"],
            "marketEventFamilies": (
                candidate.get("marketEventFamilies")
                if isinstance(candidate.get("marketEventFamilies"), list)
                else [profile["eventFamily"]]
            ),
            "deadlineText": profile["deadlineText"],
            "headlineEventFamily": head["eventFamily"],
            "headlineEventFamilies": list(headline_families),
            "mappingStatus": candidate.get("mappingStatus"),
            "specificityFlags": (
                candidate.get("specificityFlags")
                if isinstance(candidate.get("specificityFlags"), list)
                else []
            ),
            "missingHeadlineActors": (
                candidate.get("missingHeadlineActors")
                if isinstance(candidate.get("missingHeadlineActors"), list)
                else []
            ),
            "venue": candidate.get("venue"),
            "clobTokenId": candidate.get("clobTokenId"),
            "bestBid": candidate.get("bestBid"),
            "bestAsk": candidate.get("bestAsk"),
            "spreadPct": candidate.get("spreadPct"),
            "topBookDepth": candidate.get("topBookDepth"),
            "familyMatch": family_match,
            "specificityIssues": [
                issue
                for issue, active in [
                    ("headline-has-multiple-event-families", len(headline_families) > 1),
                    ("headline-does-not-identify-counterparty", len(actor_overlap) < 2 and profile["eventFamily"] == "geopolitical-agreement"),
                    ("headline-family-differs-from-question-family", not family_match),
                    ("deadline-choice-requires-forward-market-selection", bool(profile["deadlineText"])),
                ]
                if active
            ],
        })
    return rows


def mapping_repair_targets(headline_reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    repair_qualities = {
        "refine-ambiguous-fanout",
        "refine-missing-current-candidate",
        "reject-spread-and-ambiguous-fanout",
    }
    for item in headline_reviews:
        if item.get("mappingQuality") not in repair_qualities:
            continue
        rows = item.get("candidateSpecificityRows") if isinstance(item.get("candidateSpecificityRows"), list) else []
        family_counts: Counter[str] = Counter()
        counterparty_counts: Counter[str] = Counter()
        deadline_counts: Counter[str] = Counter()
        status_counts: Counter[str] = Counter()
        specificity_counts: Counter[str] = Counter()
        top_candidates: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            families = row.get("marketEventFamilies") if isinstance(row.get("marketEventFamilies"), list) else [row.get("eventFamily")]
            for family in families:
                if family:
                    family_counts[str(family)] += 1
            actors = row.get("marketActors") if isinstance(row.get("marketActors"), list) else row.get("actors")
            if isinstance(actors, list) and actors:
                counterparty_counts["/".join(sorted(str(actor) for actor in actors))] += 1
            if row.get("deadlineText"):
                deadline_counts[str(row.get("deadlineText"))] += 1
            if row.get("mappingStatus"):
                status_counts[str(row.get("mappingStatus"))] += 1
            for flag in row.get("specificityFlags") if isinstance(row.get("specificityFlags"), list) else []:
                specificity_counts[str(flag)] += 1
            for issue in row.get("specificityIssues") if isinstance(row.get("specificityIssues"), list) else []:
                specificity_counts[str(issue)] += 1
            if len(top_candidates) < 8:
                top_candidates.append({
                    "externalId": row.get("externalId"),
                    "clobTokenId": row.get("clobTokenId"),
                    "question": row.get("question"),
                    "marketActors": actors if isinstance(actors, list) else [],
                    "marketEventFamilies": families,
                    "deadlineText": row.get("deadlineText"),
                    "mappingStatus": row.get("mappingStatus"),
                    "specificityFlags": row.get("specificityFlags"),
                    "bestBid": row.get("bestBid"),
                    "bestAsk": row.get("bestAsk"),
                    "spreadPct": row.get("spreadPct"),
                    "topBookDepth": row.get("topBookDepth"),
                })
        targets.append({
            "headline": item.get("headline"),
            "eventIso": item.get("eventIso"),
            "mappingQuality": item.get("mappingQuality"),
            "repairReason": "ambiguous headline fanout; choose exactly one event family, counterparty set, and deadline before forward capture",
            "reviewedExternalIds": item.get("reviewedExternalIds") or [],
            "candidateExternalIds": item.get("candidateExternalIds") or [],
            "candidateCount": len(item.get("candidateExternalIds") or []),
            "headlineEventFamilies": sorted({
                str(family)
                for row in rows
                if isinstance(row, dict)
                for family in (row.get("headlineEventFamilies") if isinstance(row.get("headlineEventFamilies"), list) else [])
            }),
            "candidateFamilyCounts": dict(family_counts),
            "candidateCounterpartyCounts": dict(counterparty_counts),
            "candidateDeadlineCounts": dict(deadline_counts),
            "mappingStatusCounts": dict(status_counts),
            "specificityFlagCounts": dict(specificity_counts),
            "topCandidateSummaries": top_candidates,
            "deadlineLadderCaptureCandidates": deadline_ladder_capture_candidates(rows, item.get("eventIso")),
            "nextSingleVariable": "market specificity",
            "blockedUntil": [
                "single event family selected",
                "single counterparty set selected",
                "single deadline/market family selected",
                "forward public CLOB capture collected after mapping repair",
            ],
        })
    return targets


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_event_date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        return None


def parse_deadline_date(deadline_text: Any, event_date: date | None) -> date | None:
    text = normalized_headline(deadline_text).replace(",", "")
    parts = text.split()
    if len(parts) < 2 or parts[0] not in MONTHS:
        return None
    try:
        month = MONTHS[parts[0]]
        day = int(parts[1])
        year = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else (event_date.year if event_date else datetime.now(timezone.utc).year)
        return date(year, month, day)
    except Exception:
        return None


def deadline_ladder_capture_candidates(rows: list[dict[str, Any]], event_iso: Any = None) -> list[dict[str, Any]]:
    """Choose adjacent deadline contracts for bounded forward capture only.

    This deliberately does not resolve the mapping. It narrows future public
    CLOB capture to the most semantically direct agreement/ceasefire ladder
    while keeping paper/execution blocked until settlement text and no-lookahead
    evidence are reviewed.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    event_date = parse_event_date(event_iso)
    positive_terms = ("agreement", "ceasefire")
    adjacent_or_wrong_terms = (
        "permanent peace deal",
        "blockade",
        "strait of hormuz",
        "uranium",
        "enrichment",
        "transit fees",
        "military action",
        "airstrike",
        "nuclear",
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        token = str(row.get("clobTokenId") or "")
        question = normalized_headline(row.get("question"))
        if not token or token in seen:
            continue
        if not any(term in question for term in positive_terms):
            continue
        if any(term in question for term in adjacent_or_wrong_terms):
            continue
        families = row.get("marketEventFamilies") if isinstance(row.get("marketEventFamilies"), list) else [row.get("eventFamily")]
        if "geopolitical-agreement" not in {str(family) for family in families}:
            continue
        status = str(row.get("mappingStatus") or "")
        if "counterparty" in status or "mismatch" in status or "ambiguous" in status:
            continue
        deadline_date = parse_deadline_date(row.get("deadlineText"), event_date)
        if event_date and deadline_date and deadline_date < event_date:
            continue
        seen.add(token)
        out.append({
            "externalId": row.get("externalId"),
            "tokenId": token,
            "question": row.get("question"),
            "deadlineText": row.get("deadlineText"),
            "deadlineDate": deadline_date.isoformat() if deadline_date else None,
            "marketActors": row.get("marketActors") if isinstance(row.get("marketActors"), list) else row.get("actors"),
            "marketEventFamilies": families,
            "mappingStatus": row.get("mappingStatus"),
            "bestBid": row.get("bestBid"),
            "bestAsk": row.get("bestAsk"),
            "spreadPct": row.get("spreadPct"),
            "topBookDepth": row.get("topBookDepth"),
            "reviewUseOnly": "deadline-ladder-forward-capture-only; not a mapping override, paper approval, signal, or execution approval",
        })
    return sorted(
        out,
        key=lambda item: (
            str(item.get("deadlineDate") or item.get("deadlineText") or ""),
            -float(item.get("topBookDepth") or 0),
            str(item.get("tokenId") or ""),
        ),
    )


def public_capture_review_leads(repair_targets: list[dict[str, Any]], recorder: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    recorder = recorder or {}
    live_quality = recorder.get("liveQualityDiagnostics") if isinstance(recorder.get("liveQualityDiagnostics"), dict) else {}
    assets = live_quality.get("assets") if isinstance(live_quality.get("assets"), list) else []
    leads: list[dict[str, Any]] = []
    for target in repair_targets:
        if not isinstance(target, dict):
            continue
        target_families = set((target.get("candidateFamilyCounts") or {}).keys())
        target_counterparties = set((target.get("candidateCounterpartyCounts") or {}).keys())
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            profile = question_profile(asset.get("question"))
            if target_families and profile["eventFamily"] not in target_families:
                continue
            counterparty = "/".join(sorted(str(actor) for actor in profile["actors"]))
            counterparty_match = counterparty in target_counterparties if target_counterparties else False
            if not counterparty_match and profile["eventFamily"] == "geopolitical-agreement":
                continue
            leads.append({
                "headline": target.get("headline"),
                "question": asset.get("question"),
                "tokenId": asset.get("tokenId"),
                "eventFamily": profile["eventFamily"],
                "counterparty": counterparty,
                "deadlineText": profile["deadlineText"],
                "status": asset.get("status"),
                "bestBid": asset.get("liveBestBid"),
                "bestAsk": asset.get("liveBestAsk"),
                "spread": asset.get("liveSpread"),
                "bidSize": asset.get("liveBidSize"),
                "askSize": asset.get("liveAskSize"),
                "lastBookLocalTs": asset.get("lastBookLocalTs"),
                "reviewUseOnly": "public-capture-fillability-lead; not a mapping override, signal, or paper approval",
            })
    return leads


def build_refinement(
    manual_review: dict[str, Any],
    mapping_plan: dict[str, Any],
    recorder: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reviewed = manual_review.get("reviewedWindows") if isinstance(manual_review.get("reviewedWindows"), list) else []
    candidates = mapping_plan.get("candidates") if isinstance(mapping_plan.get("candidates"), list) else []
    reviewed_by_headline = _rows_by_headline(reviewed)
    candidates_by_headline = _rows_by_headline(candidates)

    headline_reviews: list[dict[str, Any]] = []
    mapping_quality_counts: Counter[str] = Counter()
    ambiguous_fanout_count = 0
    for headline, windows in sorted(reviewed_by_headline.items()):
        candidate_rows = candidates_by_headline.get(headline, [])
        candidate_ids = sorted({str(item.get("externalId")) for item in candidate_rows if item.get("externalId")})
        reviewed_ids = sorted({str(item.get("externalId")) for item in windows if item.get("externalId")})
        decisions = Counter(str(item.get("decision") or "missing") for item in windows)
        reasons = sorted({
            str(reason)
            for item in windows
            for reason in (item.get("reasons") if isinstance(item.get("reasons"), list) else [])
        })
        ambiguous = len(candidate_ids) > 1 or len(reviewed_ids) > 1 or any(
            "same-headline-maps-to-multiple-markets" in (item.get("reasons") or [])
            for item in windows
            if isinstance(item, dict)
        )
        rejected_for_spread = any(
            "move-does-not-clear-half-spread" in (item.get("reasons") or [])
            for item in windows
            if isinstance(item, dict)
        )
        manual_selections = [
            item
            for item in windows
            if isinstance(item, dict)
            and item.get("decision") == "keep-watch"
            and not (item.get("reasons") if isinstance(item.get("reasons"), list) else [])
            and item.get("externalId")
            and str(item.get("externalId")) in candidate_ids
        ]
        fanout_resolved_by_manual_review = (
            ambiguous
            and not rejected_for_spread
            and len(manual_selections) == 1
            and bool(manual_selections[0].get("clobTokenId"))
        )
        if ambiguous and not fanout_resolved_by_manual_review:
            ambiguous_fanout_count += 1
        if rejected_for_spread and ambiguous:
            mapping_quality = "reject-spread-and-ambiguous-fanout"
        elif rejected_for_spread:
            mapping_quality = "reject-spread-quality"
        elif fanout_resolved_by_manual_review:
            mapping_quality = "manual-selected-forward-capture-watch"
        elif ambiguous:
            mapping_quality = "refine-ambiguous-fanout"
        elif not candidate_ids:
            mapping_quality = "refine-missing-current-candidate"
        else:
            mapping_quality = "single-market-candidate-watch-only"
        mapping_quality_counts[mapping_quality] += 1
        headline_reviews.append({
            "headline": windows[0].get("headline"),
            "eventIso": windows[0].get("eventIso"),
            "reviewedExternalIds": reviewed_ids,
            "candidateExternalIds": candidate_ids,
            "decisionCounts": dict(decisions),
            "reasons": reasons,
            "mappingQuality": mapping_quality,
            "fanoutResolvedByManualReview": fanout_resolved_by_manual_review,
            "manualSelectedExternalId": str(manual_selections[0].get("externalId")) if fanout_resolved_by_manual_review else None,
            "manualSelectedTokenId": str(manual_selections[0].get("clobTokenId")) if fanout_resolved_by_manual_review else None,
            "manualSelectedQuestion": manual_selections[0].get("question") if fanout_resolved_by_manual_review else None,
            "nextSingleVariable": (
                "market specificity"
                if mapping_quality in {"refine-ambiguous-fanout", "refine-missing-current-candidate", "reject-spread-and-ambiguous-fanout"}
                else "forward public CLOB capture"
            ),
            "candidateSpecificityRows": candidate_specificity_rows(windows[0].get("headline"), candidate_rows),
        })

    blockers: list[str] = []
    if not reviewed:
        blockers.append("manual-review-missing-or-empty")
    if not candidates:
        blockers.append("mapping-plan-has-no-current-candidates")
    if mapping_quality_counts.get("reject-spread-quality") or mapping_quality_counts.get("reject-spread-and-ambiguous-fanout"):
        blockers.append("spread-quality-rejected-current-watch-window")
    if ambiguous_fanout_count or mapping_quality_counts.get("reject-spread-and-ambiguous-fanout"):
        blockers.append("ambiguous-headline-to-market-fanout")
    if mapping_quality_counts.get("refine-missing-current-candidate"):
        blockers.append("manual-review-window-missing-from-current-mapping-plan")

    ready_for_forward_capture = bool(reviewed) and bool(candidates) and not blockers
    decision = (
        "research-only-mapping-refinement-ready-for-forward-capture"
        if ready_for_forward_capture
        else "research-only-mapping-refinement-required"
    )
    next_action = (
        "Run forward public CLOB capture on the single-market candidates, then rebuild no-lookahead replay."
        if ready_for_forward_capture
        else "Improve event-market mapping specificity before more threshold or paper-readiness work."
    )
    repair_targets = mapping_repair_targets(headline_reviews)
    capture_leads = public_capture_review_leads(repair_targets, recorder)
    ladder_candidates = [
        candidate
        for target in repair_targets
        for candidate in (
            target.get("deadlineLadderCaptureCandidates")
            if isinstance(target.get("deadlineLadderCaptureCandidates"), list)
            else []
        )
        if isinstance(candidate, dict)
    ]

    return {
        "command": "prediction-event-mapping-refinement",
        "generatedAt": now_iso(),
        "sourceArtifacts": [
            ".rumbling-hedge/state/prediction-event-lag-manual-review.latest.json",
            ".rumbling-hedge/state/prediction-event-market-mapping-plan.latest.json",
        ],
        "decision": decision,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "readyForForwardCapture": ready_for_forward_capture,
        "reviewedWindowCount": len([item for item in reviewed if isinstance(item, dict)]),
        "mappingCandidateCount": len([item for item in candidates if isinstance(item, dict)]),
        "mappingQualityCounts": dict(mapping_quality_counts),
        "headlineReviews": headline_reviews,
        "mappingRepairTargets": repair_targets,
        "mappingRepairTargetCount": len(repair_targets),
        "publicCaptureReviewLeads": capture_leads,
        "publicCaptureReviewLeadCount": len(capture_leads),
        "deadlineLadderCaptureCandidates": ladder_candidates,
        "deadlineLadderCaptureCandidateCount": len(ladder_candidates),
        "blockers": blockers,
        "promotionBlockers": [
            "manual-review-does-not-approve-paper-or-execution",
            "forward-public-clob-capture-still-required",
            "strict-no-lookahead-replay-still-required",
            "resolved-label-and-fillability-review-still-required",
        ],
        "nextAction": next_action,
        "oneVariableRule": {
            "currentVariable": "market specificity/source capture quality" if blockers else "forward public CLOB capture",
            "blockedVariables": [
                "threshold tuning",
                "paper trading",
                "execution",
                "sizing",
            ] if blockers else ["paper trading", "execution", "sizing"],
            "reason": "Do not tune lag/spread thresholds while headline-to-market mapping is ambiguous.",
        },
        "commands": [
            "npm run --silent bill:prediction-event-market-mapping-plan",
            "npm run --silent bill:prediction-event-mapping-refinement",
            "inspect .rumbling-hedge/state/prediction-event-mapping-refinement.latest.json mappingRepairTargets and write one manual mapping decision before capture",
            "npm run --silent bill:prediction-event-clob-capture-targets",
            "npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15 --max-output-mb 128 --min-free-gb 20",
            "npm run --silent bill:prediction-event-lag-replay",
            "npm run --silent bill:prediction-event-lag-sensitivity",
            "npm run --silent bill:prediction-event-lag-watch-review",
            "npm run --silent bill:prediction-event-lag-manual-review",
            "npm run --silent bill:prediction-evidence-triage",
        ],
        "hardRules": [
            "This artifact is not a signal, paper trade, funding approval, or execution approval.",
            "Only one variable may change next: mapping specificity/source capture quality, not thresholds and mapping together.",
            "A clean manual keep-watch selection can only authorize forward public CLOB capture, never paper, funding, sizing, or execution.",
            "Public capture review leads show fillable books to inspect manually; they are not mapping overrides.",
            "A headline mapping to multiple similar markets remains research-only until resolved by forward capture and settlement text review.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prediction Event Mapping Refinement",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only refinement after manual event-lag watch review.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Ready for forward capture: `{payload.get('readyForForwardCapture')}`",
        f"- Reviewed windows: `{payload.get('reviewedWindowCount')}`",
        f"- Mapping candidates: `{payload.get('mappingCandidateCount')}`",
        f"- Mapping quality counts: `{payload.get('mappingQualityCounts')}`",
        f"- Mapping repair targets: `{payload.get('mappingRepairTargetCount')}`",
        f"- Deadline ladder capture candidates: `{payload.get('deadlineLadderCaptureCandidateCount')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        f"- Next action: {payload.get('nextAction')}",
        "",
        "## Mapping Repair Targets",
        "",
    ]
    for item in payload.get("mappingRepairTargets") or []:
        lines.extend([
            f"### {item.get('eventIso')} - {item.get('mappingQuality')}",
            "",
            f"- Headline: {item.get('headline')}",
            f"- Candidate count: `{item.get('candidateCount')}`",
            f"- Candidate families: `{item.get('candidateFamilyCounts')}`",
            f"- Counterparty choices: `{item.get('candidateCounterpartyCounts')}`",
            f"- Deadline choices: `{item.get('candidateDeadlineCounts')}`",
            f"- Specificity flags: `{item.get('specificityFlagCounts')}`",
            f"- Deadline ladder capture candidates: `{item.get('deadlineLadderCaptureCandidates')}`",
            f"- Blocked until: `{item.get('blockedUntil')}`",
            "",
        ])
    lines.extend([
        "## Public Capture Review Leads",
        "",
        "These are fillable public CLOB books to inspect while repairing mapping. They do not approve paper or execution.",
        "",
    ])
    for item in payload.get("publicCaptureReviewLeads") or []:
        lines.extend([
            f"- `{item.get('status')}` {item.get('question')} | counterparty `{item.get('counterparty')}` | deadline `{item.get('deadlineText')}` | bid/ask `{item.get('bestBid')}`/`{item.get('bestAsk')}` | token `{item.get('tokenId')}`",
        ])
    lines.append("")
    lines.extend([
        "## Headline Reviews",
        "",
    ])
    for item in payload.get("headlineReviews") or []:
        lines.extend([
            f"### {item.get('eventIso')} - {item.get('mappingQuality')}",
            "",
            f"- Headline: {item.get('headline')}",
            f"- Reviewed markets: `{item.get('reviewedExternalIds')}`",
            f"- Current mapping candidates: `{item.get('candidateExternalIds')}`",
            f"- Decisions: `{item.get('decisionCounts')}`",
            f"- Reasons: `{item.get('reasons')}`",
            f"- Next single variable: `{item.get('nextSingleVariable')}`",
            "",
        ])
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refine event-to-market mappings after manual review.")
    parser.add_argument("--manual-review", default=str(MANUAL_REVIEW))
    parser.add_argument("--mapping-plan", default=str(MAPPING_PLAN))
    parser.add_argument("--recorder", default=str(RECORDER))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=None)
    args = parser.parse_args()

    payload = build_refinement(
        read_json(Path(args.manual_review)),
        read_json(Path(args.mapping_plan)),
        read_json(Path(args.recorder)),
    )
    out = Path(args.output)
    md = Path(args.markdown_output) if args.markdown_output else default_markdown_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
