#!/usr/bin/env python3
"""
EDGAR Insider Trading Scanner — Government Filing Signals
==========================================================
Pulls live SEC Form 4 insider trading data for NQ top components
and generates aggregate insider sentiment signals.

Insider trading is one of the most researched alpha signals:
- Cluster buying → strong bullish signal
- CEO/CFO open market purchases → strongest signal
- Sustained insider selling → bearish (but less predictive than buying)
- Insider buying after 20%+ drawdown → high alpha

Data source: SEC EDGAR via MCP stock-scanner tools

Output: ~/hedge/.rumbling-hedge/state/insider-signal.latest.json
"""

import json, os, sys, subprocess
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Optional, Tuple

STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", os.path.expanduser("~/hedge/.rumbling-hedge/state")))
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "insider-signal.latest.json"
CACHE_FILE = STATE_DIR / "insider-cache.json"

# NQ top components to scan
NQ_TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", 
              "TSLA", "AVGO", "COST", "NFLX", "AMD", "ADBE", "PEP", "LIN"]

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")

def fetch_insider_trades(ticker: str) -> List[Dict]:
    """
    Fetch insider trades for a ticker using the EDGAR MCP tool.
    Returns list of parsed transactions.
    """
    try:
        # Use the MCP tool via a Python subprocess approach
        # Since we can't directly call MCP tools from Python scripts,
        # we read from the MCP response by calling it externally
        # For now, use the cached data pattern
        result = subprocess.run(
            ["python3", "-c", f"""
import json, sys
# This would use the MCP tool if accessible from scripts
# For now, signal that MCP data needs to be injected externally
print(json.dumps({{"ticker": "{ticker}", "status": "mcp_required"}}))
"""],
            capture_output=True, text=True, timeout=30
        )
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e), "ticker": ticker, "status": "failed"}

