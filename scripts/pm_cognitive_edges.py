#!/usr/bin/env python3
"""pm_cognitive_edges.py — Research-driven cognitive edge detector for Polymarket."""
import json, re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import requests

GAMMA = "https://gamma-api.polymarket.com"
STATE = Path.home() / "hedge" / ".rumbling-hedge" / "state"
MAX_STAKE = 10.0

def parse_prices(m):
    raw = m.get("outcomePrices", '["0","0"]')
    if isinstance(raw, str) and raw.startswith("["):
        try: return [float(x) for x in json.loads(raw)]
        except: return [0.0, 0.0]
    return [float(x) for x in raw] if isinstance(raw, list) else [0.0, 0.0]

class CognitiveScanner:
    def __init__(self):
        self.signals = []
    
    def fetch(self):
        try:
            r = requests.get(f"{GAMMA}/markets", params={"limit":200,"closed":"false","order":"volume24hr","ascending":"false"}, timeout=10)
            return r.json() if r.ok else []
        except: return []
    
    def scan(self):
        markets = self.fetch()
        print(f"Cognitive scanner: {len(markets)} markets")
        
        # Consensus complacency
        patterns = [("recession",0.10),("war",0.05),("default",0.02),("crash",0.08)]
        for m in markets[:150]:
            q = (m.get("question","")).lower()
            prices = parse_prices(m)
            vol = float(m.get("volume24hr",0) or 0)
            if vol < 5000: continue
            for pat, floor in patterns:
                if pat in q and prices[0] < floor:
                    self.signals.append({
                        "type":"consensus_complacency","question":m["question"][:100],
                        "price":prices[0],"fair":floor,"edge":round(floor-prices[0],4),
                        "action":f"BUY YES @ {prices[0]:.3f} — {pat} underpriced",
                        "stake":min(MAX_STAKE, MAX_STAKE*(floor-prices[0])*100),"confidence":0.6,"volume":vol
                    })
        
        # Calendar arbitrage
        cal = re.compile(r'(.+?)\s+(?:by|in|before)\s+(q[1-4]|january|february|march|april|may|june|july|august|september|october|november|december)', re.I)
        months = ["january","february","march","april","may","june","july","august","september","october","november","december"]
        qmap = {"q1":1,"q2":4,"q3":7,"q4":10}
        evs = defaultdict(list)
        for m in markets[:200]:
            prices = parse_prices(m)
            if prices[0] <= 0.01: continue
            match = cal.search(m.get("question",""))
            if not match: continue
            ev = match.group(1).strip().lower()
            ds = match.group(2).lower()
            mn = qmap.get(ds, months.index(ds)+1 if ds in months else 13)
            evs[ev].append((mn, ds, prices[0], m.get("question","")[:80]))
        
        for ev, items in evs.items():
            items.sort()
            for i in range(len(items)-1):
                if items[i+1][2] < items[i][2]:
                    e = items[i][2] - items[i+1][2]
                    if e > 0.03:
                        self.signals.append({
                            "type":"calendar","event":ev[:60],"edge":round(e,4),
                            "action":f"BUY {items[i+1][1]}@{items[i+1][2]:.3f} SELL {items[i][1]}@{items[i][2]:.3f}",
                            "stake":min(MAX_STAKE,MAX_STAKE*e*100),"confidence":0.7
                        })
        
        self.signals.sort(key=lambda x:x.get("confidence",0), reverse=True)
        out = {"ts":datetime.now(timezone.utc).isoformat(),"signals":self.signals,"total":len(self.signals)}
        (STATE/"cognitive-edges.latest.json").parent.mkdir(parents=True,exist_ok=True)
        (STATE/"cognitive-edges.latest.json").write_text(json.dumps(out,indent=2))
        
        print(f"Found {len(self.signals)} cognitive edges")
        for s in self.signals[:5]:
            print(f"  [{s['type'][:15]:15s}] {s.get('action','')[:100]}")
        print(f"\nSaved to cognitive-edges.latest.json")
        return out

if __name__ == "__main__":
    CognitiveScanner().scan()
