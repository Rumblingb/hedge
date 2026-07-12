#!/usr/bin/env python3
"""Define requirements for prediction-market news/event lag research.

Research-only. This turns the thesis "price lags news" into a concrete
evidence contract: timestamp provenance, market mapping, no-lookahead windows,
CLOB observations around the event, resolved labels, and fillability.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "prediction-event-lag-requirements.latest.json"
VAULT = Path.home() / "Documents/memorybrain"

NEWS = STATE / "news-sentiment.json"
WATCHLIST = STATE / "prediction-research-watchlist.latest.json"
LABEL_MANIFEST = STATE / "prediction-label-source-manifest.latest.json"
CLOB_AUDIT = STATE / "prediction-clob-microstructure-feature-audit.latest.json"
EVENT_MAPPING_PLAN = STATE / "prediction-event-market-mapping-plan.latest.json"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def current_utc_date() -> str:
    return now_utc().date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-event-lag-requirements-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_dt(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if not isinstance(value, str) or not value:
        return None
    text = value
    if text.endswith("+00:00Z"):
        text = text[:-1]
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def token_set(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 3 and token not in {"will", "the", "and", "for", "with", "from", "new", "yes", "no"}
    }


def overlap(a: set[str], b: set[str]) -> int:
    return len(a & b)


def news_age_hours(news: dict[str, Any], now: datetime | None = None) -> float | None:
    now = now or now_utc()
    generated = parse_dt(news.get("generated_at") or news.get("generatedAt"))
    if not generated:
        return None
    return round((now - generated).total_seconds() / 3600, 3)


def event_market_matches(news: dict[str, Any], watchlist: dict[str, Any], min_token_overlap: int = 2) -> list[dict[str, Any]]:
    articles = news.get("articles") if isinstance(news.get("articles"), list) else []
    items = watchlist.get("items") if isinstance(watchlist.get("items"), list) else []
    matches: list[dict[str, Any]] = []
    for item in items:
        question = str(item.get("question") or "")
        q_tokens = token_set(question)
        best: dict[str, Any] | None = None
        for article in articles:
            headline = str(article.get("headline") or "")
            score = overlap(q_tokens, token_set(headline))
            if score < min_token_overlap:
                continue
            candidate = {
                "externalId": item.get("externalId"),
                "question": question,
                "headline": headline,
                "source": article.get("source"),
                "articleDatetime": article.get("datetime"),
                "tokenOverlap": score,
            }
            if best is None or score > int(best.get("tokenOverlap") or 0):
                best = candidate
        if best:
            matches.append(best)
    return matches


def requirement(
    *,
    req_id: str,
    title: str,
    status: str,
    current: dict[str, Any],
    needed: dict[str, Any],
    proof_commands: list[str],
    blocks: list[str],
) -> dict[str, Any]:
    return {
        "id": req_id,
        "title": title,
        "status": status,
        "current": current,
        "needed": needed,
        "proofCommands": proof_commands,
        "blocks": blocks,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }


def build_requirements(
    *,
    news: dict[str, Any],
    watchlist: dict[str, Any],
    label_manifest: dict[str, Any],
    clob_audit: dict[str, Any],
    event_mapping_plan: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or now_utc()
    age = news_age_hours(news, now)
    matches = event_market_matches(news, watchlist)
    event_mapping_plan = event_mapping_plan or {}
    strict_mapping_candidates = event_mapping_plan.get("candidates") if isinstance(event_mapping_plan.get("candidates"), list) else []
    mapping_count = max(len(matches), len(strict_mapping_candidates))
    label_usable = int(label_manifest.get("usableForResearchJoinCount") or 0)
    ready_feature_count = int(clob_audit.get("readyFeatureCount") or 0)
    articles = news.get("articles") if isinstance(news.get("articles"), list) else []
    fetch_errors = news.get("fetchErrors") if isinstance(news.get("fetchErrors"), dict) else {}
    requirements = [
        requirement(
            req_id="fresh-timestamped-news-source",
            title="News/event data must be fresh and timestamped",
            status="pass" if age is not None and 0 <= age <= 24 and len(articles) >= 10 else "blocked",
            current={
                "ageHours": age,
                "articleCount": len(articles),
                "generatedAt": news.get("generated_at") or news.get("generatedAt"),
                "newsStatus": news.get("status"),
                "dataUsable": news.get("dataUsable"),
                "apiKeyStatus": news.get("api_key_status"),
                "fetchErrors": fetch_errors,
            },
            needed={"maxAgeHours": 24, "minimumArticles": 10, "eventTimestampRequired": True, "sourceRequired": True},
            proof_commands=[
                "npm run --silent bill:finnhub-news",
                "npm run --silent bill:prediction-event-news-rss",
                "npm run --silent bill:prediction-event-lag-requirements",
            ],
            blocks=["event-lag study", "news-first scanner"],
        ),
        requirement(
            req_id="event-to-market-mapping",
            title="News events must map to prediction markets without broad semantic guessing",
            status="pass" if mapping_count >= 3 else "blocked",
            current={
                "matchCount": mapping_count,
                "watchlistMatchCount": len(matches),
                "strictMappingCandidateCount": len(strict_mapping_candidates),
                "matches": matches[:10],
                "strictMappingCandidates": strict_mapping_candidates[:10],
                "minimumTokenOverlap": 2,
            },
            needed={"minimumMappedMarkets": 3, "minimumTokenOverlap": 2, "subjectSpecificMapping": True, "settlementTextPresent": True},
            proof_commands=[
                "npm run --silent bill:prediction-event-market-mapping-plan",
                "npm run --silent bill:prediction-event-lag-requirements",
            ],
            blocks=["event-lag replay", "watchlist promotion"],
        ),
        requirement(
            req_id="resolved-label-coverage",
            title="Mapped event markets need resolved label coverage",
            status="pass" if label_usable >= 3 else "blocked",
            current={"usableForResearchJoinCount": label_usable, "statusCounts": label_manifest.get("statusCounts", {})},
            needed={"minimumUsableResearchJoins": 3, "subjectSpecificResolvedHistory": True},
            proof_commands=[
                "npm run --silent bill:prediction-label-source-manifest",
                "npm run --silent bill:prediction-resolved-outcome-join",
            ],
            blocks=["paper review", "event-lag expectancy estimate"],
        ),
        requirement(
            req_id="clob-around-event-window",
            title="CLOB observations must cover pre/post event windows",
            status="pass" if ready_feature_count >= 3 else "blocked",
            current={"readyFeatureCount": ready_feature_count, "capture": clob_audit.get("capture", {})},
            needed={"preEventMinutes": 30, "postEventMinutes": 120, "readyFeatureFamilies": 3, "fillabilityReview": True},
            proof_commands=[
                "npm run --silent bill:polymarket-clob-recorder",
                "npm run --silent bill:prediction-clob-microstructure-audit",
            ],
            blocks=["lag measurement", "spread/fee stress"],
        ),
    ]
    blocked = [item for item in requirements if item["status"] != "pass"]
    return {
        "command": "prediction-event-lag-requirements",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "requirements": requirements,
        "passCount": len(requirements) - len(blocked),
        "blockedCount": len(blocked),
        "eventMarketMatches": matches,
        "decision": "research-only-event-lag-requirements-not-cleared" if blocked else "research-only-event-lag-requirements-cleared",
        "nextAction": (
            "Refresh timestamped news, map events to markets, and collect CLOB around event windows before testing lag alpha."
            if blocked
            else "Run a no-lookahead event-lag replay; still no paper/live route."
        ),
        "hardRules": [
            "No lookahead: event timestamp must precede all measured market repricing.",
            "Sentiment alone is not alpha evidence.",
            "Broad token overlap is a triage aid only; paper review requires subject-specific mapping and resolved labels.",
            "No item here approves funding, paper, demo, live, sizing, or broker routing.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Prediction Event Lag Requirements - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only checklist for news-first prediction-market lag studies. This page does not approve paper or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Passed: `{payload.get('passCount')}`",
        f"- Blocked: `{payload.get('blockedCount')}`",
        "",
        "## Requirements",
        "",
    ]
    for item in payload.get("requirements") or []:
        lines.extend([
            f"### {item.get('id')}",
            "",
            f"- Title: {item.get('title')}",
            f"- Status: `{item.get('status')}`",
            f"- Current: `{item.get('current')}`",
            f"- Needed: `{item.get('needed')}`",
            f"- Blocks: `{item.get('blocks')}`",
            "- Proof commands:",
        ])
        for command in item.get("proofCommands") or []:
            lines.append(f"  - `{command}`")
        lines.append("")
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    payload = build_requirements(
        news=read_json(NEWS),
        watchlist=read_json(WATCHLIST),
        label_manifest=read_json(LABEL_MANIFEST),
        clob_audit=read_json(CLOB_AUDIT),
        event_mapping_plan=read_json(EVENT_MAPPING_PLAN),
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
