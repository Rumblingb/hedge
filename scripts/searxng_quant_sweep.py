#!/usr/bin/env python3
"""SearXNG quant alpha research sweeper."""
import json
import urllib.request
import urllib.parse
import time

SEARXNG = "http://127.0.0.1:8888"

queries = [
    "volatility breakout alpha factor futures 2024 2025 site:ssrn.com OR site:arxiv.org",
    "machine learning regime detection NQ ES futures 2025",
    "order flow imbalance OHLCV proxy index futures microstructure",
    "cross-asset correlation trading NQ ES CL GC statistical arbitrage",
    "intraday time-of-day pattern S&P 500 Nasdaq futures alpha",
    "transformer neural network futures price prediction 2025 arxiv.org",
    "novel momentum factor decomposition equity index futures research",
    "volume profile market profile trading NQ ES quantitative strategy",
]

all_results = {}

for i, q in enumerate(queries):
    print(f"\n[{i+1}/8] Query: {q[:70]}")
    params = urllib.parse.urlencode({"q": q, "format": "json"})
    url = f"{SEARXNG}/search?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        print(f"  Results: {len(results)}")

        sources = []
        for r in results[:5]:
            sources.append({
                "title": r.get("title", "?")[:150],
                "url": r.get("url", "?"),
                "engine": r.get("engine", "?"),
                "content": r.get("content", "")[:300],
            })
            print(f"  [{r.get('engine','?')}] {r.get('title','?')[:100]}")
            print(f"    {r.get('url','?')}")

        all_results[f"query_{i+1}"] = {
            "query": q,
            "total_results": len(results),
            "sources": sources,
        }
    except Exception as e:
        print(f"  ERROR: {e}")
        all_results[f"query_{i+1}"] = {"query": q, "error": str(e)}
    time.sleep(0.5)

# Save all results
with open("/Users/brain/hedge/.rumbling-hedge/research/macro/searxng-quant-results.json", "w") as f:
    json.dump(all_results, f, indent=2, default=str)

print(f"\n\nSaved to searxng-quant-results.json")
print(f"\n=== KEY FINDINGS ===")
for k, v in all_results.items():
    q = v.get("query", "?")
    sources = v.get("sources", [])
    n = v.get("total_results", 0)
    if sources:
        print(f"\n{'='*60}")
        print(f"Query: {q[:70]}")
        print(f"Top result: {sources[0]['title'][:120]}")
        print(f"URL: {sources[0]['url']}")
    else:
        print(f"\n{q[:60]}: {n} results - no actionable sources")
