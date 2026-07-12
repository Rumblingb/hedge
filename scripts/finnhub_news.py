#!/usr/bin/env python3
"""Finnhub News + Sentiment Integration for Bill/Hedge
Fetches market news, economic calendar, and computes sentiment scores.
Free tier: 60 API calls/minute. Outputs JSON for strategy gating.

Usage: python3 scripts/finnhub_news.py
Output: .rumbling-hedge/state/news-sentiment.json
"""
import argparse
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ENV_PATHS = [
    Path.home() / ".hermes/.env",
    Path.home() / "Library/Application Support/AgentPay/bill/bill.env",
]


def read_secure_env(key):
    value = os.environ.get(key)
    if value:
        return value.strip().strip("'\"")
    for path in ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[7:]
            if "=" not in stripped:
                continue
            name, raw = stripped.split("=", 1)
            if name.strip() == key:
                return raw.strip().strip("'\"")
    return None


# Finnhub free-tier key. Read local secure env files directly so cron/npm
# research runs do not depend on an interactive shell exporting the key.
API_KEY = read_secure_env("FINNHUB_API_KEY") or "demo"
OUT_PATH = ".rumbling-hedge/state/news-sentiment.json"
LATEST_PATH = ".rumbling-hedge/state/finnhub-news.latest.json"

# Try VADER for sentiment, fall back to simple keyword scoring
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    HAS_VADER = True
except ImportError:
    HAS_VADER = False

# Economic calendar events that matter for futures
HIGH_IMPACT_EVENTS = [
    "FOMC", "Fed", "interest rate", "CPI", "PPI", "NFP", "nonfarm", "non-farm",
    "GDP", "unemployment", "jobless claims", "ISM", "PMI", "retail sales",
    "consumer confidence", "durable goods", "trade balance", "ECB", "OPEC",
    "EIA", "crude oil inventories", "natural gas"
]

MEDIUM_IMPACT_EVENTS = [
    "housing starts", "building permits", "industrial production",
    "factory orders", "wholesale inventories", "consumer credit",
    "Michigan sentiment", "Philadelphia Fed", "Empire State"
]

BULLISH_KEYWORDS = [
    "beat", "exceed", "surge", "rally", "jump", "soar", "bullish", "upgrade",
    "strong", "robust", "optimistic", "growth", "expansion", "recovery",
    "stimulus", "easing", "dovish", "cut", "lower rates"
]

BEARISH_KEYWORDS = [
    "miss", "disappoint", "plunge", "crash", "tumble", "sink", "bearish", "downgrade",
    "weak", "fragile", "pessimistic", "contraction", "recession", "slowdown",
    "tightening", "hawkish", "hike", "raise rates", "tariff", "trade war"
]

def simple_sentiment(text):
    """Simple keyword-based sentiment scoring"""
    text_lower = text.lower()
    bullish_score = sum(1 for w in BULLISH_KEYWORDS if w in text_lower)
    bearish_score = sum(1 for w in BEARISH_KEYWORDS if w in text_lower)
    total = bullish_score + bearish_score
    if total == 0:
        return {"compound": 0, "pos": 0, "neg": 0, "neu": 1}
    compound = (bullish_score - bearish_score) / total
    return {
        "compound": round(compound, 3),
        "pos": round(bullish_score / total, 3) if total > 0 else 0,
        "neg": round(bearish_score / total, 3) if total > 0 else 0,
        "neu": 0
    }

def get_sentiment(text):
    if HAS_VADER:
        analyzer = SentimentIntensityAnalyzer()
        return analyzer.polarity_scores(text)
    return simple_sentiment(text)

def fetch_finnhub_news():
    """Fetch market news from Finnhub"""
    import urllib.request
    
    url = f"https://finnhub.io/api/v1/news?category=general&token={API_KEY}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return (data[:20] if isinstance(data, list) else []), None
    except Exception as e:
        print(f"  Finnhub news fetch failed: {e}")
        return [], str(e)

def fetch_economic_calendar():
    """Fetch economic calendar from Finnhub"""
    import urllib.request
    from datetime import datetime, timezone
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/calendar/economic?from={today}&to={today}&token={API_KEY}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if isinstance(data, list):
                return data, None
            if isinstance(data, dict):
                rows = data.get("economicCalendar") or data.get("data") or data.get("calendar")
                return (rows if isinstance(rows, list) else []), None
            return [], None
    except Exception as e:
        print(f"  Economic calendar fetch failed: {e}")
        return [], str(e)

