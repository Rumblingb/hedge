#!/usr/bin/env python3
"""Map fresh news events to active prediction markets for event-lag research.

Research-only. This is stricter than broad token overlap: a mapping candidate
must share a subject token and an event-family token with the headline, and it
must come from active/narrow market snapshots with settlement text.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
SNAPSHOT_ROOT = ROOT / ".rumbling-hedge" / "research" / "prediction-narrow-snapshots"
NEWS = STATE / "news-sentiment.json"
OUT = STATE / "prediction-event-market-mapping-plan.latest.json"
VAULT = Path.home() / "Documents" / "memorybrain"

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "will",
    "this",
    "that",
    "market",
    "markets",
    "prediction",
    "latest",
    "update",
    "news",
    "yes",
    "no",
    "new",
}

SUBJECT_TERMS = {
    "argentina",
    "brazil",
    "china",
    "fed",
    "fomc",
    "france",
    "iran",
    "israel",
    "kalshi",
    "polymarket",
    "russia",
    "trump",
    "ukraine",
    "us",
    "u.s",
    "usa",
}

ACTOR_ALIASES = {
    "america": "us",
    "american": "us",
    "fed": "fed",
    "federal": "fed",
    "fomc": "fed",
    "israeli": "israel",
    "united": "us",
    "usa": "us",
    "us": "us",
    "states": "us",
}

FAMILY_TERMS = {
    "agreement",
    "ban",
    "ceasefire",
    "deal",
    "election",
    "extension",
    "inflation",
    "lawsuit",
    "oil",
    "peace",
    "probe",
    "rate",
    "rates",
    "strike",
}

FAMILY_GROUPS = {
    "geopolitical-agreement": {"agreement", "ceasefire", "deal", "extension", "peace"},
    "macro-rates": {"fed", "fomc", "inflation", "rate", "rates", "bps", "hike", "hiking"},
    "energy": {"oil", "opec"},
    "election": {"election"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"prediction-event-market-mapping-plan-{current_utc_date()}.md"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {} if path.suffix == ".json" else []


def tokens(text: Any) -> set[str]:
    normalized = str(text or "").lower().replace("u.s.", "us").replace("u.s", "us")
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 2 and token not in STOPWORDS
    }


def subject_tokens(text: Any) -> set[str]:
    toks = tokens(text)
    if "united" in toks and "states" in toks:
        toks.add("us")
    return toks & SUBJECT_TERMS


def actor_tokens(text: Any) -> set[str]:
    toks = tokens(text)
    actors = (toks & SUBJECT_TERMS) | {ACTOR_ALIASES[token] for token in toks if token in ACTOR_ALIASES}
    if "united" in toks and "states" in toks:
        actors.add("us")
    return {actor for actor in actors if actor not in {"kalshi", "polymarket"}}


def family_tokens(text: Any) -> set[str]:
    return tokens(text) & FAMILY_TERMS


def event_families(text: Any) -> set[str]:
    toks = tokens(text)
    families = {
        family
        for family, terms in FAMILY_GROUPS.items()
        if toks & terms
    }
    return families or {"unknown"}


def load_markets(snapshot_root: Path, categories: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for category in categories:
        path = snapshot_root / f"{category}.json"
        data = read_json(path)
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            question = str(item.get("marketQuestion") or item.get("question") or "")
            settlement = str(item.get("settlementText") or "")
            if not question or not settlement:
                continue
            row = dict(item)
            row["category"] = category
            rows.append(row)
    return rows


def article_rows(news: dict[str, Any]) -> list[dict[str, Any]]:
    articles = news.get("articles") if isinstance(news.get("articles"), list) else []
    return [article for article in articles if isinstance(article, dict) and article.get("headline")]


def candidate_for(article: dict[str, Any], market: dict[str, Any]) -> dict[str, Any] | None:
    headline = str(article.get("headline") or "")
    question = str(market.get("marketQuestion") or market.get("question") or "")
    headline_subjects = subject_tokens(headline)
    market_subjects = subject_tokens(question + " " + str(market.get("settlementText") or ""))
    headline_actors = actor_tokens(headline)
    market_actors = actor_tokens(question + " " + str(market.get("settlementText") or ""))
    subject_overlap = headline_subjects & market_subjects
    if not subject_overlap:
        return None
    headline_family = family_tokens(headline)
    market_family = family_tokens(question + " " + str(market.get("settlementText") or ""))
    family_overlap = headline_family & market_family
    if not family_overlap:
        return None
    headline_event_families = event_families(headline)
    market_event_families = event_families(question + " " + str(market.get("settlementText") or ""))
    event_family_overlap = sorted((headline_event_families & market_event_families) - {"unknown"})
    overlap = tokens(headline) & tokens(question)
    score = len(subject_overlap) * 3 + len(family_overlap) * 2 + len(overlap)
    if score < 5:
        return None
    mapping_status = "candidate-review-required"
    specificity_flags: list[str] = []
    if len(headline_event_families - {"unknown"}) > 1:
        mapping_status = "ambiguous-headline-family-review-required"
        specificity_flags.append("headline-has-multiple-event-families")
    if "geopolitical-agreement" in market_event_families and len(market_actors - headline_actors) > 0:
        if mapping_status == "candidate-review-required":
            mapping_status = "counterparty-review-required"
        specificity_flags.append("market-counterparty-not-explicit-in-headline")
    if not event_family_overlap and "unknown" not in headline_event_families and "unknown" not in market_event_families:
        mapping_status = "event-family-mismatch-review-required"
        specificity_flags.append("event-family-mismatch")
    return {
        "externalId": market.get("externalId"),
        "venue": market.get("venue"),
        "category": market.get("category"),
        "question": question,
        "headline": headline,
        "source": article.get("source"),
        "articleDatetime": article.get("datetime"),
        "published": article.get("published"),
        "subjectOverlap": sorted(subject_overlap),
        "familyOverlap": sorted(family_overlap),
        "headlineEventFamilies": sorted(headline_event_families),
        "marketEventFamilies": sorted(market_event_families),
        "eventFamilyOverlap": event_family_overlap,
        "headlineActors": sorted(headline_actors),
        "marketActors": sorted(market_actors),
        "missingHeadlineActors": sorted(market_actors - headline_actors),
        "tokenOverlap": sorted(overlap),
        "score": score,
        "price": market.get("price"),
        "bestBid": market.get("bestBid"),
        "bestAsk": market.get("bestAsk"),
        "spreadPct": market.get("spreadPct"),
        "topBookDepth": market.get("topBookDepth"),
        "clobTokenId": market.get("clobTokenId"),
        "settlementTextPresent": bool(market.get("settlementText")),
        "mappingStatus": mapping_status,
        "specificityFlags": specificity_flags,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }


def build_plan(
    *,
    news: dict[str, Any],
    markets: list[dict[str, Any]],
    minimum_candidates: int = 3,
    top_n: int = 20,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for article in article_rows(news):
        for market in markets:
            candidate = candidate_for(article, market)
            if candidate:
                candidates.append(candidate)
    candidates.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            str(item.get("headline") or ""),
            str(item.get("externalId") or ""),
        )
    )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in candidates:
        key = (str(item.get("headline") or ""), str(item.get("externalId") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    selected = deduped[:top_n]
    by_category = Counter(str(item.get("category") or "missing") for item in selected)
    headline_family_fanout: dict[str, dict[str, Any]] = {}
    for item in selected:
        headline = str(item.get("headline") or "")
        if not headline:
            continue
        row = headline_family_fanout.setdefault(headline, {
            "headline": headline,
            "headlineEventFamilies": item.get("headlineEventFamilies", []),
            "marketEventFamilies": set(),
            "headlineActors": item.get("headlineActors", []),
            "marketActorSets": set(),
            "counterpartyIssueCount": 0,
            "candidateExternalIds": [],
            "mappingStatuses": Counter(),
        })
        row["marketEventFamilies"].update(item.get("marketEventFamilies", []))
        row["marketActorSets"].add(tuple(item.get("marketActors") or []))
        if "market-counterparty-not-explicit-in-headline" in (item.get("specificityFlags") or []):
            row["counterpartyIssueCount"] += 1
        row["candidateExternalIds"].append(item.get("externalId"))
        row["mappingStatuses"][str(item.get("mappingStatus") or "missing")] += 1
    normalized_fanout = []
    ambiguous_fanout = []
    counterparty_fanout = []
    ambiguous_headline_count = 0
    counterparty_fanout_count = 0
    for row in headline_family_fanout.values():
        market_families = sorted(row["marketEventFamilies"])
        market_actor_sets = sorted([list(item) for item in row["marketActorSets"]])
        statuses = dict(row["mappingStatuses"])
        ambiguous = (
            len(set(row["headlineEventFamilies"]) - {"unknown"}) > 1
            or len(set(market_families) - {"unknown"}) > 1
            or any("ambiguous" in status or "mismatch" in status for status in statuses)
        )
        counterparty_ambiguous = (
            len(market_actor_sets) > 1
            or int(row.get("counterpartyIssueCount") or 0) > 0
            or any("counterparty" in status for status in statuses)
        )
        if ambiguous:
            ambiguous_headline_count += 1
        if counterparty_ambiguous:
            counterparty_fanout_count += 1
        fanout_row = {
            "headline": row["headline"],
            "headlineEventFamilies": row["headlineEventFamilies"],
            "marketEventFamilies": market_families,
            "headlineActors": row["headlineActors"],
            "marketActorSets": market_actor_sets,
            "counterpartyIssueCount": row.get("counterpartyIssueCount", 0),
            "candidateExternalIds": row["candidateExternalIds"][:12],
            "mappingStatuses": statuses,
            "ambiguous": ambiguous,
            "counterpartyAmbiguous": counterparty_ambiguous,
        }
        normalized_fanout.append(fanout_row)
        if ambiguous:
            ambiguous_fanout.append(fanout_row)
        if counterparty_ambiguous:
            counterparty_fanout.append(fanout_row)
    blockers: list[str] = []
    if len(selected) < minimum_candidates:
        blockers.append("too-few-strict-event-market-candidates")
    if ambiguous_headline_count:
        blockers.append("ambiguous-headline-event-family-fanout")
    if counterparty_fanout_count:
        blockers.append("ambiguous-headline-counterparty-fanout")
    return {
        "command": "prediction-event-market-mapping-plan",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForPaper": False,
        "readyForExecution": False,
        "minimumCandidates": minimum_candidates,
        "candidateCount": len(selected),
        "categories": dict(by_category),
        "ambiguousHeadlineCount": ambiguous_headline_count,
        "ambiguousCounterpartyHeadlineCount": counterparty_fanout_count,
        "headlineFamilyFanout": normalized_fanout,
        "ambiguousHeadlineFamilyFanout": ambiguous_fanout,
        "ambiguousHeadlineCounterpartyFanout": counterparty_fanout,
        "candidates": selected,
        "blockers": blockers,
        "decision": "research-only-event-market-mapping-candidates-ready" if not blockers else "research-only-event-market-mapping-blocked",
        "hardRules": [
            "A mapping candidate is not a signal or paper-trade approval.",
            "Subject and event-family overlap are required; broad prediction-market headlines do not qualify.",
            "Headlines with multiple event families remain mapping-review only until a single market family is selected.",
            "Geopolitical headlines must identify the relevant counterparties before a market family can become paper evidence.",
            "Geopolitics mappings still need no-lookahead replay and fillability/spread review before paper.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_at = str(payload.get("generatedAt") or "")
    report_date = generated_at[:10] if len(generated_at) >= 10 else datetime.now(timezone.utc).date().isoformat()
    lines = [
        f"# Prediction Event Market Mapping Plan - {report_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only strict mapping candidates from fresh news to active prediction markets.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Candidate count: `{payload.get('candidateCount')}`",
        f"- Minimum candidates: `{payload.get('minimumCandidates')}`",
        f"- Categories: `{payload.get('categories')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        f"- Ambiguous headline count: `{payload.get('ambiguousHeadlineCount')}`",
        f"- Ambiguous counterparty count: `{payload.get('ambiguousCounterpartyHeadlineCount')}`",
        "",
        "## Ambiguous Headline Fanout",
        "",
    ]
    for item in payload.get("ambiguousHeadlineFamilyFanout") or []:
        lines.extend([
            f"- Headline: {item.get('headline')}",
            f"  - Headline families: `{item.get('headlineEventFamilies')}`",
            f"  - Market families: `{item.get('marketEventFamilies')}`",
            f"  - Headline actors: `{item.get('headlineActors')}`",
            f"  - Market actor sets: `{item.get('marketActorSets')}`",
            f"  - Mapping statuses: `{item.get('mappingStatuses')}`",
            f"  - Candidate ids: `{item.get('candidateExternalIds')}`",
        ])
    lines.extend([
        "",
        "## Ambiguous Counterparty Fanout",
        "",
    ])
    for item in payload.get("ambiguousHeadlineCounterpartyFanout") or []:
        lines.extend([
            f"- Headline: {item.get('headline')}",
            f"  - Headline actors: `{item.get('headlineActors')}`",
            f"  - Market actor sets: `{item.get('marketActorSets')}`",
            f"  - Candidate ids: `{item.get('candidateExternalIds')}`",
        ])
    lines.extend([
        "",
        "## Candidates",
        "",
    ])
    for item in payload.get("candidates") or []:
        lines.extend([
            f"### {item.get('externalId')}",
            "",
            f"- Headline: {item.get('headline')}",
            f"- Market: {item.get('question')}",
            f"- Source: {item.get('source')}",
            f"- Subject overlap: `{item.get('subjectOverlap')}`",
            f"- Family overlap: `{item.get('familyOverlap')}`",
            f"- Price/bid/ask: `{item.get('price')}` / `{item.get('bestBid')}` / `{item.get('bestAsk')}`",
            f"- Mapping status: `{item.get('mappingStatus')}`",
            "",
        ])
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--news", default=str(NEWS))
    parser.add_argument("--snapshot-root", default=str(SNAPSHOT_ROOT))
    parser.add_argument("--categories", default="geopolitics,politics,macro-rates,commodities,equities")
    parser.add_argument("--minimum-candidates", type=int, default=3)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(default_markdown_path()))
    args = parser.parse_args()

    categories = [part.strip() for part in args.categories.split(",") if part.strip()]
    payload = build_plan(
        news=read_json(Path(args.news)),
        markets=load_markets(Path(args.snapshot_root), categories),
        minimum_candidates=args.minimum_candidates,
        top_n=args.top_n,
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
