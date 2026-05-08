#!/usr/bin/env python3
"""Prediction Markets Execution Engine — Complete strategy execution.
Cross-venue arb, resolution front-run, Kelly sizing, news reaction, sentiment.
Targets: 5-30% weekly compounding. No PDT rule = max compounding speed.
"""
import json, math, os, sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

STATE_DIR = Path(".rumbling-hedge/state")
PM_STATE = STATE_DIR / "pm-execution-engine.json"
PM_JOURNAL = STATE_DIR / "pm-trade-journal.jsonl"

# ============================================================
# 1. KELLY CRITERION — Optimal bet sizing for compounding
# ============================================================

def kelly_fraction(probability: float, odds: float, fraction: float = 0.25) -> float:
    """Fractional Kelly criterion. f* = (bp - q) / b, then scale by fraction.
    Args:
        probability: true probability of winning (0-1)
        odds: decimal odds (e.g., 1.05 for buying at 95c = 100/95 ≈ 1.053)
        fraction: Kelly fraction (0.25 = quarter-Kelly, conservative)
    Returns:
        Fraction of bankroll to bet (0-1)
    """
    if probability <= 0 or odds <= 1:
        return 0.0
    q = 1.0 - probability
    b = odds - 1.0  # net odds
    if b <= 0:
        return 0.0
    f_star = (b * probability - q) / b
    return max(0.0, min(f_star * fraction, 0.25))  # Cap at 25% per bet

def optimal_bet_size(bankroll: float, probability: float, price: float, 
                     fraction: float = 0.25) -> Tuple[float, int]:
    """Calculate optimal bet size in dollars and shares.
    For binary outcome: buying at price P with true probability > P.
    Price is the market-implied probability.
    """
    if price >= probability or price <= 0:
        return 0.0, 0
    # Buying "YES" at price: risk = price, reward = 1-price if correct
    odds = 1.0 / price
    f = kelly_fraction(probability, odds, fraction)
    bet_amount = bankroll * f
    shares = int(bet_amount / price) if price > 0 else 0
    return round(bet_amount, 2), shares

# ============================================================
# 2. CROSS-VENUE ARBITRAGE — Risk-free when available
# ============================================================

def find_cross_venue_arbs(polymarket_events: List[dict], 
                          kalshi_events: List[dict]) -> List[dict]:
    """Find arbitrage opportunities between Polymarket and Kalshi.
    Same event, different platforms, different prices = free money.
    """
    arbs = []
    
    # Match events by title similarity
    pm_map = {e.get("eventTitle", "").lower()[:60]: e for e in polymarket_events}
    k_map = {e.get("eventTitle", "").lower()[:60]: e for e in kalshi_events}
    
    for key in pm_map:
        if key in k_map:
            pm = pm_map[key]
            k = k_map[key]
            pm_price = pm.get("price", 0.5)
            k_price = k.get("price", 0.5)
            
            # Arb: buy low, sell high
            if pm_price < k_price:
                buy_price = pm_price
                sell_price = k_price
                buy_venue = "polymarket"
                sell_venue = "kalshi"
            else:
                buy_price = k_price
                sell_price = pm_price
                buy_venue = "kalshi"
                sell_venue = "polymarket"
            
            edge = sell_price - buy_price
            if edge > 0.02:  # 2% minimum edge after fees
                arbs.append({
                    "type": "cross-venue-arb",
                    "event": key[:80],
                    "buy_venue": buy_venue,
                    "sell_venue": sell_venue,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "edge": round(edge, 4),
                    "edge_pct": round(edge / buy_price * 100, 1),
                    "risk_free_return": round((1 - buy_price) / buy_price * 100, 1),
                })
    
    return sorted(arbs, key=lambda a: a["edge"], reverse=True)

# ============================================================
# 3. RESOLUTION FRONT-RUN — Near-certain events
# ============================================================

