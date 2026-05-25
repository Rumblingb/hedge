#!/usr/bin/env python3
"""
PEAD — Post-Earnings Announcement Drift Signal Generator
========================================================
Institutional strategy validated across 53 years of academic research.
Generates NQ/ES directional signals from top component earnings.

Source: Matteo Conti (former market maker, €30M+ PnL)
Papers: Ball & Brown (1968), Bernard & Thomas (1989), 
        Livnat & Mendenhall (2006), Fink (2021)

Strategy rules:
• LONG: Earnings beat consensus AND stock reacts positively (concordant filter)
• SHORT: Earnings miss consensus AND stock reacts negatively
• NO TRADE: Surprise and price reaction disagree
• Exit: 60 trading days from entry (no SL/TP)
• Sizing: Fixed % of capital per position

Output: ~/.rumbling-hedge/state/pead-signal.latest.json
"""

import json, os, sys, math, time
from pathlib import Path
from datetime import datetime, timedelta, date, timezone
from typing import Optional, Dict, List, Tuple

STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "pead-signal.latest.json"
EARNINGS_CACHE = STATE_DIR / "pead-earnings-cache.json"

# NQ Top Components (top ~15 by weighting in Nasdaq 100)
# We track these for earnings events → trade NQ directionally
NQ_TOP_COMPONENTS = {
    "AAPL": {"name": "Apple Inc.", "sector": "Tech"},
    "MSFT": {"name": "Microsoft Corp.", "sector": "Tech"},
    "NVDA": {"name": "NVIDIA Corp.", "sector": "Semiconductor"},
    "GOOGL": {"name": "Alphabet Inc.", "sector": "Tech"},
    "AMZN": {"name": "Amazon.com Inc.", "sector": "Consumer/Cloud"},
    "META": {"name": "Meta Platforms Inc.", "sector": "Tech"},
    "TSLA": {"name": "Tesla Inc.", "sector": "Automotive"},
    "AVGO": {"name": "Broadcom Inc.", "sector": "Semiconductor"},
    "COST": {"name": "Costco Wholesale", "sector": "Retail"},
    "GOOG": {"name": "Alphabet Inc. (C)", "sector": "Tech"},
    "NFLX": {"name": "Netflix Inc.", "sector": "Entertainment"},
    "AMD": {"name": "Advanced Micro Devices", "sector": "Semiconductor"},
    "ADBE": {"name": "Adobe Inc.", "sector": "Software"},
    "PEP": {"name": "PepsiCo Inc.", "sector": "Consumer"},
    "LIN": {"name": "Linde plc", "sector": "Industrial"},
}

# Known earnings dates (approximate seasonal patterns)
# In production, fetch from Zacks/IBKR/Financial Modeling Prep
EARNINGS_SEASONS = {
    "Q1": (date(2026, 4, 10), date(2026, 5, 15)),  # Jan-Mar results
    "Q2": (date(2026, 7, 10), date(2026, 8, 14)),  # Apr-Jun results
    "Q3": (date(2026, 10, 8), date(2026, 11, 13)),  # Jul-Sep results
    "Q4": (date(2027, 1, 8), date(2027, 2, 15)),    # Oct-Dec results
}

TRADING_DAYS_60 = 60  # hold period (Bernard & Thomas 1989)

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")

