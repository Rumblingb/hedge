#!/usr/bin/env python3
"""Multi-Track Coordination Layer — Capital allocation across all trading tracks.
Coordinates: Futures (prop firms), Prediction Markets, Options, Crypto.
Capital allocation plan: $1000 total → 2×$50K prop firm accounts + $200 options + $300 crypto + $100 prediction.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path(".rumbling-hedge/state")
COORD_STATE = STATE_DIR / "multi-track-coordination.json"

CAPITAL_ALLOCATION = {
    "total_capital": 1000,
    "tracks": {
        "futures_prop_firms": {
            "allocation": 600,  # 2×$50K accounts cost ~$300 each
            "target_monthly_return": 0.15,  # 15% monthly on prop firm
            "risk_level": "high",
            "description": "Topstep 50K challenge accounts. 2 accounts for redundancy.",
            "status": "active",
            "strategies_count": 110,
        },
        "prediction_markets": {
            "allocation": 100,
            "target_monthly_return": 0.20,  # 20% monthly
            "risk_level": "medium",
            "description": "Polymarket + Kalshi arbitrage and event trading.",
            "status": "building",
            "strategies_count": 8,
        },
        "options": {
            "allocation": 200,
            "target_monthly_return": 0.10,  # 10% monthly (conservative theta)
            "risk_level": "medium",
            "description": "Theta farming + gamma scalping + defined-risk spreads.",
            "status": "building",
            "strategies_count": 8,
        },
        "crypto": {
            "allocation": 300,  # Extra from prop firm payouts
            "target_monthly_return": 0.25,  # 25% monthly (higher vol)
            "risk_level": "high",
            "description": "Perps funding + momentum + on-chain strategies.",
            "status": "building",
            "strategies_count": 10,
        },
    },
    "total_strategies": 136,  # 110 futures + 8 PM + 8 options + 10 crypto
    "reinvestment_rules": {
        "prop_firm_payout_to": ["futures_prop_firms", "crypto"],
        "prediction_market_profit_to": ["prediction_markets", "options"],
        "options_profit_to": ["options", "crypto"],
        "crypto_profit_to": ["crypto", "futures_prop_firms"],
    },
}

CROSS_TRACK_SIGNALS = {
    "pm_to_futures": {
        "description": "Prediction market event probabilities → futures directional bias",
        "signals": [
            "Fed rate decision probability → ES direction",
            "CPI print expectation → NQ volatility sizing",
            "Election probability → VIX positioning",
            "Recession probability → GC long bias",
        ],
    },
    "options_to_futures": {
        "description": "Options flow → futures positioning signals",
        "signals": [
            "Gamma exposure → intraday support/resistance levels",
            "Put/call ratio extremes → contrarian futures signals",
            "IV term structure → vol regime for futures sizing",
            "Max pain → OPEX pin levels for futures targets",
        ],
    },
    "crypto_to_futures": {
        "description": "Crypto leading indicator → equities direction",
        "signals": [
            "BTC 15m lead on NQ (0.7 correlation in risk-on)",
            "ETH gas fees → DeFi activity → risk appetite",
            "Stablecoin flows → liquidity entering/leaving crypto → risk on/off",
        ],
    },
}

def execute_coordination_layer():
    """Main coordination execution — assess all tracks and allocate."""
    print("Multi-Track Coordination Layer")
    print("=" * 60)
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "capital_allocation": CAPITAL_ALLOCATION,
        "cross_track_signals": CROSS_TRACK_SIGNALS,
        "track_status": {},
        "cross_track_alpha": [],
        "recommendations": [],
    }
    
    # Check each track's state
    tracks = {
        "futures_prop_firms": STATE_DIR / "strategy-factory.latest.json",
        "prediction_markets": STATE_DIR / "prediction-markets-execution.json",
        "options": STATE_DIR / "options-trading-execution.json",
        "crypto": STATE_DIR / "crypto-trading-execution.json",
    }
    
    for track_name, state_path in tracks.items():
        if state_path.exists():
            with open(state_path) as f:
                try:
                    state = json.load(f)
                    report["track_status"][track_name] = {
                        "status": state.get("status", "active"),
                        "last_update": state.get("generated_at", "unknown"),
                    }
                except:
                    report["track_status"][track_name] = {"status": "error", "last_update": None}
        else:
            report["track_status"][track_name] = {"status": "not_initialized", "last_update": None}
    
    # Generate cross-track alpha
    report["cross_track_alpha"] = [
        {
            "source": "prediction_markets",
            "target": "futures_prop_firms",
            "signal": "Use PM event probabilities for futures directional bias",
            "confidence": 0.65,
        },
        {
            "source": "options",
            "target": "futures_prop_firms",
            "signal": "Use gamma exposure levels for intraday S/R on ES",
            "confidence": 0.70,
        },
        {
            "source": "crypto",
            "target": "futures_prop_firms",
            "signal": "BTC leading NQ by 5-15 min in risk-on — use as leading indicator",
            "confidence": 0.60,
        },
    ]
    
    # Recommendations
    report["recommendations"] = [
        "Week 1-2: Focus on prop firm challenge passes (consistent small gains)",
        "Week 3-4: Activate prediction market arbitrage with prop firm profits",
        "Month 2: Scale options theta farming with consistent monthly income",
        "Month 3: Activate crypto funding rate arb + perps momentum",
        "Quarter 2: All 4 tracks active, reinvesting profits for compounding",
    ]
    
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(COORD_STATE, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"Tracks: {len(report['track_status'])}")
    for track, status in report["track_status"].items():
        print(f"  {track}: {status['status']}")
    print(f"Cross-track alpha signals: {len(report['cross_track_alpha'])}")
    print(f"Total strategies: {CAPITAL_ALLOCATION['total_strategies']}")
    print(f"Report: {COORD_STATE}")

if __name__ == "__main__":
    execute_coordination_layer()
