#!/usr/bin/env python3
"""Options Strategy Research Module — Stub for Fable 5.

This file is the entry point for options strategy development.
Currently a placeholder — all options strategies are TODO.

Goals:
1. CBOE options chain data ingestion
2. Delta-neutral / vol arb signal generation
3. Tail risk hedge construction
4. Multi-leg option strategy backtesting

Data sources to investigate:
- Polygon.io options chain API
- CBOE data shop
- Yahoo Finance options chains (delayed, free)
- Tradier API (cheap, good options data)

Account considerations:
- Topstep does NOT support options trading
- Options would need a separate brokerage account (Tastyworks, IBKR, Tradier)
- This module is for research/signal generation only until a funded options account exists
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".rumbling-hedge" / "state"
OPTIONS_STATE = STATE / "options"


def chain_file(symbol: str, expiry: str) -> Path:
    """Path to cached options chain data."""
    OPTIONS_STATE.mkdir(parents=True, exist_ok=True)
    return OPTIONS_STATE / f"{symbol}-{expiry}.json"


class OptionsStrategy:
    """Base class for options strategies. Subclass and implement."""
    
    def __init__(self, name: str):
        self.name = name
        self.positions: list[dict] = []
    
    def generate_signal(self) -> dict:
        """Return signal dict with direction, confidence, reason."""
        raise NotImplementedError
    
    def place_order(self) -> bool:
        """Execute the strategy (stub)."""
        print(f"[options] {self.name}: order stub — no broker connected")
        return False


class DeltaNeutralStraddle(OptionsStrategy):
    """Market-neutral straddle — short vol when IV > HV, long vol when IV < HV."""
    
    def __init__(self):
        super().__init__("delta-neutral-straddle")
    
    def generate_signal(self) -> dict:
        return {
            "strategy": self.name,
            "direction": "neutral",
            "confidence": 0.0,
            "reason": "stub — not implemented",
            "promoted_for_execution": False,
        }


class TailRiskHedge(OptionsStrategy):
    """Out-of-the-money put spread as portfolio hedge during high-regime uncertainty."""
    
    def __init__(self):
        super().__init__("tail-risk-hedge")
    
    def generate_signal(self) -> dict:
        return {
            "strategy": self.name,
            "direction": "bearish",
            "confidence": 0.0,
            "reason": "stub — not implemented",
            "promoted_for_execution": False,
        }


if __name__ == "__main__":
    print("Options Research Module — Stub")
    print("Fable 5: implement data ingestion + signal generation here")
