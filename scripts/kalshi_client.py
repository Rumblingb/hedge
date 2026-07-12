#!/usr/bin/env python3
"""
kalshi_client.py — Kalshi public-market scanner for Bill/Hermes.

This is research-only infrastructure. It may read public demo/prod market data
and write candidate observations, but it must not place orders, move funds, or
claim paper/live readiness.
"""
import json, os, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests

# API endpoints
DEMO_BASE = "https://external-api.demo.kalshi.co/trade-api/v2"
PROD_BASE = "https://external-api.kalshi.com/trade-api/v2"

HOME = Path.home()
BILL_ENV = HOME / "Library/Application Support/AgentPay/bill/bill.env"
STATE_DIR = HOME / "hedge" / ".rumbling-hedge" / "state"
STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", str(STATE_DIR))).expanduser()

RESEARCH_SAFETY = {
    "researchOnly": True,
    "writesOrders": False,
    "touchesBroker": False,
    "movesFunds": False,
    "readyForPaper": False,
    "readyForExecution": False,
    "tradable_signal": False,
}

class KalshiClient:
    """Kalshi prediction market client — demo or production."""
    
    def __init__(self, demo=True):
        self.base = DEMO_BASE if demo else PROD_BASE
        self.demo = demo
        self.api_key = None
        self.private_key = None
        self.allow_authenticated_reads = os.environ.get("BILL_KALSHI_ALLOW_AUTH_READS", "false").lower() == "true"
        self._load_env()
    
    def _load_env(self):
        if BILL_ENV.exists():
            for line in BILL_ENV.read_text().splitlines():
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:]
                if "KALSHI_API_KEY" in line:
                    self.api_key = line.split("=", 1)[1].strip().strip("'\"")
                if "KALSHI_PRIVATE_KEY" in line:
                    self.private_key = line.split("=", 1)[1].strip().strip("'\"")
    
    def _headers(self, auth=False):
        h = {"Content-Type": "application/json"}
        if auth and self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h
    
    def get_markets(self, status="open", limit=50, category=None):
        """Get available markets."""
        params = {"status": status, "limit": limit}
        if category:
            params["category"] = category
        r = requests.get(f"{self.base}/markets", headers=self._headers(), params=params)
        r.raise_for_status()
        return r.json()
    
    def get_market(self, ticker):
        r = requests.get(f"{self.base}/markets/{ticker}", headers=self._headers())
        r.raise_for_status()
        return r.json()
    
    def get_orderbook(self, ticker):
        r = requests.get(f"{self.base}/markets/{ticker}/orderbook", headers=self._headers())
        r.raise_for_status()
        return r.json()
    
    def get_balance(self):
        """Requires authentication and explicit read-only opt-in."""
        if not self.allow_authenticated_reads:
            raise PermissionError("Kalshi account reads are disabled; set BILL_KALSHI_ALLOW_AUTH_READS=true for read-only checks.")
        r = requests.get(f"{self.base}/portfolio/balance", headers=self._headers(auth=True))
        r.raise_for_status()
        return r.json()
    
    def get_positions(self):
        """Requires authentication and explicit read-only opt-in."""
        if not self.allow_authenticated_reads:
            raise PermissionError("Kalshi account reads are disabled; set BILL_KALSHI_ALLOW_AUTH_READS=true for read-only checks.")
        r = requests.get(f"{self.base}/portfolio/positions", headers=self._headers(auth=True))
        r.raise_for_status()
        return r.json()
    
    def scan_opportunities(self, min_edge=0.01, max_stake=10):
        """Scan markets for trading opportunities."""
        try:
            markets_data = self.get_markets(limit=50)
        except Exception as e:
            return {"error": str(e), "opportunities": []}
        
        opps = []
        for m in markets_data.get("markets", []):
            ticker = m.get("ticker", "")
            title = m.get("title", "")
            yes_bid = float(m.get("yes_bid_dollars", 0) or 0)
            yes_ask = float(m.get("yes_ask_dollars", 0) or 0)
            no_bid = float(m.get("no_bid_dollars", 0) or 0)
            no_ask = float(m.get("no_ask_dollars", 0) or 0)
            volume = float(m.get("volume_24h_fp", 0) or 0)
            close_ts = m.get("close_time", "")
            
            # Skip markets closing soon
            if close_ts:
                try:
                    close_dt = datetime.fromisoformat(close_ts.replace("Z", "+00:00"))
                    if close_dt < datetime.now(timezone.utc) + timedelta(hours=1):
                        continue
                except:
                    pass
            
            # Arbitrage: yes_bid + no_bid > 1.00?
            if yes_bid and no_bid:
                arb = (yes_bid + no_bid) - 1.0
                if arb > min_edge:
                    confidence = min(1.0, arb / min_edge)
                    opps.append({
                        "type": "arbitrage",
                        "paperCandidateOnly": True,
                        "ticker": ticker,
                        "title": title,
                        "edge": round(arb, 4),
                        "stake": min(max_stake, max_stake * arb / min_edge),
                        "confidence": round(confidence, 2),
                        "volume": volume,
                        "action": f"RESEARCH: observe YES bid {yes_bid} + NO bid {no_bid}"
                    })
            
            # Value: yes_ask < 0.40 with high volume?
            if yes_ask and yes_ask < 0.40 and volume > 1000:
                opps.append({
                    "type": "value_buy",
                    "paperCandidateOnly": True,
                    "ticker": ticker,
                    "title": title,
                    "price": yes_ask,
                    "stake": min(max_stake, max_stake * 0.5),
                    "confidence": round(1.0 - yes_ask, 2),
                    "volume": volume,
                    "action": f"RESEARCH: observe YES ask {yes_ask}"
                })
        
        opps.sort(key=lambda x: x.get("edge", x.get("confidence", 0)), reverse=True)
        return {
            **RESEARCH_SAFETY,
            "opportunities": opps,
            "count": len(opps),
            "base": self.base,
            "demo": self.demo,
            "mode": "public-market-scan",
            "minEdge": min_edge,
            "maxStakeReferenceOnly": max_stake,
        }

def run_kalshi_scan():
    """Run a Kalshi scan and save results."""
    client = KalshiClient(demo=True)
    result = client.scan_opportunities(min_edge=0.01, max_stake=10)
    
    # Save to state
    out = STATE_DIR / "kalshi-opportunities.latest.json"
    result["ts"] = datetime.now(timezone.utc).isoformat()
    result["bankroll"] = 100.0
    result["capitalPlan"] = "$100 bankroll is a research sizing reference only; do not place Kalshi/Polymarket orders from this artifact."
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    
    print(f"Scanned Kalshi public markets ({'DEMO' if client.demo else 'PROD'})")
    print(f"  Base: {client.base}")
    print(f"  Has API key: {bool(client.api_key)}")
    print("  Safety: researchOnly=true writesOrders=false touchesBroker=false")
    print(f"  Opportunities: {result['count']}")
    
    for opp in result.get("opportunities", [])[:5]:
        print(f"  [{opp['type']:12s}] {opp['ticker']:20s} edge={opp.get('edge', opp.get('confidence', 0)):.2%} stake=${opp['stake']:.0f}")
    
    return result

if __name__ == "__main__":
    run_kalshi_scan()