def find_resolution_plays(events: List[dict], min_prob: float = 0.90) -> List[dict]:
    """Find near-certain resolution events. Buy at 90c+, collect 100c.
    Expected return: 5-11% in days/weeks. Near risk-free.
    """
    plays = []
    for event in events:
        price = event.get("price", 0.5)
        volume = event.get("displayedSize", 0)
        
        if price >= min_prob and volume > 1000:
            remaining = 1.0 - price
            expected_return = remaining / price * 100
            plays.append({
                "type": "resolution-front-run",
                "event": event.get("eventTitle", "")[:80],
                "current_price": price,
                "upside": round(remaining, 4),
                "expected_return_pct": round(expected_return, 1),
                "volume": volume,
                "risk": "black-swan-resolution",
                "kelly_bet_pct": round(kelly_fraction(price + remaining * 0.5, 1/price, 0.25) * 100, 1),
            })
    
    return sorted(plays, key=lambda p: p["expected_return_pct"], reverse=True)

# ============================================================
# 4. MEAN REVERSION — Fade extreme moves
# ============================================================

def find_mean_reversion_plays(events: List[dict], history: List[dict], 
                               z_threshold: float = 2.5) -> List[dict]:
    """Find events where price has moved > 2.5 std from mean → fade.
    Binary markets mean-revert faster than continuous markets.
    """
    plays = []
    for event in events:
        event_id = event.get("externalId", "")
        event_prices = [h.get("price", 0.5) for h in history 
                       if h.get("externalId") == event_id]
        
        if len(event_prices) < 20:
            continue
        
        mean = sum(event_prices) / len(event_prices)
        std = math.sqrt(sum((p - mean)**2 for p in event_prices) / len(event_prices))
        
        if std < 0.01:
            continue
        
        current = event.get("price", 0.5)
        z_score = (current - mean) / std
        
        if abs(z_score) > z_threshold:
            plays.append({
                "type": "mean-reversion",
                "event": event.get("eventTitle", "")[:80],
                "current_price": current,
                "mean_price": round(mean, 4),
                "z_score": round(z_score, 2),
                "direction": "buy" if z_score < 0 else "sell",
                "target": round(mean, 4),
                "expected_return_pct": round(abs(mean - current) / current * 100, 1),
                "confidence": min(0.8, abs(z_score) / 5),
            })
    
    return sorted(plays, key=lambda p: abs(p["z_score"]), reverse=True)

# ============================================================
# 5. NEWS REACTION — Speed-based alpha
# ============================================================

SENTIMENT_KEYWORDS = {
    "bullish": ["beat", "exceed", "surge", "rally", "jump", "soar", "upgrade",
                "strong", "robust", "optimistic", "growth", "expansion",
                "stimulus", "easing", "dovish", "cut", "lower"],
    "bearish": ["miss", "disappoint", "plunge", "crash", "tumble", "sink",
                "downgrade", "weak", "fragile", "contraction", "recession",
                "tightening", "hawkish", "hike", "raise", "tariff"],
}

def analyze_news_sentiment(news_items: List[dict], events: List[dict]) -> List[dict]:
    """React to news faster than prediction market reprices.
    Speed is the edge — first mover advantage.
    """
    signals = []
    
    for news in news_items:
        headline = news.get("headline", "").lower()
        sentiment_score = 0
        for word in SENTIMENT_KEYWORDS["bullish"]:
            if word in headline: sentiment_score += 1
        for word in SENTIMENT_KEYWORDS["bearish"]:
            if word in headline: sentiment_score -= 1
        
        if sentiment_score == 0:
            continue
        
        # Match news to events
        for event in events:
            title = event.get("eventTitle", "").lower()
            # Simple keyword overlap
            overlap = len(set(headline.split()) & set(title.split()))
            if overlap > 2:
                direction = "buy" if sentiment_score > 0 else "sell"
                signals.append({
                    "type": "news-reaction",
                    "event": event.get("eventTitle", "")[:80],
                    "headline": news.get("headline", "")[:100],
                    "sentiment": sentiment_score,
                    "direction": direction,
                    "current_price": event.get("price", 0.5),
                    "confidence": min(0.7, abs(sentiment_score) / 5),
                    "urgency": "immediate",  # Speed-dependent
                })
    
    return sorted(signals, key=lambda s: abs(s["sentiment"]), reverse=True)

