#!/usr/bin/env python3
"""GOLD #7: Financial NLP Sentiment Engine.

Fetches financial news headlines via SearXNG, scores sentiment.
Output: {ts, sentiment, source_count, top_sources, top_headlines}
"""
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.path.expanduser("~/.rumbling-hedge"))
STATE_DIR = ROOT / "state"

# Positive/negative word lists for simple sentiment scoring
POSITIVE_WORDS = {"bullish", "surge", "rally", "gain", "up", "growth", "positive", "strong",
    "outperform", "beat", "upgrade", "buy", "opportunity", "breakout", "momentum",
    "recovery", "expansion", "boom", "profit", "record", "high"}
NEGATIVE_WORDS = {"bearish", "plunge", "crash", "loss", "down", "decline", "negative", "weak",
    "underperform", "miss", "downgrade", "sell", "risk", "recession", "slowdown",
    "inflation", "fear", "panic", "drop", "low", "cut", "slump"}

SEARXNG_URL = (
    os.environ.get("BILL_SEARXNG_URL")
    or os.environ.get("SEARXNG_URL")
    or os.environ.get("RESEARCHER_SEARXNG_URL")
    or "http://127.0.0.1:8888"
).rstrip("/")

def fetch_financial_news():
    """Fetch financial news headlines via SearXNG."""
    queries = [
        "stock market today finance news",
        "S&P 500 Nasdaq trading",
        "Federal Reserve interest rates economy",
        "commodities oil gold markets"
    ]
    all_headlines = []
    for q in queries:
        try:
            cmd = f'curl -s --max-time 10 "{SEARXNG_URL}/search?q={q.replace(chr(34),chr(37)+chr(51)+chr(68))}&format=json&limit=5"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            data = json.loads(result.stdout)
            for r in data.get("results", []):
                all_headlines.append({
                    "title": r.get("title", ""),
                    "content": r.get("content", ""),
                    "source": r.get("engine", "?"),
                    "url": r.get("url", ""),
                })
        except Exception:
            pass
    return all_headlines

def score_sentiment(headlines):
    """Score sentiment of headlines using word lists."""
    total_score = 0.0
    scored = 0
    for h in headlines:
        text = (h.get("title", "") + " " + h.get("content", "")).lower()
        pos_count = sum(1 for w in POSITIVE_WORDS if w in text)
        neg_count = sum(1 for w in NEGATIVE_WORDS if w in text)
        total = pos_count + neg_count
        if total > 0:
            total_score += (pos_count - neg_count) / total
            scored += 1
    avg = total_score / scored if scored > 0 else 0.0
    # Clamp to -1..+1
    return max(-1.0, min(1.0, avg))

def main():
    ts = datetime.now(timezone.utc).isoformat()
    headlines = fetch_financial_news()
    sentiment = score_sentiment(headlines)
    
    by_source = {}
    for h in headlines:
        s = h.get("source", "?")
        by_source.setdefault(s, 0)
        by_source[s] += 1
    
    output = {
        "ts": ts,
        "sentiment": round(sentiment, 3),
        "source_count": len(by_source),
        "top_sources": dict(sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:5]),
        "total_headlines": len(headlines),
        "top_headlines": [h["title"] for h in headlines[:5] if h.get("title")],
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / "nlp-sentiment.latest.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"  NLP Sentiment: {sentiment:+.3f} from {len(headlines)} headlines")

if __name__ == "__main__":
    main()