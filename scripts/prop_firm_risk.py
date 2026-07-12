#!/usr/bin/env python3
"""Prop Firm Risk Management Overlay for Topstep.
Optimizes position sizing, daily loss caps, and consistency rules.
Runs as a meta-layer above all strategies.
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone

class PropFirmRiskManager:
    """Topstep 50K challenge risk management."""
    
    # Topstep rules
    MAX_DAILY_LOSS = 1000.0  # USD
    MAX_TRAILING_DRAWDOWN = 2000.0
    PROFIT_TARGET = 3000.0
    MAX_CONSECUTIVE_LOSSES = 2
    MAX_TRADES_PER_DAY = 3
    RISK_PER_TRADE_PCT = 0.01  # 1% max risk per trade
    CONSISTENCY_RULE = 0.40  # Best day <= 40% of total profit
    
    def __init__(self, account_balance: float = 50000.0):
        self.starting_balance = account_balance
        self.current_balance = account_balance
        self.peak_balance = account_balance
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.consecutive_losses = 0
        self.trades_today = 0
        self.best_day_pnl = 0.0
        self.day_pnls = []
        self.trade_log = []
    
    def can_trade(self, proposed_risk_usd: float, proposed_reward_usd: float) -> tuple[bool, str]:
        """Check if a trade is allowed under prop firm rules."""
        # Daily loss check
        if self.daily_pnl - proposed_risk_usd <= -self.MAX_DAILY_LOSS:
            return False, f"Daily loss limit reached: current PnL ${self.daily_pnl:.0f}"
        
        # Trailing drawdown check
        drawdown = self.peak_balance - (self.current_balance - proposed_risk_usd)
        if drawdown >= self.MAX_TRAILING_DRAWDOWN:
            return False, f"Trailing drawdown breached: ${drawdown:.0f}/{self.MAX_TRAILING_DRAWDOWN}"
        
        # Max trades per day
        if self.trades_today >= self.MAX_TRADES_PER_DAY:
            return False, f"Max daily trades reached: {self.trades_today}/{self.MAX_TRADES_PER_DAY}"
        
        # Consecutive losses
        if self.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            return False, f"Max consecutive losses: {self.consecutive_losses}"
        
        # Risk per trade check
        max_risk = self.current_balance * self.RISK_PER_TRADE_PCT
        if proposed_risk_usd > max_risk:
            return False, f"Risk exceeds {self.RISK_PER_TRADE_PCT*100}%: ${proposed_risk_usd:.0f} > ${max_risk:.0f}"
        
        # Consistency: don't let any single day exceed 40% of total profit target
        projected_best = max(self.best_day_pnl, self.daily_pnl + proposed_reward_usd)
        total_target = self.PROFIT_TARGET
        if projected_best > total_target * self.CONSISTENCY_RULE and self.total_pnl > 0:
            return False, f"Consistency violation: best day ${projected_best:.0f} > {self.CONSISTENCY_RULE*100}% of profit"
        
        return True, "Approved"
    
    def record_trade(self, pnl_usd: float):
        """Record a completed trade."""
        self.current_balance += pnl_usd
        self.daily_pnl += pnl_usd
        self.total_pnl += pnl_usd
        self.trades_today += 1
        
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        
        if pnl_usd > 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
        
        self.trade_log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "pnl": round(pnl_usd, 2),
            "balance": round(self.current_balance, 2),
            "daily_pnl": round(self.daily_pnl, 2),
        })
    
    def end_of_day(self):
        """Reset daily stats."""
        self.day_pnls.append(self.daily_pnl)
        if self.daily_pnl > self.best_day_pnl:
            self.best_day_pnl = self.daily_pnl
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.consecutive_losses = 0
    
    def optimal_position_size(self, stop_distance_ticks: float, tick_value_usd: float) -> int:
        """Calculate optimal contracts given stop distance and risk rules."""
        max_risk = min(
            self.MAX_DAILY_LOSS * 0.33,  # Max 33% of daily loss per trade
            self.current_balance * self.RISK_PER_TRADE_PCT,
            (self.MAX_TRAILING_DRAWDOWN - (self.peak_balance - self.current_balance)) * 0.5
        )
        if max_risk <= 0:
            return 0
        risk_per_contract = stop_distance_ticks * tick_value_usd
        if risk_per_contract <= 0:
            return 1
        contracts = int(max_risk / risk_per_contract)
        return max(1, min(contracts, 2))  # Cap at 2 for challenge phase
    
    def status_report(self) -> dict:
        return {
            "starting_balance": self.starting_balance,
            "current_balance": round(self.current_balance, 2),
            "peak_balance": round(self.peak_balance, 2),
            "total_pnl": round(self.total_pnl, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "trades_today": self.trades_today,
            "consecutive_losses": self.consecutive_losses,
            "best_day": round(self.best_day_pnl, 2),
            "drawdown_remaining": round(self.MAX_TRAILING_DRAWDOWN - (self.peak_balance - self.current_balance), 2),
            "daily_loss_remaining": round(self.MAX_DAILY_LOSS + self.daily_pnl, 2),
            "profit_to_target": round(self.PROFIT_TARGET - self.total_pnl, 2),
        }

if __name__ == "__main__":
    # Test the risk manager
    rm = PropFirmRiskManager(50000)
    can, reason = rm.can_trade(200, 400)
    print(f"Trade 1: {can} - {reason}")
    print(json.dumps(rm.status_report(), indent=2))
