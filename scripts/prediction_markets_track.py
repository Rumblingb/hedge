#!/usr/bin/env python3
"""Prediction Markets Research Track — Polymarket + Kalshi candidate strategies.

This file intentionally produces research/paper-candidate signals only. It must
not place orders, move funds, or be used as a live execution policy.
"""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", ".rumbling-hedge/state")).expanduser()
JOURNAL_PATH = Path(".rumbling-hedge/runtime/prediction/opportunities.jsonl")
PM_STATE = STATE_DIR / "prediction-markets-research-track.latest.json"

RESEARCH_SAFETY = {
    "researchOnly": True,
    "writesOrders": False,
    "touchesBroker": False,
    "movesFunds": False,
    "readyForPaper": False,
    "readyForExecution": False,
    "tradable_signal": False,
}

MAX_REFERENCE_STAKE_USD = 10

# Prediction market strategies
PREDICTION_STRATEGIES = {
    "arbitrage": {
        "name": "Cross-Venue Arbitrage",
        "description": "Buy low on Kalshi, sell high on Polymarket (or vice versa). Same event, different prices.",
        "minEdge": 0.01,  # exploratory threshold only; never promotes without paper gate
        "maxStake": 10,   # reference cap for a $100 bankroll
        "enabled": True,
    },
    "event-fade": {
        "name": "Event Fade",
        "description": "Fade the initial overreaction on news events. 80%+ win rate on non-binary events.",
        "minConfidence": 0.55,  # exploratory threshold only; do not use for paper/live promotion
        "maxStake": 8,
        "enabled": True,
    },
    "momentum-follow": {
        "name": "Momentum Follow",
        "description": "Follow sustained price movement > 2% in last hour. Trend continuation.",
        "minMove": 0.02,  # exploratory threshold only; do not use for paper/live promotion
        "maxStake": 8,
        "enabled": True,
    },
    "mean-reversion": {
        "name": "Mean Reversion",
        "description": "Price > 1.5 std from 24h mean → fade. Works on liquid markets.",
        "zThreshold": 1.5,  # exploratory threshold only; do not use for paper/live promotion
        "maxStake": 6,
        "enabled": True,
    },
    "liquidity-provision": {
        "name": "Liquidity Provision",
        "description": "Provide liquidity at wide spreads on low-activity markets. Collect spread.",
        "minSpread": 0.05,
        "maxStake": 15,
        "enabled": False,  # Requires active order management
    },
    "resolution-frontrun": {
        "name": "Resolution Front-Run",
        "description": "Buy near-certain outcomes below 95c just before resolution.",
        "minProb": 0.9,
        "maxStake": 10,
        "enabled": True,
    },
    "news-reaction": {
        "name": "News Reaction",
        "description": "React to breaking news before market fully prices it. Speed-based edge.",
        "maxStake": 8,
        "enabled": True,
    },
    "volume-breakout": {
        "name": "Volume Breakout",
        "description": "Unusual volume spike → follow the volume direction.",
        "volThreshold": 3.0,  # 3x normal volume
        "maxStake": 8,
        "enabled": True,
    },
}


def reference_stake(config: dict, raw_stake: int | float) -> int:
    """Return a capped research-only sizing reference for a $100 bankroll."""
    return int(max(0, min(MAX_REFERENCE_STAKE_USD, config.get("maxStake", MAX_REFERENCE_STAKE_USD), raw_stake)))


def watch_action(side: str) -> str:
    return f"watch-{side}-candidate"

def analyze_opportunity(event: dict, strategy: str) -> dict or None:
    """Analyze a prediction market opportunity for a specific strategy."""
    config = PREDICTION_STRATEGIES[strategy]
    if not config.get("enabled", False):
        return None
    
    price = event.get("price", 0.5)
    volume = event.get("displayedSize", 0)
    title = event.get("eventTitle", "")
    
    if strategy == "arbitrage":
        edge = event.get("edge", 0)
        if edge >= config["minEdge"]:
            return {
                "strategy": strategy,
                "action": watch_action("buy") if price < 0.5 else watch_action("sell"),
                "confidence": min(1, edge / 0.1),
                "stake": reference_stake(config, int(edge * 1000)),
                "reason": f"Cross-venue edge: {edge:.1%}",
                "watchCandidateOnly": True,
                "paperCandidateOnly": False,
            }
    
    elif strategy == "resolution-frontrun":
        if price > config["minProb"]:
            remaining = 1.0 - price
            return {
                "strategy": strategy,
                "action": watch_action("buy"),
                "confidence": price,
                "stake": reference_stake(config, int(remaining * 500)),
                "reason": f"Near-certain at {price:.1%}, {remaining:.1%} upside",
                "watchCandidateOnly": True,
                "paperCandidateOnly": False,
            }
    
    elif strategy == "mean-reversion":
        z = event.get("zScore", 0)
        if abs(z) > config["zThreshold"]:
            return {
                "strategy": strategy,
                "action": watch_action("buy") if z < 0 else watch_action("sell"),
                "confidence": min(1, abs(z) / 4),
                "stake": reference_stake(config, config["maxStake"]),
                "reason": f"Z-score: {z:.1f}, reverting",
                "watchCandidateOnly": True,
                "paperCandidateOnly": False,
            }
    
    return None

def execute_prediction_track():
    """Main prediction markets research loop."""
    print("Prediction Markets Track — Research-only")
    print("=" * 50)
    
    # Load latest opportunities
    opportunities = []
    if JOURNAL_PATH.exists():
        with open(JOURNAL_PATH) as f:
            for line in f:
                if line.strip():
                    opportunities.append(json.loads(line))
    
    print(f"Loaded {len(opportunities)} opportunities")
    
    # Analyze each opportunity against all strategies
    signals = []
    for opp in opportunities[-50:]:  # Last 50 opportunities
        for strategy in PREDICTION_STRATEGIES:
            result = analyze_opportunity(opp, strategy)
            if result:
                signals.append({**result, "event": opp.get("eventTitle", "")[:80]})
    
    # Sort by confidence
    signals.sort(key=lambda s: s["confidence"], reverse=True)
    
    # Generate execution report
    report = {
        **RESEARCH_SAFETY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": "research-only-prediction-candidates-visible",
        "total_opportunities": len(opportunities),
        "signals_generated": len(signals),
        "by_strategy": {},
        "top_signals": signals[:10],
        "capital_allocation": {
            "total_available": 100,  # Small starting capital
            "per_trade_max": MAX_REFERENCE_STAKE_USD,
            "max_concurrent": 5,
            "referenceOnly": True,
        },
        "thresholdMode": "exploratory-watch-only",
        "promotionGate": (
            "Lowered thresholds may create watch candidates only. Paper/live promotion still requires "
            "the prediction paper-promotion gate, fillability proof, operator approval, and execution firewall."
        ),
    }
    
    for s in signals:
        strat = s["strategy"]
        if strat not in report["by_strategy"]:
            report["by_strategy"][strat] = 0
        report["by_strategy"][strat] += 1
    
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PM_STATE, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"Signals: {len(signals)}")
    for s in signals[:5]:
        print(f"  [{s['confidence']:.2f}] {s['strategy']}: {s['action']} ({s['reason'][:50]})")
    print(f"Report: {PM_STATE}")

if __name__ == "__main__":
    execute_prediction_track()
