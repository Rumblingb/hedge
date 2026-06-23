#!/usr/bin/env python3
"""Read-only RSS news collector for prediction event-lag research.

This is a fallback for the Finnhub demo-key path. It writes the same
``news-sentiment.json`` contract used by event-lag requirements, but does not
touch broker APIs, funding, orders, or execution state.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.finnhub_news import get_sentiment

STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "news-sentiment.json"
LATEST = STATE / "prediction-event-news-rss.latest.json"

DEFAULT_QUERIES = [
    "Federal Reserve OR FOMC OR CPI OR inflation when:2d",
    "election OR tariff OR oil OR OPEC OR ceasefire when:2d",
    "Bitcoin OR BTC OR Ethereum OR ETH OR crypto when:2d",
    "prediction market OR Polymarket OR Kalshi when:2d",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rss_url(query: str) -> str:
    encoded = quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"


def parse_pub_date(value: str | None) -> int:
    if not value:
        return 0
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except Exception:
        return 0


def strip_source(title: str) -> tuple[str, str]:
    if " - " not in title:
        return title.strip(), ""
    headline, source = title.rsplit(" - ", 1)
    return headline.strip(), source.strip()


def parse_rss(xml_text: str, query: str, limit: int) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    out: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        raw_title = item.findtext("title") or ""
        headline, source = strip_source(raw_title)
        description = item.findtext("description") or ""
        published = item.findtext("pubDate") or ""
        out.append({
            "headline": headline[:240],
            "source": source or "Google News RSS",
            "datetime": parse_pub_date(published),
            "published": published,
            "summary": description[:500],
            "category": "rss_event_news",
            "query": query,
        })
        if len(out) >= limit:
            break
    return out


def fetch_query(query: str, limit: int = 10) -> tuple[list[dict[str, Any]], str | None]:
    try:
        req = Request(rss_url(query), headers={"User-Agent": "BillHermesResearch/1.0"})
        with urlopen(req, timeout=12) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        return parse_rss(text, query, limit), None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def dedupe_articles(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: int(item.get("datetime") or 0), reverse=True):
        key = str(row.get("headline") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def build_output(articles: list[dict[str, Any]], fetch_errors: dict[str, str | None]) -> dict[str, Any]:
    scored = []
    total = 0.0
    for article in articles:
        text = f"{article.get('headline', '')}. {article.get('summary', '')}"[:500]
        sentiment = get_sentiment(text)
        total += float(sentiment.get("compound") or 0)
        scored.append({
            "headline": str(article.get("headline") or "")[:120],
            "source": article.get("source") or "",
            "datetime": article.get("datetime") or 0,
            "published": article.get("published") or "",
            "sentiment": sentiment,
            "category": article.get("category") or "rss_event_news",
            "query": article.get("query") or "",
        })
    avg = total / len(scored) if scored else 0.0
    data_usable = len(scored) >= 10
    generated_at = now_iso()
    decision = "research-only-event-news-rss-ready" if data_usable else "research-only-event-news-rss-blocked-no-data"
    return {
        "command": "prediction-event-news-rss",
        "generated_at": generated_at,
        "generatedAt": generated_at,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForPaper": False,
        "decision": decision,
        "status": "PASS" if data_usable else "BLOCKED_NO_DATA",
        "dataUsable": data_usable,
        "sourceAdapter": "google_news_rss_fallback",
        "api_key_status": "not_required_rss",
        "fetchErrors": fetch_errors,
        "news_count": len(scored),
        "newsCount": len(scored),
        "articleCount": len(scored),
        "itemCount": len(scored),
        "average_sentiment": round(avg, 3),
        "sentiment_regime": "bullish" if avg > 0.15 else "bearish" if avg < -0.15 else "neutral",
        "articles": scored,
        "calendar_events": [],
        "event_alerts": [],
        "trading_gate": {
            "trend_strategies_allowed": False,
            "max_position_size_pct": 0.0,
            "mean_reversion_allowed": False,
            "active_alerts": 0,
            "data_usable": data_usable,
            "research_only_news_context": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch RSS event news for prediction event-lag research.")
    parser.add_argument("--query", action="append", default=[], help="RSS search query. Can be provided multiple times.")
    parser.add_argument("--per-query", type=int, default=10)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--latest-output", default=str(LATEST))
    args = parser.parse_args()

    queries = args.query or DEFAULT_QUERIES
    rows: list[dict[str, Any]] = []
    errors: dict[str, str | None] = {}
    for query in queries:
        query_rows, error = fetch_query(query, args.per_query)
        rows.extend(query_rows)
        errors[query] = error
    payload = build_output(dedupe_articles(rows, args.limit), errors)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    latest_output = Path(args.latest_output)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