def build_output(news, calendar, news_error=None, calendar_error=None):
    """Build a fail-closed research artifact from fetched news/calendar rows."""
    total_compound = 0
    scored_articles = []
    for article in news:
        headline = article.get("headline", "")
        summary = article.get("summary", "")
        text = f"{headline}. {summary}"[:500]
        sentiment = get_sentiment(text)
        total_compound += sentiment["compound"]

        scored_articles.append({
            "headline": headline[:120],
            "source": article.get("source", ""),
            "datetime": article.get("datetime", 0),
            "sentiment": sentiment,
            "category": article.get("category", ""),
        })

    avg_sentiment = total_compound / len(scored_articles) if scored_articles else 0
    event_alerts = build_event_gate(calendar)
    data_usable = bool(scored_articles or calendar) and not (news_error and calendar_error)
    status = "PASS" if data_usable else "BLOCKED_NO_DATA"
    trend_allowed = data_usable and not any(a["action"] == "BLOCK_TREND_STRATEGIES" for a in event_alerts)

    return {
        "command": "finnhub-news",
        "sourceAdapter": "finnhub",
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "executionAuthority": False,
        "readyForExecution": False,
        "status": status,
        "dataUsable": data_usable,
        "fetchErrors": {
            "news": news_error,
            "calendar": calendar_error,
        },
        "news_count": len(scored_articles),
        "average_sentiment": round(avg_sentiment, 3),
        "sentiment_regime": (
            "bullish" if avg_sentiment > 0.15
            else "bearish" if avg_sentiment < -0.15
            else "neutral"
        ),
        "articles": scored_articles[:10],
        "calendar_events": calendar[:10],
        "event_alerts": event_alerts,
        "trading_gate": {
            "trend_strategies_allowed": trend_allowed,
            "max_position_size_pct": 0.0 if not data_usable else 0.5 if any(a["action"] == "REDUCE_EXPOSURE" for a in event_alerts) else 1.0,
            "mean_reversion_allowed": data_usable,
            "active_alerts": len(event_alerts),
            "data_usable": data_usable,
        },
        "api_key_status": "configured" if API_KEY != "demo" else "demo_limited"
    }

def build_event_gate(calendar_events):
    """Determine if any high-impact events are happening now or within 30 min"""
    from datetime import datetime, timezone, timedelta
    
    now = datetime.now(timezone.utc)
    alerts = []
    
    for event in calendar_events:
        event_title = event.get("event", "")
        event_time_str = event.get("date", "")
        
        if not event_time_str:
            continue
        
        try:
            event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
        except:
            continue
        
        # Check if event is within 30 min window
        time_diff = abs((event_time - now).total_seconds()) / 60
        
        # Check impact
        title_lower = event_title.lower()
        is_high = any(e.lower() in title_lower for e in HIGH_IMPACT_EVENTS)
        is_medium = any(e.lower() in title_lower for e in MEDIUM_IMPACT_EVENTS)
        
        if is_high and time_diff < 60:
            alerts.append({
                "event": event_title,
                "time": event_time_str,
                "impact": "high",
                "minutes_away": round(time_diff),
                "action": "BLOCK_TREND_STRATEGIES",
                "rationale": "High-impact event — block momentum/trend strategies, allow mean-reversion only"
            })
        elif is_medium and time_diff < 30:
            alerts.append({
                "event": event_title,
                "time": event_time_str,
                "impact": "medium",
                "minutes_away": round(time_diff),
                "action": "REDUCE_EXPOSURE",
                "rationale": "Medium-impact event — reduce position sizes by 50%"
            })
    
    return alerts

def parse_args():
    parser = argparse.ArgumentParser(description="Fetch Finnhub research/news context for Bill.")
    parser.add_argument("--compact", action="store_true", help="Print a compact summary instead of verbose details.")
    parser.add_argument("--dry-run", action="store_true", help="Build the artifact without writing state files.")
    return parser.parse_args()


def write_outputs(output):
    out_dir = Path(".rumbling-hedge/state")
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in (OUT_PATH, LATEST_PATH):
        with open(path, 'w') as f:
            json.dump(output, f, indent=2, default=str)


def print_summary(output, calendar, compact=False, dry_run=False):
    if compact:
        print(json.dumps({
            "status": output["status"],
            "dataUsable": output["dataUsable"],
            "newsCount": output["news_count"],
            "calendarEvents": len(calendar),
            "activeAlerts": len(output["event_alerts"]),
            "researchOnly": output["researchOnly"],
            "readyForExecution": output["readyForExecution"],
            "dryRun": dry_run,
        }, sort_keys=True))
        return
    print(f"\nWritten to {OUT_PATH}" if not dry_run else "\nDry run: no files written")
    print(f"Latest Finnhub artifact: {LATEST_PATH}")
    print(f"Status: {output['status']}")
    print(f"Articles scored: {output['news_count']}")
    print(f"Average sentiment: {output['average_sentiment']:.3f} ({output['sentiment_regime']})")
    print(f"Calendar events: {len(calendar)}")
    print(f"Event alerts: {len(output['event_alerts'])}")
    for alert in output["event_alerts"]:
        print(f"  {alert['impact'].upper()}: {alert['event']} ({alert['minutes_away']}m away)")


def main():
    args = parse_args()
    print("Finnhub News + Sentiment for Bill/Hedge")
    print(f"  API Key: {'set' if API_KEY != 'demo' else 'DEMO (limited)'}")

    # Fetch news
    print("Fetching market news...")
    news, news_error = fetch_finnhub_news()

    # Fetch economic calendar
    print("Fetching economic calendar...")
    calendar, calendar_error = fetch_economic_calendar()
    output = build_output(news, calendar, news_error, calendar_error)
    if not args.dry_run:
        write_outputs(output)
    print_summary(output, calendar, compact=args.compact, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