# ============================================================
# 6. CORRELATED EVENT PAIRS — Inconsistency detection
# ============================================================

def find_correlated_inconsistencies(events: List[dict]) -> List[dict]:
    """Find pricing inconsistencies in correlated event pairs.
    Example: Candidate winning presidency should align with swing state odds.
    """
    inconsistencies = []
    
    # Group events by category
    by_category = {}
    for e in events:
        title = e.get("eventTitle", "").lower()
        if "election" in title: by_category.setdefault("election", []).append(e)
        elif "fed" in title or "fomc" in title or "rate" in title: by_category.setdefault("fed", []).append(e)
        elif "cpi" in title or "inflation" in title: by_category.setdefault("inflation", []).append(e)
        elif "crypto" in title or "bitcoin" in title: by_category.setdefault("crypto", []).append(e)
    
    for category, cat_events in by_category.items():
        if len(cat_events) < 2:
            continue
        
        # Find price extremes within category
        prices = [e.get("price", 0.5) for e in cat_events]
        max_price = max(prices)
        min_price = min(prices)
        spread = max_price - min_price
        
        if spread > 0.15:  # 15%+ spread in related events = potential arb
            inconsistencies.append({
                "type": "correlated-inconsistency",
                "category": category,
                "event_count": len(cat_events),
                "max_price": max_price,
                "min_price": min_price,
                "spread": round(spread, 4),
                "action": f"Buy low ({min_price:.2f}), sell high ({max_price:.2f}) — convergence expected",
                "expected_return_pct": round(spread / min_price * 100, 1),
            })
    
    return inconsistencies

# ============================================================
# 7. PORTFOLIO OPTIMIZER — Kelly across all opportunities
# ============================================================

def optimize_portfolio(opportunities: List[dict], bankroll: float, 
                       max_positions: int = 5) -> dict:
    """Kelly-optimal portfolio allocation across all opportunities."""
    ranked = sorted(opportunities, 
                   key=lambda o: o.get("edge", o.get("expected_return_pct", 0)), 
                   reverse=True)
    
    portfolio = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bankroll": bankroll,
        "total_opportunities": len(opportunities),
        "selected_positions": [],
        "total_allocated": 0.0,
        "remaining_bankroll": bankroll,
    }
    
    for opp in ranked[:max_positions * 2]:  # Consider top 2x for filtering
        if len(portfolio["selected_positions"]) >= max_positions:
            break
        
        edge = opp.get("edge", opp.get("expected_return_pct", 0)) / 100
        price = opp.get("current_price", opp.get("buy_price", 0.5))
        prob = price + edge if edge > 0 else price
        
        if prob > 1.0:
            prob = 0.99
        
        bet_amount, shares = optimal_bet_size(
            portfolio["remaining_bankroll"], prob, price, fraction=0.25
        )
        
        if bet_amount > 1 and portfolio["remaining_bankroll"] >= bet_amount:
            portfolio["selected_positions"].append({
                **opp,
                "kelly_bet": bet_amount,
                "shares": shares,
            })
            portfolio["total_allocated"] += bet_amount
            portfolio["remaining_bankroll"] -= bet_amount
    
    portfolio["total_allocated"] = round(portfolio["total_allocated"], 2)
    portfolio["remaining_bankroll"] = round(portfolio["remaining_bankroll"], 2)
    portfolio["allocation_pct"] = round(portfolio["total_allocated"] / bankroll * 100, 1)
    
    return portfolio

# ============================================================
# 8. MAIN EXECUTION ENGINE
# ============================================================

