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
    "bitcoin",
    "btc",
    "china",
    "colombia",
    "fed",
    "fomc",
    "france",
    "ethereum",
    "eth",
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

SUBJECT_ALIASES = {
    "btc": "bitcoin",
    "eth": "ethereum",
}

NON_ACTOR_SUBJECTS = {"bitcoin", "btc", "ethereum", "eth"}

JURISDICTION_TERMS = {
    "argentina",
    "brazil",
    "china",
    "colombia",
    "france",
    "iran",
    "israel",
    "russia",
    "ukraine",
    "us",
}

GEOPOLITICAL_TOPIC_GROUPS = {
    "peace": {"ceasefire", "peace", "truce"},
    "nuclear": {"enrichment", "nuclear", "uranium"},
    "territory": {"control", "island", "kharg", "territory"},
    "shipping": {"fees", "hormuz", "shipping", "strait", "transit"},
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
    "above",
    "agreement",
    "ban",
    "below",
    "ceasefire",
    "deal",
    "election",
    "extension",
    "inflation",
    "hit",
    "hits",
    "lawsuit",
    "oil",
    "peace",
    "price",
    "probe",
    "rally",
    "rallies",
    "rate",
    "rates",
    "reach",
    "reaches",
    "strike",
}

FAMILY_GROUPS = {
    "geopolitical-agreement": {"agreement", "ceasefire", "deal", "extension", "peace"},
    "macro-rates": {"fed", "fomc", "inflation", "rate", "rates", "bps", "hike", "hiking"},
    "energy": {"oil", "opec"},
    "election": {"election"},
    "crypto-price": {
        "above",
        "below",
        "dip",
        "dips",
        "drop",
        "drops",
        "crash",
        "crashes",
        "fall",
        "falls",
        "hit",
        "hits",
        "price",
        "rally",
        "rallies",
        "reach",
        "reaches",
        "rise",
        "rises",
        "slide",
        "slides",
        "surge",
        "surges",
        "tumble",
        "tumbles",
    },
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
    subjects = toks & SUBJECT_TERMS
    subjects.update(SUBJECT_ALIASES[token] for token in toks if token in SUBJECT_ALIASES)
    return subjects - set(SUBJECT_ALIASES)


def actor_tokens(text: Any) -> set[str]:
    toks = tokens(text)
    actors = (toks & SUBJECT_TERMS) | {ACTOR_ALIASES[token] for token in toks if token in ACTOR_ALIASES}
    if "united" in toks and "states" in toks:
        actors.add("us")
    return {
        actor
        for actor in actors
        if actor not in {"kalshi", "polymarket"} | NON_ACTOR_SUBJECTS
    }


def jurisdiction_tokens(text: Any) -> set[str]:
    return actor_tokens(text) & JURISDICTION_TERMS


def geopolitical_topics(text: Any) -> set[str]:
    toks = tokens(text)
    return {topic for topic, terms in GEOPOLITICAL_TOPIC_GROUPS.items() if toks & terms}


def family_tokens(text: Any) -> set[str]:
    toks = tokens(text)
    families = toks & FAMILY_TERMS
    if "deal" in families and len(actor_tokens(text)) < 2 and not (toks & {"agreement", "ceasefire", "peace"}):
        families.remove("deal")
    return families


def event_families(text: Any) -> set[str]:
    toks = tokens(text)
    families: set[str] = set()
    for family, terms in FAMILY_GROUPS.items():
        matches = toks & terms
        if family == "crypto-price" and not (subject_tokens(text) & {"bitcoin", "ethereum"}):
            continue
        if family == "geopolitical-agreement" and matches == {"deal"} and len(actor_tokens(text)) < 2:
            continue
        if matches:
            families.add(family)
    return families or {"unknown"}


def crypto_directions(text: Any) -> set[str]:
    toks = tokens(text)
    directions: set[str] = set()
    if toks & {
        "above", "gain", "gains", "greater", "high", "higher", "jump", "jumps",
        "rally", "rallies", "reach", "reaches", "rise", "rises", "surge", "surges",
    }:
        directions.add("up")
    if toks & {
        "below", "crash", "crashes", "dip", "dips", "drop", "drops", "fall", "falls", "less",
        "low", "lower", "plunge", "plunges", "slide", "slides", "tumble", "tumbles",
    }:
        directions.add("down")
    return directions


def crypto_price_mentions(text: Any) -> list[tuple[float, int]]:
    raw = str(text or "")
    matches = list(re.finditer(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)(?:\s*([kKmMbB])\b)?", raw))
    matches.extend(re.finditer(r"\b([0-9]+(?:\.[0-9]+)?)\s*([kKmMbB])\b", raw))
    mentions: list[tuple[float, int]] = []
    for match in sorted(matches, key=lambda item: item.start()):
        number, suffix = match.group(1), match.group(2) or ""
        try:
            value = float(number.replace(",", ""))
        except ValueError:
            continue
        if suffix.lower() == "k":
            value *= 1_000
        elif suffix.lower() == "m":
            value *= 1_000_000
        elif suffix.lower() == "b":
            value *= 1_000_000_000
        mention = (value, match.start())
        if mention not in mentions:
            mentions.append(mention)
    return mentions


def crypto_price_values(text: Any) -> list[float]:
    values: list[float] = []
    for value, _ in crypto_price_mentions(text):
        if value not in values:
            values.append(value)
    return values


def crypto_price_values_for_subject(text: Any, subject: str) -> list[float]:
    raw = str(text or "").lower()
    aliases = {"bitcoin": {"bitcoin", "btc"}, "ethereum": {"ethereum", "eth"}}
    subject_mentions: list[tuple[str, int]] = []
    for canonical, names in aliases.items():
        for name in names:
            subject_mentions.extend((canonical, match.start()) for match in re.finditer(rf"\b{re.escape(name)}\b", raw))
    values: list[float] = []
    plausible_ranges = {"bitcoin": (1_000.0, 1_000_000.0), "ethereum": (100.0, 100_000.0)}
    plausible_low, plausible_high = plausible_ranges.get(subject, (0.0, float("inf")))
    for value, position in crypto_price_mentions(text):
        if not subject_mentions:
            continue
        closest_subject, _ = min(subject_mentions, key=lambda item: abs(item[1] - position))
        if closest_subject == subject and plausible_low <= value <= plausible_high and value not in values:
            values.append(value)
    return values


def crypto_market_value_matches(headline: Any, question: Any, subject: str) -> bool:
    headline_values = crypto_price_values_for_subject(headline, subject)
    market_values = crypto_price_values_for_subject(question, subject)
    if not headline_values or not market_values:
        return False
    toks = tokens(question)
    low, high = min(market_values), max(market_values)
    if "between" in toks and len(market_values) >= 2:
        return any(low <= value <= high for value in headline_values)
    threshold = market_values[0]
    if toks & {"less", "below", "under"}:
        return any(value < threshold for value in headline_values)
    if toks & {"above", "greater", "higher", "over"}:
        return any(value > threshold for value in headline_values)
    tolerance = max(500.0, threshold * 0.01)
    return any(abs(value - threshold) <= tolerance for value in headline_values)


def rate_directions(text: Any) -> set[str]:
    toks = tokens(text)
    directions: set[str] = set()
    if toks & {"hike", "hikes", "hiking", "increase", "increases", "raise", "raises", "raised", "tighten", "tightening"}:
        directions.add("up")
    if toks & {"cut", "cuts", "cutting", "decrease", "decreases", "lower", "lowers", "lowered", "easing"}:
        directions.add("down")
    normalized = " ".join(str(text or "").lower().split())
    if "no change" in normalized or "unchanged" in toks or "hold" in toks:
        directions.add("flat")
    return directions


def article_date(article: dict[str, Any]) -> datetime:
    value = article.get("datetime") or article.get("published")
    try:
        if isinstance(value, (int, float)):
            seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def market_deadline(market: dict[str, Any], *, reference: datetime) -> datetime | None:
    question = str(market.get("marketQuestion") or market.get("question") or "")
    match = re.search(
        r"\bby\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b",
        question,
        flags=re.IGNORECASE,
    )
    if match:
        try:
            month = datetime.strptime(match.group(1), "%B").month
            year = int(match.group(3)) if match.group(3) else reference.year
            return datetime(year, month, int(match.group(2)), 23, 59, 59, tzinfo=timezone.utc)
        except ValueError:
            pass
    for key in ("expiry", "endDate", "endDateIso"):
        value = market.get(key)
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def market_event_date(market: dict[str, Any], *, reference: datetime):
    question = str(market.get("marketQuestion") or market.get("question") or "")
    match = re.search(
        r"\bon\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b",
        question,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    try:
        month = datetime.strptime(match.group(1), "%B").month
        year = int(match.group(3)) if match.group(3) else reference.year
        return datetime(year, month, int(match.group(2)), tzinfo=timezone.utc).date()
    except ValueError:
        return None


def market_active_for_article(article: dict[str, Any], market: dict[str, Any]) -> bool:
    published_at = article_date(article)
    deadline = market_deadline(market, reference=published_at)
    return deadline is None or deadline.date() >= published_at.date()


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
    if not market_active_for_article(article, market):
        return None
    headline = str(article.get("headline") or "")
    question = str(market.get("marketQuestion") or market.get("question") or "")
    published_at = article_date(article)
    event_date = market_event_date(market, reference=published_at)
    if event_date is not None and event_date != published_at.date():
        return None
    headline_subjects = subject_tokens(headline)
    market_subjects = subject_tokens(question + " " + str(market.get("settlementText") or ""))
    headline_actors = actor_tokens(headline)
    market_actors = actor_tokens(question + " " + str(market.get("settlementText") or ""))
    headline_jurisdictions = jurisdiction_tokens(headline)
    market_jurisdictions = jurisdiction_tokens(question + " " + str(market.get("settlementText") or ""))
    subject_overlap = headline_subjects & market_subjects
    if not subject_overlap:
        return None
    headline_family = family_tokens(headline)
    market_family = family_tokens(question + " " + str(market.get("settlementText") or ""))
    family_overlap = headline_family & market_family
    headline_event_families = event_families(headline)
    market_event_families = event_families(question + " " + str(market.get("settlementText") or ""))
    event_family_overlap = sorted((headline_event_families & market_event_families) - {"unknown"})
    if (
        "election" in event_family_overlap
        and headline_jurisdictions
        and market_jurisdictions
        and headline_jurisdictions != market_jurisdictions
    ):
        return None
    if "geopolitical-agreement" in event_family_overlap:
        headline_topics = geopolitical_topics(headline)
        market_topics = geopolitical_topics(question)
        if (headline_topics or market_topics) and not (headline_topics & market_topics):
            return None
    headline_crypto_directions = crypto_directions(headline)
    market_crypto_directions = crypto_directions(question)
    crypto_family_match = event_family_overlap == ["crypto-price"]
    headline_crypto_values = crypto_price_values(headline)
    market_crypto_values = crypto_price_values(question)
    crypto_subject_overlap = subject_overlap & {"bitcoin", "ethereum"}
    crypto_matched_subjects = sorted(
        subject
        for subject in crypto_subject_overlap
        if crypto_market_value_matches(headline, question, subject)
    )
    crypto_value_match = bool(crypto_matched_subjects)
    crypto_direction_match = bool(
        len(crypto_subject_overlap) == 1
        and
        headline_crypto_directions
        and market_crypto_directions
        and headline_crypto_directions & market_crypto_directions
    )
    crypto_semantic_match = crypto_value_match if market_crypto_values else crypto_direction_match
    if crypto_family_match and not crypto_semantic_match:
        return None
    if not family_overlap and not (
        crypto_family_match
        and crypto_semantic_match
    ):
        return None
    headline_rate_directions = rate_directions(headline)
    market_rate_directions = rate_directions(question)
    if (
        "macro-rates" in headline_event_families
        and headline_rate_directions
        and market_rate_directions
        and not (headline_rate_directions & market_rate_directions)
    ):
        return None
    overlap = tokens(headline) & tokens(question)
    score = (
        len(subject_overlap) * 3
        + len(family_overlap) * 2
        + len(event_family_overlap) * 2
        + len(overlap)
        + (3 if crypto_value_match else 0)
    )
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
        "marketEventDate": event_date.isoformat() if event_date else None,
        "subjectOverlap": sorted(subject_overlap),
        "familyOverlap": sorted(family_overlap),
        "headlineEventFamilies": sorted(headline_event_families),
        "marketEventFamilies": sorted(market_event_families),
        "eventFamilyOverlap": event_family_overlap,
        "headlineRateDirections": sorted(headline_rate_directions),
        "marketRateDirections": sorted(market_rate_directions),
        "headlineCryptoDirections": sorted(headline_crypto_directions),
        "marketCryptoDirections": sorted(market_crypto_directions),
        "headlineCryptoPriceValues": headline_crypto_values,
        "marketCryptoPriceValues": market_crypto_values,
        "cryptoValueMatch": crypto_value_match,
        "cryptoMatchedSubjects": crypto_matched_subjects,
        "headlineActors": sorted(headline_actors),
        "marketActors": sorted(market_actors),
        "headlineJurisdictions": sorted(headline_jurisdictions),
        "marketJurisdictions": sorted(market_jurisdictions),
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
    candidates_by_headline: dict[str, list[dict[str, Any]]] = {}
    for item in candidates:
        candidates_by_headline.setdefault(str(item.get("headline") or ""), []).append(item)
    narrowed_candidates: list[dict[str, Any]] = []
    for headline_candidates in candidates_by_headline.values():
        preferred_crypto_ranges = [
            item
            for item in headline_candidates
            if item.get("category") == "crypto"
            and item.get("cryptoValueMatch") is True
            and "between" in tokens(item.get("question"))
        ]
        if preferred_crypto_ranges:
            narrowed_candidates.extend(
                item for item in headline_candidates if item.get("category") != "crypto"
            )
            narrowed_candidates.extend(preferred_crypto_ranges)
        else:
            narrowed_candidates.extend(headline_candidates)
    candidates = narrowed_candidates
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
            "items": [],
        })
        row["marketEventFamilies"].update(item.get("marketEventFamilies", []))
        row["marketActorSets"].add(tuple(item.get("marketActors") or []))
        if "market-counterparty-not-explicit-in-headline" in (item.get("specificityFlags") or []):
            row["counterpartyIssueCount"] += 1
        row["candidateExternalIds"].append(item.get("externalId"))
        row["items"].append(item)
    normalized_fanout = []
    ambiguous_fanout = []
    counterparty_fanout = []
    market_line_fanout = []
    ambiguous_headline_count = 0
    counterparty_fanout_count = 0
    market_line_fanout_count = 0
    for row in headline_family_fanout.values():
        market_families = sorted(row["marketEventFamilies"])
        market_actor_sets = sorted([list(item) for item in row["marketActorSets"]])
        line_ambiguous = (
            len(set(str(item) for item in row["candidateExternalIds"] if item)) > 1
            and len(market_actor_sets) == 1
            and len(set(market_families) - {"unknown"}) == 1
        )
        if line_ambiguous:
            market_line_fanout_count += 1
            for item in row["items"]:
                if item.get("mappingStatus") == "candidate-review-required":
                    item["mappingStatus"] = "ambiguous-market-line-review-required"
                flags = item.get("specificityFlags") if isinstance(item.get("specificityFlags"), list) else []
                if "headline-maps-to-multiple-market-lines" not in flags:
                    flags.append("headline-maps-to-multiple-market-lines")
                item["specificityFlags"] = flags
        statuses = dict(Counter(str(item.get("mappingStatus") or "missing") for item in row["items"]))
        ambiguous = (
            len(set(row["headlineEventFamilies"]) - {"unknown"}) > 1
            or len(set(market_families) - {"unknown"}) > 1
            or any("ambiguous-headline-family" in status or "mismatch" in status for status in statuses)
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
            "marketLineAmbiguous": line_ambiguous,
        }
        normalized_fanout.append(fanout_row)
        if ambiguous:
            ambiguous_fanout.append(fanout_row)
        if counterparty_ambiguous:
            counterparty_fanout.append(fanout_row)
        if line_ambiguous:
            market_line_fanout.append(fanout_row)
    blockers: list[str] = []
    if len(selected) < minimum_candidates:
        blockers.append("too-few-strict-event-market-candidates")
    if ambiguous_headline_count:
        blockers.append("ambiguous-headline-event-family-fanout")
    if counterparty_fanout_count:
        blockers.append("ambiguous-headline-counterparty-fanout")
    if market_line_fanout_count:
        blockers.append("ambiguous-headline-market-line-fanout")
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
        "ambiguousMarketLineHeadlineCount": market_line_fanout_count,
        "headlineFamilyFanout": normalized_fanout,
        "ambiguousHeadlineFamilyFanout": ambiguous_fanout,
        "ambiguousHeadlineCounterpartyFanout": counterparty_fanout,
        "ambiguousHeadlineMarketLineFanout": market_line_fanout,
        "candidates": selected,
        "blockers": blockers,
        "decision": "research-only-event-market-mapping-candidates-ready" if not blockers else "research-only-event-market-mapping-blocked",
        "hardRules": [
            "A mapping candidate is not a signal or paper-trade approval.",
            "Subject and event-family overlap are required; broad prediction-market headlines do not qualify.",
            "Headlines with multiple event families remain mapping-review only until a single market family is selected.",
            "Geopolitical headlines must identify the relevant counterparties before a market family can become paper evidence.",
            "One headline mapping to multiple outcome lines counts as one event and remains review-only until exactly one line is selected.",
            "Crypto mappings require an asset-bound compatible price/band or an explicit matching direction; ambiguous threshold fanout remains review-only.",
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
        f"- Ambiguous market-line count: `{payload.get('ambiguousMarketLineHeadlineCount')}`",
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
    parser.add_argument("--categories", default="geopolitics,politics,macro-rates,commodities,equities,crypto")
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
