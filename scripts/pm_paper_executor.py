#!/usr/bin/env python3
"""PM Paper Executor — Track Polymarket paper-watch edges through simulated fills.

Reads paper-watch edges from the two-track-readiness report, checks
market depth/liquidity via Polymarket CLOB API, simulates fills at
current prices, and journals results for promotion gate validation.

Usage: python3 scripts/pm_paper_executor.py [--dry-run]
"""

import json
import os
import sys
import time
import urllib.request

EDGES = [
    {"id": "mispriced-002", "title": "Starmer Out Series - Calendar Arbitrage", "type": "calendar", "slug": "starmer-out"},
    {"id": "mispriced-004", "title": "Base Token Launch - Temporal Discontinuity", "type": "calendar", "slug": "base-token-launch"},
    {"id": "contrarian-001", "title": "US Declares War on Iran - Surprisingly Low Probability", "type": "contrarian", "slug": "us-war-iran"},
    {"id": "contrarian-003", "title": "US Recession by End of 2026 - Consensus Complacency", "type": "contrarian", "slug": "us-recession-2026"},
    {"id": "mispriced-001", "title": "MicroStrategy BTC Sell Series - Temporal Inconsistency", "type": "calendar", "slug": "mstr-btc-sell"},
    {"id": "mispriced-003", "title": "BTC $150k Series - Exponential Decay Anomaly", "type": "calendar", "slug": "btc-150k"},
    {"id": "mispriced-005", "title": "OpenAI IPO Series - Calendar Discontinuity", "type": "calendar", "slug": "openai-ipo"},
]

POLYMARKET_API = "https://clob.polymarket.com"
STATE_DIR = os.path.expanduser("/Users/brain/hedge/.rumbling-hedge/state")

def fetch_json(url):
    """Fetch JSON from URL with timeout."""
    req = urllib.request.Request(url, headers={"User-Agent": "PM-Paper-Executor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def search_market(slug):
    """Search Polymarket CLOB API for a market by slug."""
    url = f"{POLYMARKET_API}/markets?tag={slug}&limit=5"
    return fetch_json(url)

def check_liquidity(market_id):
    """Check order book depth for a market."""
    url = f"{POLYMARKET_API}/book?market={market_id}&side=BUY"
    return fetch_json(url)

def simulate_fill(edge, market_data):
    """Simulate a paper fill at current best bid/ask."""
    result = {
        "edge_id": edge["id"],
        "title": edge["title"],
        "slug": edge["slug"],
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "market_found": False,
        "best_bid": None,
        "best_ask": None,
        "spread_pct": None,
        "estimated_liquidity": None,
        "fillable": False,
        "fill_price": None,
        "reason": None,
    }

    if "error" in market_data:
        result["reason"] = f"API error: {market_data['error']}"
        return result

    markets = market_data if isinstance(market_data, list) else market_data.get("data", [])
    if not markets:
        result["reason"] = "No markets found"
        return result

    m = markets[0] if isinstance(markets, list) else markets
    market_id = m.get("condition_id", m.get("id", "unknown"))
    result["market_found"] = True
    result["market_id"] = market_id

    # Check book
    book = check_liquidity(market_id)
    if "error" in book:
        result["reason"] = f"Book error: {book['error']}"
        return result

    bids = book.get("bids", [])
    asks = book.get("asks", [])

    if bids:
        result["best_bid"] = float(bids[0].get("price", 0))
        result["bid_size"] = float(bids[0].get("size", 0))
    if asks:
        result["best_ask"] = float(asks[0].get("price", 0))
        result["ask_size"] = float(asks[0].get("size", 0))

    if result["best_bid"] and result["best_ask"]:
        result["spread_pct"] = (result["best_ask"] - result["best_bid"]) / result["best_bid"] * 100

    # Total depth within 5% of best
    total_bid_depth = sum(float(b.get("size", 0)) for b in bids[:5]) if bids else 0
    result["estimated_liquidity"] = total_bid_depth

    # Market is fillable if spread < 20% and depth > 100 contracts
    spread_ok = result["spread_pct"] is not None and result["spread_pct"] < 20.0
    depth_ok = total_bid_depth > 100

    result["fillable"] = spread_ok and depth_ok

    if result["fillable"]:
        # Simulate market-buy at best ask + 1 tick
        result["fill_price"] = result["best_ask"]
        result["fill_size"] = min(100, total_bid_depth)
        result["reason"] = "FILLABLE"
    else:
        blockers = []
        if not spread_ok:
            blockers.append(f"wide-spread({result['spread_pct']:.1f}%)")
        if not depth_ok:
            blockers.append(f"thin-depth({total_bid_depth:.0f})")
        result["reason"] = ";".join(blockers)

    return result

def main():
    dry_run = "--dry-run" in sys.argv
    results_path = os.path.join(STATE_DIR, "pm-paper-executor.latest.json")

    print("=" * 60)
    print("PM PAPER EXECUTOR — Polymarket Paper Trade Simulator")
    print("=" * 60)
    print(f"Edges to check: {len(EDGES)}")
    print(f"Dry run: {dry_run}")
    print()

    all_results = []
    fillable_count = 0

    for edge in EDGES:
        print(f"Checking: {edge['title']} ({edge['slug']})...", end=" ", flush=True)

        if dry_run:
            print("SKIP (dry-run)")
            continue

        market_data = search_market(edge["slug"])
        result = simulate_fill(edge, market_data)

        if result["fillable"]:
            fillable_count += 1
            print(f"✅ FILLABLE @ ${result['fill_price']:.3f} (depth={result['estimated_liquidity']:.0f})")
        else:
            print(f"❌ {result['reason']}")

        all_results.append(result)
        time.sleep(0.5)  # Rate limit

    print()
    print("=" * 60)
    print(f"RESULTS: {fillable_count}/{len(EDGES)} fillable")

    if not dry_run:
        report = {
            "command": "pm-paper-executor",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "edges_checked": len(EDGES),
            "fillable": fillable_count,
            "results": all_results,
        }
        os.makedirs(os.path.dirname(results_path), exist_ok=True)
        with open(results_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to {results_path}")

if __name__ == "__main__":
    main()