class PEADScanner:
    def __init__(self):
        self.cache = self._load_cache()
        
    def _load_cache(self) -> dict:
        if EARNINGS_CACHE.exists():
            try:
                with open(EARNINGS_CACHE) as f:
                    return json.load(f)
            except:
                pass
        return {"earnings": {}, "active_positions": []}
    
    def _save_cache(self):
        with open(EARNINGS_CACHE, "w") as f:
            json.dump(self.cache, f, indent=2)
    
    def get_trading_days_forward(self, from_date: date, days: int) -> date:
        """Approximate calendar days for N trading days (~1.4x multiplier)"""
        return from_date + timedelta(days=int(days * 1.4))
    
    def check_earnings_calendar(self) -> List[dict]:
        """
        Check which NQ components have upcoming earnings.
        In production: fetch from Zacks API, IBKR, or Financial Modeling Prep.
        
        For now: returns the seasonal earnings window + known dates
        Returns list of {ticker, report_date_est, consensus_eps, consensus_rev}
        """
        today = date.today()
        upcoming = []
        
        for ticker, info in NQ_TOP_COMPONENTS.items():
            # Check if this ticker has cached earnings data
            cached = self.cache.get("earnings", {}).get(ticker, {})
            
            # Simple heuristic: assume Q2 2026 is approaching (May-Jun 2026)
            # In production: fetch from API
            report_date = None
            if cached.get("report_date"):
                report_date = datetime.fromisoformat(cached["report_date"]).date()
            
            if report_date and abs((report_date - today).days) <= 14:
                upcoming.append({
                    "ticker": ticker,
                    "name": info["name"],
                    "sector": info["sector"],
                    "report_date": report_date.isoformat(),
                    "consensus_eps": cached.get("consensus_eps"),
                    "consensus_rev": cached.get("consensus_rev"),
                    "days_until": (report_date - today).days,
                })
        
        return upcoming
    
    def fetch_earnings_result(self, ticker: str) -> Optional[Dict]:
        """
        Fetch actual earnings result for a ticker that just reported.
        
        In production:
        - Use Financial Modeling Prep API
        - Use Yahoo Finance (yfinance)
        - Use Zacks API
        - Use IBKR fundamentals
        
        For now: check if cached result exists
        """
        cached = self.cache.get("earnings", {}).get(ticker, {})
        if cached.get("actual_eps") is not None:
            return cached
        return None
    
    def check_price_reaction(self, ticker: str, report_date: date) -> Optional[str]:
        """
        Check if the stock reacted positively or negatively on reaction day.
        
        Reaction day:
        - BMO (Before Market Open): reaction day = same trading day
        - AMC (After Close): reaction day = next trading session
        
        Returns: "positive", "negative", or None if unclear
        """
        cached = self.cache.get("earnings", {}).get(ticker, {})
        return cached.get("reaction_direction")
    
    def evaluate_pead_signal(self, ticker: str) -> Optional[Dict]:
        """
        Full PEAD signal evaluation for a ticker.
        
        Returns signal dict if concordant, None otherwise.
        """
        cached = self.cache.get("earnings", {}).get(ticker, {})
        
        actual_eps = cached.get("actual_eps")
        consensus_eps = cached.get("consensus_eps")
        reaction = cached.get("reaction_direction")
        
        if actual_eps is None or consensus_eps is None or reaction is None:
            return None
        
        # Calculate surprise
        if consensus_eps != 0:
            surprise_pct = ((actual_eps - consensus_eps) / abs(consensus_eps)) * 100
        else:
            surprise_pct = 100 if actual_eps > 0 else -100
        
        beat = actual_eps > consensus_eps
        miss = actual_eps < consensus_eps
        
        # Concordant filter
        if beat and reaction == "positive":
            direction = "long"
            confidence = min(0.5 + abs(surprise_pct) * 0.005, 0.75)
        elif miss and reaction == "negative":
            direction = "short"
            confidence = min(0.5 + abs(surprise_pct) * 0.005, 0.75)
        else:
            # Discordant — no trade
            return None
        
        report_date_str = cached.get("report_date", "")
        entry_date = self._get_entry_date(report_date_str)
        exit_date = self.get_trading_days_forward(entry_date, TRADING_DAYS_60)
        
        return {
            "strategy": "pead",
            "signal": direction,
            "ticker": ticker,
            "name": NQ_TOP_COMPONENTS.get(ticker, {}).get("name", ticker),
            "surprise_pct": round(surprise_pct, 2),
            "beat": beat,
            "reaction": reaction,
            "concordant": True,
            "confidence": round(confidence, 3),
            "entry_date": entry_date.isoformat(),
            "exit_date": exit_date.isoformat(),
            "hold_trading_days": TRADING_DAYS_60,
            "quantity": None,  # Set by execution layer
            "strike": f"Signal on {ticker} → trade NQ directionally",
            "nq_direction": direction,  # The actual instrument we trade
            "source": "pead-institutional-strategy",
        }
    
    def _get_entry_date(self, report_date_str: str) -> date:
        """Entry at open of session FOLLOWING reaction day"""
        try:
            rd = datetime.fromisoformat(report_date_str).date()
        except:
            rd = date.today()
        # Next trading day
        next_day = rd + timedelta(days=1)
        # Skip weekends (simple version)
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        return next_day
    
    def check_active_positions_for_exit(self) -> List[Dict]:
        """Check if any active PEAD positions have reached 60-day exit"""
        today = date.today()
        to_close = []
        
        for pos in self.cache.get("active_positions", []):
            exit_date = datetime.fromisoformat(pos["exit_date"]).date()
            if today >= exit_date:
                to_close.append(pos)
                log(f"PEAD EXIT: {pos['ticker']} {pos['direction']} — held {pos.get('hold_days', TRADING_DAYS_60)} days")
        
        return to_close
    
    def run(self):
        """Main execution"""
        log("PEAD Earnings Drift Scanner — Running")
        
        # 1. Check active positions for exit
        to_close = self.check_active_positions_for_exit()
        
        # 2. Check upcoming earnings
        upcoming = self.check_earnings_calendar()
        log(f"Upcoming earnings in next 14 days: {len(upcoming)} events")
        for u in upcoming:
            log(f"  {u['ticker']} ({u['name']}) — {u['days_until']} days")
        
        # 3. Evaluate signals for tickers with fresh earnings data
        signals = []
        for ticker in NQ_TOP_COMPONENTS:
            signal = self.evaluate_pead_signal(ticker)
            if signal:
                signals.append(signal)
                log(f"PEAD SIGNAL: {signal['signal'].upper()} {ticker} (surprise: {signal['surprise_pct']:+.1f}%)")
        
        # 4. Build output
        active_positions = self.cache.get("active_positions", [])
        
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strategy": "PEAD — Post-Earnings Announcement Drift",
            "active_signals": signals,
            "active_positions": active_positions,
            "positions_to_close": [p["ticker"] for p in to_close],
            "upcoming_earnings": upcoming,
            "nq_bias": self._compute_nq_bias(signals),
            "total_events_tracked": len(NQ_TOP_COMPONENTS),
            "hold_trading_days": TRADING_DAYS_60,
        }
        
        with open(STATE_FILE, "w") as f:
            json.dump(output, f, indent=2)
        
        log(f"✅ Written to {STATE_FILE}")
        if signals:
            log(f"  → {len(signals)} active PEAD signals")
        if to_close:
            log(f"  → {len(to_close)} positions to close")
        log(f"  → NQ bias: {output['nq_bias']}")
        
        return output
    
    def _compute_nq_bias(self, signals: List[Dict]) -> str:
        longs = sum(1 for s in signals if s["signal"] == "long")
        shorts = sum(1 for s in signals if s["signal"] == "short")
        if longs > shorts:
            return "bullish"
        elif shorts > longs:
            return "bearish"
        return "neutral"
    
    def add_earnings_data(self, ticker: str, report_date: str, 
                          consensus_eps: float, actual_eps: float, 
                          reaction: str):
        """Manually add earnings data for testing / API ingestion"""
        if "earnings" not in self.cache:
            self.cache["earnings"] = {}
        
        self.cache["earnings"][ticker] = {
            "report_date": report_date,
            "consensus_eps": consensus_eps,
            "actual_eps": actual_eps,
            "reaction_direction": reaction,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_cache()
        log(f"Cached earnings data for {ticker}")

if __name__ == "__main__":
    scanner = PEADScanner()
    
    # If arguments provided, add earnings data
    if len(sys.argv) >= 5 and sys.argv[1] == "add":
        ticker = sys.argv[2]
        report_date = sys.argv[3]
        consensus_eps = float(sys.argv[4])
        actual_eps = float(sys.argv[5])
        reaction = sys.argv[6] if len(sys.argv) > 6 else "positive"
        scanner.add_earnings_data(ticker, report_date, consensus_eps, actual_eps, reaction)
    
    elif len(sys.argv) >= 2 and sys.argv[1] == "test":
        # Test mode — inject known examples
        log("=== PEAD TEST MODE ===")
        today = date.today()
        
        # Example 1: AAPL beats and reacts positively → LONG signal
        scanner.add_earnings_data("AAPL", today.isoformat(), 2.45, 2.83, "positive")
        
        # Example 2: TSLA misses and reacts negatively → SHORT signal
        scanner.add_earnings_data("TSLA", today.isoformat(), 0.72, 0.58, "negative")
        
        # Example 3: META beats but reacts negatively → NO SIGNAL (discordant)
        scanner.add_earnings_data("META", today.isoformat(), 5.12, 5.35, "negative")
        
        # Example 4: NVDA beats strongly and reacts very positively → STRONG LONG
        scanner.add_earnings_data("NVDA", today.isoformat(), 0.95, 1.42, "positive")
        
        scanner.run()
    
    else:
        # Production mode
        scanner.run()
