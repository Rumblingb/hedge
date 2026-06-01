#!/usr/bin/env python3
"""Build the missing-label workplan for prediction-market event lag research.

Research-only. The event-lag requirements can tell us that current news is
fresh and CLOB capture exists, but the actual blocker is usually narrower:
which mapped events do not have enough subject-specific resolved labels, and
what should the next research agent collect?
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents/memorybrain"
HERMES = VAULT / "Agent-Hermes"

EVENT_REQUIREMENTS = STATE / "prediction-event-lag-requirements.latest.json"
EVENT_LAG_REPLAY = STATE / "prediction-event-lag-replay.latest.json"
LABEL_MANIFEST = STATE / "prediction-label-source-manifest.latest.json"
WATCHLIST = STATE / "prediction-research-watchlist.latest.json"
NEWS = STATE / "news-sentiment.json"
OUT = STATE / "prediction-event-label-gap-plan.latest.json"


STOPWORDS = {
    "will",
    "with",
    "from",
    "this",
    "that",
    "have",
    "there",
    "their",
    "market",
    "markets",
    "prediction",
    "latest",
    "update",
    "news",
    "yes",
    "no",
    "the",
    "and",
    "for",
    "new",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"prediction-event-label-gap-plan-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(text).lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def overlap_count(left: str, right: str) -> int:
    return len(tokens(left) & tokens(right))


def status_rank(status: str) -> int:
    if status == "needs-family-label-source":
        return 0
    if status == "needs-subject-label-source":
        return 1
    if status == "usable-for-research-join":
        return 3
    return 2


def command_is_safe(command: str) -> bool:
    lowered = command.lower()
    banned = ["execute", "fund", "deposit", "swap", "trade", "broker", "route"]
    return not any(word in lowered for word in banned)


def safe_commands(commands: list[str]) -> list[str]:
    return [command for command in commands if command_is_safe(command)]


def by_external_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("externalId")): row for row in rows if row.get("externalId") is not None}


def news_matches_for_question(news: dict[str, Any], question: str, minimum: int = 2) -> list[dict[str, Any]]:
    articles = news.get("articles") if isinstance(news.get("articles"), list) else []
    matches = []
    for article in articles:
        headline = str(article.get("headline") or "")
        score = overlap_count(question, headline)
        if score < minimum:
            continue
        matches.append({
            "headline": headline,
            "source": article.get("source"),
            "datetime": article.get("datetime"),
            "published": article.get("published"),
            "tokenOverlap": score,
        })
    return sorted(matches, key=lambda item: int(item.get("tokenOverlap") or 0), reverse=True)[:5]


def candidate_news_seeds(news: dict[str, Any], known_questions: list[str], limit: int = 10) -> list[dict[str, Any]]:
    articles = news.get("articles") if isinstance(news.get("articles"), list) else []
    seeds = []
    for article in articles:
        headline = str(article.get("headline") or "")
        if not headline:
            continue
        best_overlap = max([overlap_count(headline, question) for question in known_questions] or [0])
        headline_tokens = tokens(headline)
        if best_overlap >= 2 or len(headline_tokens) < 3:
            continue
        seeds.append({
            "headline": headline,
            "source": article.get("source"),
            "datetime": article.get("datetime"),
            "published": article.get("published"),
            "reason": "fresh-news-without-watchlist-market-map",
            "nextStep": "map to an active market only if wording, settlement source, and resolved-label family can be identified",
        })
    return seeds[:limit]


def collection_plan_for(item: dict[str, Any]) -> dict[str, Any]:
    category = str(item.get("category") or "unknown")
    subject_key = str(item.get("subjectKey") or "unknown")
    base_commands = [
        "npm run --silent bill:prediction-event-news-rss",
        "npm run --silent bill:prediction-label-card-audit",
        "npm run --silent bill:prediction-label-source-manifest",
        "npm run --silent bill:prediction-resolved-outcome-join",
        "npm run --silent bill:prediction-event-market-mapping-plan",
        "npm run --silent bill:prediction-event-lag-requirements",
        "npm run --silent bill:prediction-event-lag-replay",
    ]
    source = item.get("recommendedNextSource") or "closed-market archive with subject-specific settlement labels"
    manual_card = f"/Users/brain/Documents/memorybrain/Research-Catalog/prediction-label-cards/{category}-{subject_key}.md"
    return {
        "sourcePriority": source,
        "manualSettlementCard": manual_card,
        "minimumNewResolvedLabels": {
            "family": max(0, 20 - int(item.get("familyResolvedCount") or 0)),
            "subjectSpecific": max(0, 5 - int(item.get("subjectResolvedCount") or 0)),
        },
        "requiredFields": [
            "venue",
            "externalId",
            "question",
            "closeTime",
            "settlementSourceUrl",
            "outcomeLabel",
            "outcomeWon",
            "marketType",
            "subjectKey",
        ],
        "proofCommands": safe_commands(base_commands),
    }


def build_plan(
    *,
    event_requirements: dict[str, Any],
    event_lag_replay: dict[str, Any] | None = None,
    label_manifest: dict[str, Any],
    watchlist: dict[str, Any],
    news: dict[str, Any],
) -> dict[str, Any]:
    event_lag_replay = event_lag_replay or {}
    coverage = label_manifest.get("coverage") if isinstance(label_manifest.get("coverage"), list) else []
    watch_items = watchlist.get("items") if isinstance(watchlist.get("items"), list) else []
    coverage_by_id = by_external_id(coverage)
    watch_by_id = by_external_id(watch_items)
    mapped_ids = {str(match.get("externalId")) for match in event_requirements.get("eventMarketMatches") or [] if match.get("externalId") is not None}

    all_ids = set(coverage_by_id) | mapped_ids | set(watch_by_id)
    gap_items: list[dict[str, Any]] = []
    for external_id in sorted(all_ids):
        coverage_item = coverage_by_id.get(external_id, {})
        watch_item = watch_by_id.get(external_id, {})
        question = str(coverage_item.get("question") or watch_item.get("question") or "")
        status = str(coverage_item.get("status") or "missing-label-coverage")
        is_mapped = external_id in mapped_ids
        needs_labels = status != "usable-for-research-join"
        if not needs_labels:
            continue
        item = {
            "externalId": external_id,
            "venue": coverage_item.get("venue") or watch_item.get("venue"),
            "question": question,
            "category": coverage_item.get("category"),
            "subjectKey": coverage_item.get("subjectKey"),
            "labelStatus": status,
            "eventMappedFromFreshNews": is_mapped,
            "familyResolvedCount": int(coverage_item.get("familyResolvedCount") or 0),
            "subjectResolvedCount": int(coverage_item.get("subjectResolvedCount") or 0),
            "blockers": list(coverage_item.get("blockers") or ["missing-label-coverage"]),
            "newsMatches": news_matches_for_question(news, question),
            "collectionPlan": collection_plan_for(coverage_item or {"category": "unknown", "subjectKey": external_id}),
            "paperStatus": "blocked",
            "readyForPaper": False,
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
        }
        gap_items.append(item)

    gap_items.sort(
        key=lambda item: (
            not bool(item.get("eventMappedFromFreshNews")),
            status_rank(str(item.get("labelStatus") or "")),
            -int(item.get("familyResolvedCount") or 0),
            str(item.get("externalId") or ""),
        )
    )

    status_counts = Counter(str(item.get("labelStatus")) for item in gap_items)
    blocked_requirements = [
        req.get("id")
        for req in event_requirements.get("requirements") or []
        if isinstance(req, dict) and req.get("status") != "pass"
    ]
    known_questions = [str(item.get("question") or "") for item in coverage] + [str(item.get("question") or "") for item in watch_items]
    commands = [
        "npm run --silent bill:prediction-event-news-rss",
        "npm run --silent bill:prediction-label-card-audit",
        "npm run --silent bill:prediction-label-source-manifest",
        "npm run --silent bill:prediction-event-label-gap-plan",
        "npm run --silent bill:prediction-event-market-mapping-plan",
        "npm run --silent bill:prediction-event-lag-requirements",
        "npm run --silent bill:prediction-event-lag-replay",
        "npm run --silent bill:alpha-frontier-queue",
    ]
    replay_blockers = event_lag_replay.get("blockers") if isinstance(event_lag_replay.get("blockers"), list) else []
    replay_missing = event_lag_replay.get("missingReasonCounts") if isinstance(event_lag_replay.get("missingReasonCounts"), dict) else {}
    replay_needs_forward_capture = (
        event_lag_replay.get("decision") == "research-only-event-lag-replay-blocked"
        and (
            "too-few-complete-event-windows" in replay_blockers
            or int(replay_missing.get("no-pre-event-quote-within-window") or 0) > 0
            or int(replay_missing.get("no-quotes-for-clob-token") or 0) > 0
        )
    )
    requirement_needs_forward_capture = "clob-around-event-window" in blocked_requirements
    forward_capture_required = replay_needs_forward_capture or requirement_needs_forward_capture
    if gap_items:
        decision = "research-only-label-gaps-remain"
        next_action = "Collect subject-specific resolved labels and settlement cards for mapped event markets before any event-lag replay."
    elif blocked_requirements:
        decision = "research-only-label-gaps-cleared-but-event-requirements-blocked"
        next_action = (
            "Keep standing public CLOB capture running and resolve the remaining non-label event-lag requirements before paper review; no paper/live approval."
            if forward_capture_required
            else "Resolve the remaining non-label event-lag requirements before paper review; no paper/live approval."
        )
    elif replay_needs_forward_capture:
        decision = "research-only-labels-clear-forward-capture-required"
        next_action = "Labels are not the blocker; run standing public CLOB capture before/through future news, then rerun no-lookahead event-lag replay."
    else:
        decision = "research-only-label-gap-plan-clear-for-replay"
        next_action = "Run no-lookahead event-lag replay; this still does not approve paper/live execution."
    return {
        "command": "prediction-event-label-gap-plan",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "sourceArtifacts": {
            "eventRequirements": str(EVENT_REQUIREMENTS),
            "eventLagReplay": str(EVENT_LAG_REPLAY),
            "labelManifest": str(LABEL_MANIFEST),
            "watchlist": str(WATCHLIST),
            "news": str(NEWS),
        },
        "eventLagDecision": event_requirements.get("decision", "missing"),
        "eventLagReplay": {
            "decision": event_lag_replay.get("decision", "missing"),
            "completeEventCount": event_lag_replay.get("completeEventCount"),
            "completeWindowCount": event_lag_replay.get("completeWindowCount"),
            "repricedWindowCount": event_lag_replay.get("repricedWindowCount"),
            "blockers": replay_blockers,
            "missingReasonCounts": replay_missing,
            "forwardCaptureRequired": replay_needs_forward_capture,
        },
        "eventRequirementForwardCaptureRequired": requirement_needs_forward_capture,
        "overallForwardCaptureRequired": forward_capture_required,
        "blockedRequirements": blocked_requirements,
        "gapCount": len(gap_items),
        "eventMappedGapCount": sum(1 for item in gap_items if item.get("eventMappedFromFreshNews")),
        "labelStatusCounts": dict(status_counts),
        "gapItems": gap_items,
        "freshNewsUnmappedSeeds": candidate_news_seeds(news, known_questions),
        "nextCommands": safe_commands(commands),
        "decision": decision,
        "nextAction": next_action,
        "hardRules": [
            "Do not widen token matching to create fake event-market links.",
            "Do not treat RSS sentiment, headlines, or broad priors as trade signals.",
            "Every resolved label needs settlement wording and source provenance.",
            "No funding, paper, demo, live, sizing, or broker route is approved by this artifact.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Event Label Gap Plan - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only plan for the prediction-market news/event lag lane. This page is a collection checklist, not a trading approval.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Event-lag decision: `{payload.get('eventLagDecision')}`",
        f"- Gap count: `{payload.get('gapCount')}`",
        f"- Event-mapped gaps: `{payload.get('eventMappedGapCount')}`",
        f"- Blocked requirements: `{payload.get('blockedRequirements')}`",
        f"- Label statuses: `{payload.get('labelStatusCounts')}`",
        "",
        "## Gap Items",
        "",
    ]
    for item in payload.get("gapItems") or []:
        plan = item.get("collectionPlan") or {}
        minimum = plan.get("minimumNewResolvedLabels") or {}
        lines.extend([
            f"### {item.get('externalId')} - {item.get('labelStatus')}",
            "",
            f"- Question: {item.get('question')}",
            f"- Category / subject: `{item.get('category')}` / `{item.get('subjectKey')}`",
            f"- Fresh-news mapped: `{item.get('eventMappedFromFreshNews')}`",
            f"- Current labels: family `{item.get('familyResolvedCount')}`, subject `{item.get('subjectResolvedCount')}`",
            f"- Need new labels: family `{minimum.get('family')}`, subject `{minimum.get('subjectSpecific')}`",
            f"- Next source: {plan.get('sourcePriority')}",
            f"- Settlement card: `{plan.get('manualSettlementCard')}`",
            "",
        ])
    lines.extend(["## Next Commands", ""])
    for command in payload.get("nextCommands") or []:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    payload = build_plan(
        event_requirements=read_json(EVENT_REQUIREMENTS),
        event_lag_replay=read_json(EVENT_LAG_REPLAY),
        label_manifest=read_json(LABEL_MANIFEST),
        watchlist=read_json(WATCHLIST),
        news=read_json(NEWS),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