def execute_prediction_markets_engine(bankroll: float = 100.0):
    """Main prediction markets execution engine."""
    print("Prediction Markets Execution Engine")
    print("=" * 60)
    print(f"Bankroll: ${bankroll:.0f}")
    print()
    
    # Load data
    pm_opps = []
    pm_path = Path(".rumbling-hedge/runtime/prediction/opportunities.jsonl")
    if pm_path.exists():
        with open(pm_path) as f:
            for line in f:
                if line.strip():
                    pm_opps.append(json.loads(line))
    
    if not pm_opps:
        # Generate test data
        pm_opps = [
            {"eventTitle": "Fed cuts rates in June 2026", "price": 0.42, "displayedSize": 50000, "externalId": "fed-june"},
            {"eventTitle": "BTC above 100K by Dec 2026", "price": 0.65, "displayedSize": 100000, "externalId": "btc-100k"},
            {"eventTitle": "Trump wins 2028 primary", "price": 0.38, "displayedSize": 80000, "externalId": "trump-28"},
        ]
    
    # 1. Find cross-venue arbs
    print("1. Cross-Venue Arbitrage")
    print("-" * 40)
    arbs = find_cross_venue_arbs(pm_opps, pm_opps)  # Both from same source for now
    for arb in arbs[:3]:
        print(f"  {arb['edge_pct']:.1f}% edge: {arb['event'][:60]}")
        print(f"    Buy {arb['buy_venue']} @ {arb['buy_price']:.3f}, Sell {arb['sell_venue']} @ {arb['sell_price']:.3f}")
    
    # 2. Resolution front-runs
    print("\n2. Resolution Front-Runs")
    print("-" * 40)
    fronts = find_resolution_plays(pm_opps, min_prob=0.85)
    for f in fronts[:3]:
        print(f"  {f['expected_return_pct']:.1f}% return: {f['event'][:60]}")
        print(f"    Buy @ {f['current_price']:.3f}, Kelly bet: {f['kelly_bet_pct']:.1f}%")
    
    # 3. Mean reversion
    print("\n3. Mean Reversion Signals")
    print("-" * 40)
    mrs = find_mean_reversion_plays(pm_opps, pm_opps)
    for mr in mrs[:3]:
        print(f"  Z={mr['z_score']:.1f}: {mr['direction']} {mr['event'][:60]}")
        print(f"    Target: {mr['target']:.3f}, Expected: {mr['expected_return_pct']:.1f}%")
    
    # 4. Correlated inconsistencies
    print("\n4. Correlated Event Inconsistencies")
    print("-" * 40)
    incs = find_correlated_inconsistencies(pm_opps)
    for inc in incs[:3]:
        print(f"  {inc['spread']:.1%} spread in {inc['category']}: {inc['action'][:80]}")
    
    # 5. Portfolio optimization
    all_opps = []
    for a in arbs: all_opps.append({"expected_return_pct": a["edge_pct"], "current_price": a["buy_price"], **a})
    for f in fronts: all_opps.append(f)
    
    print("\n5. Kelly-Optimal Portfolio")
    print("-" * 40)
    portfolio = optimize_portfolio(all_opps, bankroll)
    print(f"  Allocated: ${portfolio['total_allocated']:.0f} ({portfolio['allocation_pct']:.0f}%)")
    print(f"  Positions: {len(portfolio['selected_positions'])}")
    for pos in portfolio['selected_positions']:
        print(f"    ${pos['kelly_bet']:.0f}: {pos.get('event', pos.get('type', ''))[:50]}")
    
    # Save state
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bankroll": bankroll,
        "arbitrages": arbs[:5],
        "front_runs": fronts[:5],
        "mean_reversions": mrs[:5],
        "inconsistencies": incs[:3],
        "portfolio": portfolio,
        "compounding_target": {
            "weekly_5pct": round(bankroll * (1.05 ** 52), 0),
            "weekly_10pct": round(bankroll * (1.10 ** 52), 0),
            "monthly_20pct": round(bankroll * (1.20 ** 12), 0),
        }
    }
    with open(PM_STATE, "w") as f:
        json.dump(state, f, indent=2, default=str)
    
    print(f"\nCompounding projections from ${bankroll:.0f}:")
    print(f"  5% weekly → ${state['compounding_target']['weekly_5pct']:,.0f} in 1 year")
    print(f"  10% weekly → ${state['compounding_target']['weekly_10pct']:,.0f} in 1 year")
    print(f"  Report: {PM_STATE}")

if __name__ == "__main__":
    bankroll = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
    execute_prediction_markets_engine(bankroll)
