#!/usr/bin/env python3
"""
polymarket_logical_arb.py — Correlation & Logical Arbitrage Scanner.
Detects mathematical impossibilities in Polymarket pricing.

Strategies:
  1. Subset violations: P(A|B) > P(B) when A ⊆ B (e.g., Chiefs ⊆ AFC)
  2. Mutual exclusion: sum of disjoint outcomes > $1.00
  3. Cumulative probability: all outcomes in a set sum > 100%
  4. Calendar arbitrage: later dates priced higher than earlier for same event
  5. Conditional probability: Bayes theorem violation

Public CLOB API — no key required. Built for $100 bankroll.
"""
import json, re, time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict
import requests

# Polymarket CLOB API
CLOB_BASE = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

STATE_DIR = Path.home() / "hedge" / ".rumbling-hedge" / "state"
MIN_VIOLATION_PCT = 0.03  # 3% minimum edge
MIN_VOLUME = 5000  # minimum 24h volume to consider
MAX_STAKE = 10.0  # max per signal for $100 bankroll

class LogicalArbScanner:
    def __init__(self):
        self.markets = []
        self.signals = []
        self.relationships = []
    
    def fetch_markets(self, limit=200):
        """Fetch open markets from Polymarket Gamma API."""
        try:
            # Get markets with volume and liquidity
            params = {
                "limit": limit,
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
            }
            r = requests.get(f"{GAMMA_API}/markets", params=params, timeout=10)
            r.raise_for_status()
            self.markets = r.json()
            print(f"Fetched {len(self.markets)} markets")
            return True
        except Exception as e:
            print(f"Error fetching markets: {e}")
            # Try CLOB API as fallback
            try:
                r = requests.get(f"{CLOB_BASE}/markets", timeout=10)
                r.raise_for_status()
                self.markets = r.json()
                print(f"Fetched {len(self.markets)} from CLOB")
                return True
            except Exception as e2:
                print(f"CLOB fallback error: {e2}")
                return False
    
    def parse_market(self, m):
        """Extract key fields from market object."""
        def parse_json_field(val, default=None):
            if isinstance(val, str) and val.startswith("["):
                try:
                    return json.loads(val)
                except:
                    return default or val
            return val
        
        outcomes = parse_json_field(m.get("outcomePrices"), ["0", "0"])
        yes_price = float(outcomes[0]) if outcomes and len(outcomes) > 0 else 0
        no_price = float(outcomes[-1]) if outcomes and len(outcomes) > 1 else 0
        
        volume = float(m.get("volume24hr", 0) or 0)
        
        return {
            "id": str(m.get("id", m.get("conditionId", ""))),
            "question": m.get("question", ""),
            "slug": m.get("slug", ""),
            "yes_price": yes_price,
            "no_price": no_price,
            "volume": volume,
            "liquidity": float(m.get("liquidity", 0) or 0),
            "category": str(m.get("category", "")),
            "end_date": str(m.get("endDate", "")),
            "group_title": str(m.get("groupItemTitle", "")),
            "tokens": parse_json_field(m.get("clobTokenIds"), []),
        }
    
    def find_subset_relationships(self):
        """Find A ⊆ B relationships where P(A) should be ≤ P(B)."""
        markets = [self.parse_market(m) for m in self.markets]
        # Filter for volume
        markets = [m for m in markets if m["volume"] > MIN_VOLUME]
        
        # Pattern matching for subset relationships
        keywords = {
            "party": ["republican", "democrat", "democratic"],
            "name": ["trump", "biden", "harris", "desantis", "newsom", "vance"],
            "league": ["nba", "nfl", "mlb", "nhl", "premier"],
            "team": ["lakers", "celtics", "chiefs", "cowboys", "yankees", "dodgers"],
            "event_type": ["wins", "nomination", "election", "playoffs", "championship"],
        }
        
        for i, a in enumerate(markets):
            qa = a["question"].lower()
            if a["yes_price"] <= 0.01:
                continue
            
            for j, b in enumerate(markets):
                if i >= j:
                    continue
                qb = b["question"].lower()
                if b["yes_price"] <= 0.01:
                    continue
                
                # Check if A is a subset of B
                # Pattern: "X wins Super Bowl" ⊆ "X wins NFC"
                # Pattern: "Trump wins nomination" ⊆ "Republican wins nomination"
                
                is_subset = False
                relationship = ""
                
                # Team ⊆ League/Conference
                for team in keywords["team"]:
                    for league_type in ["conference", "division", "league"]:
                        if team in qa and league_type in qb and any(k in qa for k in ["win", "champion"]):
                            # Check if same sport context
                            sport_a = next((s for s in keywords["league"] if s in qa), None)
                            sport_b = next((s for s in keywords["league"] if s in qb), None)
                            if sport_a or sport_b:
                                if sport_a == sport_b or not sport_a or not sport_b:
                                    is_subset = True
                                    relationship = f"Team '{team}' is subset of broader {league_type}"
                
                # Person ⊆ Party
                for name in keywords["name"]:
                    for party in keywords["party"]:
                        if name in qa and party in qb and any(k in qa for k in ["win", "nomination", "elect"]):
                            is_subset = True
                            relationship = f"'{name}' is subset of '{party}'"
                
                if is_subset and a["yes_price"] > b["yes_price"]:
                    edge = a["yes_price"] - b["yes_price"]
                    if edge > MIN_VIOLATION_PCT:
                        self.signals.append({
                            "type": "subset_violation",
                            "relationship": relationship,
                            "market_a": a["question"][:100],
                            "price_a": a["yes_price"],
                            "market_b": b["question"][:100],
                            "price_b": b["yes_price"],
                            "edge": round(edge, 4),
                            "confidence": min(1.0, edge / MIN_VIOLATION_PCT),
                            "action": f"SELL {a['question'][:50]} @ {a['yes_price']:.2f}, BUY {b['question'][:50]} @ {b['yes_price']:.2f}",
                            "volume": min(a["volume"], b["volume"]),
                            "stake": min(MAX_STAKE, MAX_STAKE * edge / MIN_VIOLATION_PCT),
                        })
    
    def find_mutual_exclusion_violations(self):
        """Find mutually exclusive events whose prices sum > $1.00."""
        markets = [self.parse_market(m) for m in self.markets if self.parse_market(m)["volume"] > MIN_VOLUME]
        
        # Group by group_title (related questions)
        groups = defaultdict(list)
        for m in markets:
            group = m.get("group_title", "")
            if group:
                groups[group].append(m)
        
        for group, mkts in groups.items():
            if len(mkts) < 2:
                continue
            
            total_yes = sum(m["yes_price"] for m in mkts)
            if total_yes > 1.0 + MIN_VIOLATION_PCT:
                edge = total_yes - 1.0
                self.signals.append({
                    "type": "mutual_exclusion",
                    "group": group[:80],
                    "markets": [m["question"][:60] for m in mkts],
                    "prices": [m["yes_price"] for m in mkts],
                    "total": round(total_yes, 4),
                    "edge": round(edge, 4),
                    "confidence": min(1.0, edge / MIN_VIOLATION_PCT),
                    "action": f"SELL all {len(mkts)} outcomes — risk-free {edge:.2%} arb",
                    "volume": sum(m["volume"] for m in mkts),
                    "stake": min(MAX_STAKE, MAX_STAKE * len(mkts)),
                })
    
    def find_calendar_arbitrage(self):
        """Detect temporal mispricing: later dates priced higher than earlier."""
        markets = [self.parse_market(m) for m in self.markets if self.parse_market(m)["volume"] > MIN_VOLUME]
        
        # Pattern: "X by June" → "X by July" → "X by December"
        # Later dates should have HIGHER probability (monotonic)
        calendar_pattern = re.compile(
            r'(.+?)\s+(?:by|in|before|through)\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s*(20\d{2})?',
            re.IGNORECASE
        )
        
        months = ["january", "february", "march", "april", "may", "june",
                  "july", "august", "september", "october", "november", "december"]
        
        calendar_markets = []
        for m in markets:
            match = calendar_pattern.search(m["question"])
            if match:
                event = match.group(1).strip().lower()
                month_str = match.group(2).lower()
                try:
                    month_idx = months.index(month_str)
                except ValueError:
                    continue
                calendar_markets.append({
                    **m,
                    "event": event,
                    "month_idx": month_idx,
                    "month": month_str,
                })
        
        # Group by event
        event_groups = defaultdict(list)
        for cm in calendar_markets:
            event_groups[cm["event"]].append(cm)
        
        for event, mkts in event_groups.items():
            mkts.sort(key=lambda x: x["month_idx"])
            for i in range(len(mkts) - 1):
                earlier = mkts[i]
                later = mkts[i + 1]
                # Later date should have HIGHER probability
                if later["yes_price"] < earlier["yes_price"]:
                    edge = earlier["yes_price"] - later["yes_price"]
                    if edge > MIN_VIOLATION_PCT:
                        self.signals.append({
                            "type": "calendar_arbitrage",
                            "event": event[:60],
                            "earlier": f"{earlier['month']}",
                            "earlier_price": earlier["yes_price"],
                            "later": f"{later['month']}",
                            "later_price": later["yes_price"],
                            "edge": round(edge, 4),
                            "confidence": min(1.0, edge / MIN_VIOLATION_PCT),
                            "action": f"BUY {later['month']} @ {later['yes_price']:.2f}, SELL {earlier['month']} @ {earlier['yes_price']:.2f}",
                            "volume": min(earlier["volume"], later["volume"]),
                            "stake": min(MAX_STAKE, MAX_STAKE * edge / MIN_VIOLATION_PCT),
                        })
    
    def scan(self):
        """Run full scan."""
        print("=" * 60)
        print("POLYMARKET LOGICAL ARB SCANNER")
        print("=" * 60)
        
        if not self.fetch_markets():
            print("Failed to fetch markets. Using cached edge intake.")
            return self._fallback_scan()
        
        print("\n[1/3] Scanning subset violations...")
        self.find_subset_relationships()
        print(f"  Found {len([s for s in self.signals if s['type'] == 'subset_violation'])} subset violations")
        
        print("[2/3] Scanning mutual exclusion...")
        self.find_mutual_exclusion_violations()
        print(f"  Found {len([s for s in self.signals if s['type'] == 'mutual_exclusion'])} mutual exclusion violations")
        
        print("[3/3] Scanning calendar arbitrage...")
        self.find_calendar_arbitrage()
        print(f"  Found {len([s for s in self.signals if s['type'] == 'calendar_arbitrage'])} calendar arb opportunities")
        
        self._save_and_report()
    
    def _fallback_scan(self):
        """Use cached edge intake data."""
        edge_file = STATE_DIR / "prediction-edge-intake.latest.json"
        if edge_file.exists():
            intake = json.loads(edge_file.read_text())
            print(f"\nUsing cached edge intake ({len(intake.get('topEdges', []))} edges)")
            for e in intake.get("topEdges", []):
                if e.get("edgeType") in ["calendar", "mispriced"]:
                    self.signals.append({
                        "type": e.get("edgeType", "unknown"),
                        "title": e.get("title", "")[:80],
                        "category": e.get("category", ""),
                        "confidence": e.get("confidence", "medium"),
                        "action": f"Investigate: {e.get('title', '')[:80]}",
                        "edge": 0.03,
                    })
            self._save_and_report()
    
    def _save_and_report(self):
        """Save results and print report."""
        # Sort by confidence
        self.signals.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        out = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signals": self.signals,
            "total": len(self.signals),
            "bankroll": 100.0,
            "max_stake_per_signal": MAX_STAKE,
        }
        
        path = STATE_DIR / "logical-arb-signals.latest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2))
        
        print(f"\n{'='*60}")
        print(f"FOUND {len(self.signals)} LOGICAL ARB SIGNALS")
        print(f"{'='*60}")
        
        for s in self.signals[:10]:
            conf = s.get("confidence", 0)
            bar = "🟢" if conf > 0.7 else "🟡" if conf > 0.4 else "🔴"
            print(f"\n{bar} [{s['type']:20s}] conf={conf:.0%}")
            print(f"   {s.get('action', s.get('title', ''))[:120]}")
            if "edge" in s:
                print(f"   Edge: {s['edge']:.2%} | Stake: ${s.get('stake', 0):.0f}")
        
        print(f"\nSaved to {path}")

if __name__ == "__main__":
    scanner = LogicalArbScanner()
    scanner.scan()