class InsiderScanner:
    """Scans SEC EDGAR for insider trading signals"""
    
    def __init__(self):
        self.cache = self._load_cache()
    
    def _load_cache(self) -> dict:
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE) as f:
                    return json.load(f)
            except:
                pass
        return {"last_scan": None, "trades": {}}
    
    def _save_cache(self):
        with open(CACHE_FILE, "w") as f:
            json.dump(self.cache, f, indent=2)
    
    def scan_ticker(self, ticker: str) -> Dict:
        """
        Scan a single ticker for insider trades using the MCP edgar_insider_trades tool.
        
        This function is called externally — the MCP tool is invoked by the
        cron runner and data is injected into the cache.
        
        Returns the analysis for this ticker.
        """
        cached = self.cache.get("trades", {}).get(ticker, {"transactions": []})
        transactions = cached.get("transactions", [])
        
        # Analyze transactions
        buys = []
        sells = []
        options = []
        cluster_buys = []
        
        for t in transactions:
            ttype = t.get("type", "").upper()
            shares = t.get("shares", 0)
            price = t.get("price", 0)
            reporter = t.get("reporter", "")
            
            entry = {
                "reporter": reporter,
                "shares": shares,
                "price": price,
                "date": t.get("date", ""),
                "value": float(shares) * float(price) if price > 0 else 0,
            }
            
            if ttype in ("BUY", "PURCHASE"):
                buys.append(entry)
            elif ttype in ("SELL",):
                sells.append(entry)
            elif ttype in ("OPTION_EXERCISE", "GRANT", "AWARD"):
                options.append(entry)
            # TAX_WITHHOLDING, GIFT, etc. are neutral
        
        # Calculate metrics
        total_buy_value = sum(b["value"] for b in buys)
        total_sell_value = sum(s["value"] for s in sells)
        buy_count = len(buys)
        sell_count = len(sells)
        
        # Insider buying is rare and significant
        buys_signal = None
        if buy_count > 0:
            # Cluster buying: multiple insiders buying
            unique_buyers = set(b["reporter"] for b in buys)
            if len(unique_buyers) >= 2 and total_buy_value > 50000:
                buys_signal = "cluster_buy"
            elif any(b["value"] > 100000 for b in buys):
                buys_signal = "significant_buy"
            else:
                buys_signal = "minor_buy"
        
        # Insider selling signal (less predictive but still useful)
        sells_signal = None
        if sell_count > 0:
            unique_sellers = set(s["reporter"] for s in sells)
            # CEO selling after recent stock price drop is red flag
            if any(s["value"] > 500000 for s in sells):
                sells_signal = "significant_sell"
            elif len(unique_sellers) >= 3:
                sells_signal = "cluster_sell"
            elif total_sell_value > 100000:
                sells_signal = "notable_sell"
            else:
                sells_signal = "routine_sell"
        
        # Net insider sentiment
        if total_buy_value > 0 or total_sell_value > 0:
            net_ratio = total_buy_value / max(total_sell_value, 1)
            if net_ratio > 3:
                sentiment = "very_bullish"
            elif net_ratio > 1:
                sentiment = "bullish"
            elif net_ratio > 0.3:
                sentiment = "neutral"
            elif net_ratio > 0.05:
                sentiment = "bearish"
            else:
                sentiment = "very_bearish"
        else:
            # No open-market trades (only option exercises/tax) = neutral
            sentiment = "neutral"
        
        return {
            "ticker": ticker,
            "buys": buys,
            "sells": sells,
            "options": options,
            "metrics": {
                "buy_count": buy_count,
                "sell_count": sell_count,
                "total_buy_value": round(total_buy_value, 2),
                "total_sell_value": round(total_sell_value, 2),
                "buy_sell_ratio": round(net_ratio, 2) if (total_buy_value > 0 or total_sell_value > 0) else None,
                "unique_buyers": len(set(b["reporter"] for b in buys)),
                "unique_sellers": len(set(s["reporter"] for s in sells)),
            },
            "signals": {
                "buy_signal": buys_signal,
                "sell_signal": sells_signal,
                "sentiment": sentiment,
            },
        }
    
    def inject_mcp_data(self, ticker: str, transactions: List[Dict]):
        """Inject MCP tool data into cache for analysis"""
        if "trades" not in self.cache:
            self.cache["trades"] = {}
        self.cache["trades"][ticker] = {
            "transactions": transactions,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_cache()
    
    def compute_nq_bias(self, ticker_results: Dict[str, Dict]) -> Tuple[str, float, str]:
        """
        Compute aggregate NQ bias from all ticker insider signals.
        Returns (bias, confidence, rationale)
        """
        sentiment_scores = {
            "very_bullish": 2,
            "bullish": 1,
            "neutral": 0,
            "bearish": -1,
            "very_bearish": -2,
        }
        
        total_score = 0
        active_tickers = 0
        details = []
        
        for ticker, result in ticker_results.items():
            sentiment = result.get("signals", {}).get("sentiment", "neutral")
            score = sentiment_scores.get(sentiment, 0)
            
            metrics = result.get("metrics", {})
            buys = metrics.get("buy_count", 0)
            sells = metrics.get("sell_count", 0)
            total_value = metrics.get("total_sell_value", 0)
            
            if buys > 0 or sells > 0:
                active_tickers += 1
                total_score += score
                
                detail = f"{ticker}: {sentiment} ({buys}B/{sells}S, ${total_value:,.0f})"
                details.append(detail)
        
        if active_tickers == 0:
            return "neutral", 0.0, "No insider activity detected"
        
        avg_score = total_score / active_tickers
        
        if avg_score > 1:
            bias = "bullish"
            confidence = min(0.6 + (avg_score - 1) * 0.1, 0.85)
        elif avg_score > 0:
            bias = "mildly_bullish"
            confidence = 0.4 + avg_score * 0.1
        elif avg_score > -0.5:
            bias = "neutral"
            confidence = 0.2
        elif avg_score > -1:
            bias = "mildly_bearish"
            confidence = 0.3 + abs(avg_score) * 0.1
        else:
            bias = "bearish"
            confidence = min(0.5 + (abs(avg_score) - 1) * 0.15, 0.80)
        
        rationale = "; ".join(details)
        return bias, round(confidence, 3), rationale
    
    def run(self) -> Dict:
        """Run full insider scan analysis using cached MCP data"""
        log("EDGAR Insider Trading Scanner — Running")
        
        results = {}
        for ticker in NQ_TICKERS:
            if ticker in self.cache.get("trades", {}):
                result = self.scan_ticker(ticker)
                results[ticker] = result
                sentiment = result["signals"]["sentiment"]
                metrics = result["metrics"]
                log(f"  {ticker}: {sentiment} ({metrics['buy_count']}B/{metrics['sell_count']}S)")
        
        if not results:
            log("  ⚠️ No cached MCP data. Inject data via inject_mcp_data()")
            bias = "neutral"
            confidence = 0.0
            output = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "strategy": "SEC EDGAR Insider Trading Signals",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
                "promoted_for_execution": False,
                "tradable_signal": False,
                "execution_role": "research_only",
                "evidence_level": "sec-form4-research-only",
                "status": "no_data",
                "message": "No insider data in cache. Run inject_mcp_data() with MCP tool output first.",
                "nq_bias": "neutral",
                "confidence": 0.0,
                "tickers": 0,
            }
        else:
            bias, confidence, rationale = self.compute_nq_bias(results)
            
            output = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "strategy": "SEC EDGAR Insider Trading Signals",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
                "promoted_for_execution": False,
                "tradable_signal": False,
                "execution_role": "research_only",
                "evidence_level": "sec-form4-research-only",
                "status": "active",
                "nq_bias": bias,
                "confidence": confidence,
                "rationale": rationale,
                "tickers_scanned": len(results),
                "ticker_results": results,
                "action": "HOLD" if abs(confidence) < 0.2 else ("LONG_BIAS" if bias in ("bullish", "mildly_bullish") else "SHORT_BIAS"),
                "source": "edgar-sec-form4-insider-trades",
            }
        
        with open(STATE_FILE, "w") as f:
            json.dump(output, f, indent=2)
        
        log(f"✅ Written to {STATE_FILE}")
        log(f"  → NQ bias: {bias}")
        log(f"  → Confidence: {confidence}")
        log(f"  → Tickers: {len(results)}")
        
        return output

def inject_and_run_from_cli():
    """
    CLI entry point: accepts JSON from MCP edgar_insider_trades output
    and pipes it into the scanner.
    
    Usage: 
      python3 insider_scanner.py --inject AAPL '[{"reporter":"...",...}]'
      python3 insider_scanner.py --run
    """
    scanner = InsiderScanner()
    
    if len(sys.argv) >= 4 and sys.argv[1] == "--inject":
        ticker = sys.argv[2]
        try:
            data = json.loads(sys.argv[3])
            if isinstance(data, list):
                scanner.inject_mcp_data(ticker, data)
            elif isinstance(data, dict) and "parsedTransactions" in data:
                scanner.inject_mcp_data(ticker, data["parsedTransactions"])
            else:
                print(f"⚠️ Unknown data format for {ticker}")
        except json.JSONDecodeError as e:
            print(f"⚠️ Invalid JSON: {e}")
    
    else:
        scanner.run()

if __name__ == "__main__":
    inject_and_run_from_cli()
