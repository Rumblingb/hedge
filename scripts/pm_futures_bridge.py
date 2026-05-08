#!/usr/bin/env python3
"""Prediction Markets → Futures Correlation Bridge.
Convert prediction market signals into futures trading signals.
Edge: PM moves lead futures by 5-30 minutes on macro events.
"""
import json, math
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path(".rumbling-hedge/state")
BRIDGE_STATE = STATE_DIR / "pm-futures-bridge.json"

# Correlation mappings: PM event → futures action
CORRELATION_MAP = {
    "fed": {
        "futures_symbol": "ES",
        "direction_rule": "rate_cut_prob_up → long, rate_hike_prob_up → short",
        "confidence": 0.65,
        "lead_time_min": 15,
        "examples": ["Fed rate decision", "FOMC minutes", "Fed speech"],
    },
    "inflation": {
        "futures_symbol": "NQ",
        "direction_rule": "CPI_beat → short (hawkish), CPI_miss → long (dovish)",
        "confidence": 0.60,
        "lead_time_min": 5,
        "examples": ["CPI release", "PPI release", "PCE data"],
    },
    "recession": {
        "futures_symbol": "GC",  # Gold = safe haven
        "direction_rule": "recession_prob_up → long GC, short ES",
        "confidence": 0.55,
        "lead_time_min": 60,
        "examples": ["Recession probability", "Yield curve inversion odds"],
    },
    "election": {
        "futures_symbol": "ES",
        "direction_rule": "uncertainty_spike → short, clarity → long",
        "confidence": 0.50,
        "lead_time_min": 1440,  # Days, not minutes
        "examples": ["Presidential election", "Midterm odds"],
    },
    "crypto": {
        "futures_symbol": "NQ",  # Crypto correlation with tech
        "direction_rule": "BTC_ETF_odds_up → long NQ, crypto_ban_odds_up → short",
        "confidence": 0.60,
        "lead_time_min": 30,
        "examples": ["BTC ETF approval", "Crypto regulation", "Stablecoin bill"],
    },
    "trade_war": {
        "futures_symbol": "6E",  # Euro FX most affected
        "direction_rule": "tariff_prob_up → short ES/NQ, long ZB",
        "confidence": 0.55,
        "lead_time_min": 30,
        "examples": ["Tariff announcement", "Trade deal probability"],
    },
}

def analyze_pm_for_futures_signals(pm_opportunities: list) -> list:
    """Convert prediction market probabilities into futures trading signals."""
    signals = []
    
    for opp in pm_opportunities:
        title = (opp.get("eventTitle", "") + " " + opp.get("marketQuestion", "")).lower()
        price = opp.get("price", 0.5)
        
        # Check each correlation
        for pm_category, mapping in CORRELATION_MAP.items():
            # Check if this PM event matches the category
            matched = False
            for example in mapping["examples"]:
                if any(word in title for word in example.lower().split()):
                    matched = True
                    break
            
            if not matched:
                # Check keyword overlap
                if pm_category in title:
                    matched = True
            
            if not matched:
                continue
            
            # Generate futures signal
            if pm_category == "fed":
                # Price = probability of rate CUT
                if price > 0.65:
                    direction = "long"
                    rationale = f"Rate cut probability {price:.0%} → dovish → long ES"
                elif price < 0.35:
                    direction = "short"
                    rationale = f"Rate cut probability {price:.0%} → hawkish → short ES"
                else:
                    continue
            
            elif pm_category == "inflation":
                if price > 0.60:
                    direction = "short"
                    rationale = f"Inflation concern {price:.0%} → hawkish → short NQ"
                elif price < 0.40:
                    direction = "long"
                    rationale = f"Inflation easing {price:.0%} → dovish → long NQ"
                else:
                    continue
            
            elif pm_category == "recession":
                if price > 0.40:
                    direction = "long"  # Long gold for safety
                    rationale = f"Recession fear {price:.0%} → risk-off → long GC"
                else:
                    continue
            
            elif pm_category == "election":
                if 0.40 < price < 0.60:
                    direction = "short"
                    rationale = f"Election uncertainty {price:.0%} → vol → reduce risk"
                else:
                    continue
                
            elif pm_category == "crypto":
                if price > 0.60:
                    direction = "long"
                    rationale = f"Crypto bullish catalyst {price:.0%} → long NQ (tech proxy)"
                else:
                    continue
            
            elif pm_category == "trade_war":
                if price > 0.50:
                    direction = "short"
                    rationale = f"Tariff probability {price:.0%} → risk-off → short ES"
                else:
                    continue
            else:
                continue
            
            signals.append({
                "pm_event": opp.get("eventTitle", "")[:80],
                "pm_category": pm_category,
                "pm_probability": price,
                "futures_symbol": mapping["futures_symbol"],
                "futures_direction": direction,
                "rationale": rationale,
                "confidence": mapping["confidence"],
                "lead_time_min": mapping["lead_time_min"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })
    
    return sorted(signals, key=lambda s: abs(s["pm_probability"] - 0.5), reverse=True)

def execute_bridge():
    """Run the PM → Futures correlation bridge."""
    print("PM → Futures Correlation Bridge")
    print("=" * 60)
    
    # Load PM data
    pm_opps = []
    pm_path = Path(".rumbling-hedge/runtime/prediction/opportunities.jsonl")
    if pm_path.exists():
        with open(pm_path) as f:
            for line in f:
                if line.strip():
                    pm_opps.append(json.loads(line))
    
    if not pm_opps:
        pm_opps = [
            {"eventTitle": "Fed cuts rates in June 2026", "price": 0.42, "displayedSize": 50000},
            {"eventTitle": "US enters recession in 2026", "price": 0.35, "displayedSize": 30000},
            {"eventTitle": "BTC ETF approved by SEC 2026", "price": 0.72, "displayedSize": 80000},
        ]
    
    signals = analyze_pm_for_futures_signals(pm_opps)
    
    print(f"PM events: {len(pm_opps)}")
    print(f"Futures signals: {len(signals)}\n")
    
    for sig in signals:
        print(f"  [{sig['confidence']:.2f}] {sig['futures_direction']} {sig['futures_symbol']}")
        print(f"    {sig['rationale']}")
        print(f"    Lead: {sig['lead_time_min']} min | PM event: {sig['pm_event'][:60]}")
    
    # Save
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(BRIDGE_STATE, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "signals": signals,
            "correlations": CORRELATION_MAP,
        }, f, indent=2, default=str)
    
    print(f"\nBridge report: {BRIDGE_STATE}")

if __name__ == "__main__":
    execute_bridge()
