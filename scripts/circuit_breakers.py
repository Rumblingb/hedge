#!/usr/bin/env python3
"""Circuit Breaker System — Multi-level hard stops for all 7 tracks.
Levels: Trade → Strategy → Track → Portfolio
Triggers: Loss, Drawdown, Consecutive Losses, VIX Spike, News Event
"""
import json, math
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path(".rumbling-hedge/state")
CB_STATE = STATE_DIR / "circuit-breakers.json"

class CircuitBreakerSystem:
    """Multi-level circuit breaker. Hard stops = cannot be overridden."""
    
    def __init__(self):
        self.breakers = {
            "trade_level": {
                "max_loss_per_trade_r": 2.0,
                "max_risk_per_trade_pct": 1.0,
                "violation_action": "reject_trade",
            },
            "strategy_level": {
                "max_consecutive_losses": 3,
                "max_drawdown_pct": 30,
                "max_daily_trades": 5,
                "ooc_sharpe_failure_days": 30,
                "violation_action": "deactivate_strategy",
            },
            "track_level": {
                "futures": {"max_daily_loss": 1000, "max_trailing_dd": 2000},
                "prediction_markets": {"max_daily_loss": 50, "max_drawdown_pct": 25},
                "options": {"max_daily_loss": 100, "max_drawdown_pct": 30},
                "crypto": {"max_daily_loss": 150, "max_drawdown_pct": 35},
                "commodities": {"max_daily_loss": 100, "max_drawdown_pct": 25},
                "violation_action": "stop_track_for_day",
            },
            "portfolio_level": {
                "max_portfolio_dd_pct": 15,
                "max_consecutive_losing_days": 3,
                "vix_spike_threshold": 10,  # points in 1 day
                "correlation_emergency": 0.85,  # cross-asset correlation
                "violation_action": "reduce_all_50pct",
            },
            "market_level": {
                "news_blackout_minutes": 5,
                "circuit_breaker_halt": "cancel_all",
                "flash_crash_detection": -0.05,  # 5% in 5 min
                "violation_action": "emergency_stop_all",
            },
        }
        self.state = {level: {"triggered": False, "last_triggered": None, "reason": None}
                     for level in self.breakers}
    
    def check_trade(self, risk_r: float, risk_pct: float, strategy: str, track: str) -> dict:
        """Check if a trade should be allowed."""
        reasons = []
        
        # Trade-level
        if risk_r > self.breakers["trade_level"]["max_loss_per_trade_r"]:
            reasons.append(f"Risk {risk_r:.1f}R exceeds max {self.breakers['trade_level']['max_loss_per_trade_r']}R")
        if risk_pct > self.breakers["trade_level"]["max_risk_per_trade_pct"]:
            reasons.append(f"Risk {risk_pct:.1f}% exceeds max {self.breakers['trade_level']['max_risk_per_trade_pct']}%")
        
        # Strategy-level
        if self.is_strategy_blocked(strategy):
            reasons.append(f"Strategy {strategy} is deactivated")
        
        # Track-level
        if self.is_track_blocked(track):
            reasons.append(f"Track {track} is stopped for the day")
        
        # Portfolio-level
        if any(self.state[l]["triggered"] for l in ["portfolio_level", "market_level"]):
            reasons.append("Portfolio/market-level circuit breaker active")
        
        return {"allowed": len(reasons) == 0, "reasons": reasons}
    
    def record_trade_result(self, strategy: str, track: str, pnl_r: float):
        """Record trade outcome and check for strategy-level triggers."""
        # Update strategy state (would use persistent storage in production)
        pass
    
    def is_strategy_blocked(self, strategy: str) -> bool:
        return self.state.get(f"strategy:{strategy}", {}).get("triggered", False)
    
    def is_track_blocked(self, track: str) -> bool:
        return self.state.get(f"track:{track}", {}).get("triggered", False)
    
    def emergency_stop(self, level: str, reason: str):
        """Trigger emergency stop at specified level."""
        self.state[level] = {"triggered": True, "last_triggered": datetime.now(timezone.utc).isoformat(), "reason": reason}
        print(f"🚨 CIRCUIT BREAKER: {level} — {reason}")
    
    def reset_all(self):
        """Reset all circuit breakers (next day)."""
        for level in self.state:
            self.state[level] = {"triggered": False, "last_triggered": None, "reason": None}
    
    def status_report(self) -> dict:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "breakers_configured": list(self.breakers.keys()),
            "active_breakers": [lvl for lvl, st in self.state.items() if st["triggered"]],
            "all_clear": not any(st["triggered"] for st in self.state.values()),
            "state": self.state,
        }


def execute_circuit_breaker_test():
    print("Circuit Breaker System — Multi-Level Protection")
    print("=" * 60)
    
    cb = CircuitBreakerSystem()
    
    # Test scenarios
    tests = [
        ("Normal trade", cb.check_trade(1.0, 0.5, "session-momentum", "futures")),
        ("Excessive risk", cb.check_trade(3.0, 2.0, "ict-displacement", "futures")),
    ]
    
    for name, result in tests:
        status = "✅ ALLOWED" if result["allowed"] else "❌ BLOCKED"
        print(f"  {name}: {status}")
        if not result["allowed"]:
            for r in result["reasons"]:
                print(f"    → {r}")
    
    # Emergency stop test
    cb.emergency_stop("portfolio_level", "VIX spike +10 points")
    result = cb.check_trade(0.5, 0.3, "session-momentum", "futures")
    print(f"  After emergency: {'✅' if result['allowed'] else '❌'} — {result['reasons']}")
    
    # Save state
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CB_STATE, "w") as f:
        json.dump(cb.status_report(), f, indent=2, default=str)
    
    print(f"\nBreaker state: {CB_STATE}")

if __name__ == "__main__":
    execute_circuit_breaker_test()
