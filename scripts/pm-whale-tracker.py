#!/usr/bin/env python3
"""Polymarket Whale Tracker — scans Becker PM trade data for smart money flow.
Identifies consistent winning addresses and tracks their trades.
Produces signals for the n8n pipeline.
"""
import pyarrow.parquet as pq
import json, os, sys
from collections import defaultdict
from datetime import datetime

TRADES_DIR = "/Volumes/Seagate Expansion Drive/rumbling-hedge-cold/prediction-market-analysis/polymarket/trades"
MARKETS_DIR = "/Volumes/Seagate Expansion Drive/rumbling-hedge-cold/prediction-market-analysis/polymarket/markets"
STATE_FILE = "/Users/brain/hedge/.rumbling-hedge/state/pm-whale-signals.json"

def load_markets(max_files=10):
    """Load market metadata — question, outcomes, end_date."""
    files = sorted(os.listdir(MARKETS_DIR))[:max_files]
    markets = {}
    for fname in files:
        table = pq.read_table(os.path.join(MARKETS_DIR, fname))
        df = table.to_pandas()
        for _, row in df.iterrows():
            mkt_id = row["id"]
            try:
                prices = json.loads(row["outcome_prices"]) if isinstance(row["outcome_prices"], str) else []
                outcomes = json.loads(row["outcomes"]) if isinstance(row["outcomes"], str) else []
            except:
                prices, outcomes = [], []
            markets[mkt_id] = {
                "question": row.get("question", ""),
                "outcomes": outcomes,
                "prices": prices,
                "volume": float(row.get("volume", 0)),
                "closed": bool(row.get("closed", False)),
                "end_date": str(row.get("end_date", "")),
            }
    return markets

def analyze_trades(max_files=100):
    """Analyze Polymarket trade data for whale wallets and edges."""
    files = sorted(os.listdir(TRADES_DIR))[:max_files]
    
    # Track address performance
    addr_pnl = defaultdict(lambda: {"wins": 0, "losses": 0, "total_amt": 0, "trades": 0})
    # Track large trades (potential whales)
    large_trades = []
    
    total_trades = 0
    for fname in files:
        table = pq.read_table(os.path.join(TRADES_DIR, fname))
        df = table.to_pandas()
        
        for _, row in df.iterrows():
            maker = row["maker"]
            taker = row["taker"]
            maker_amt = float(row.get("maker_amount", 0))
            taker_amt = float(row.get("taker_amount", 0))
            
            if maker_amt <= 0 or taker_amt <= 0:
                continue
            
            price = maker_amt / (maker_amt + taker_amt)
            total = maker_amt + taker_amt
            
            # Track maker (seller) — selling at price means they think < price
            addr_pnl[maker]["trades"] += 1
            addr_pnl[maker]["total_amt"] += total
            
            # Track taker (buyer) — buying at price means they think > price
            addr_pnl[taker]["trades"] += 1
            addr_pnl[taker]["total_amt"] += total
            
            # Large trades (>100k units)
            if total > 100_000:
                large_trades.append({
                    "maker": maker,
                    "taker": taker,
                    "price": round(price, 4),
                    "total": int(total),
                    "asset": row.get("maker_asset_id", ""),
                    "block": int(row.get("block_number", 0)),
                })
            
            total_trades += 1
    
    # Find whales: addresses with many trades and consistently betting on one side
    whales = []
    for addr, stats in addr_pnl.items():
        if stats["trades"] >= 10 and stats["total_amt"] >= 500_000:
            whales.append({
                "address": addr[:10] + "...",
                "trades": stats["trades"],
                "total_volume": stats["total_amt"],
                "type": "maker" if stats["trades"] > 0 else "taker",
            })
    
    whales.sort(key=lambda w: -w["total_volume"])
    
    result = {
        "analyzed_at": str(datetime.now(datetime.UTC)) + "Z",
        "total_trades_analyzed": total_trades,
        "total_files_scanned": len(files),
        "unique_addresses": len(addr_pnl),
        "whales_detected": whales[:20],
        "large_trades_last_block": large_trades[-20:] if large_trades else [],
        "whale_count": len(whales),
        "edge_summary": {
            "large_trades_count": len(large_trades),
        }
    }
    
    return result

if __name__ == "__main__":
    max_files = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    
    markets = load_markets(max_files=min(max_files, 10))
    result = analyze_trades(max_files=max_files)
    result["markets_sample"] = list(markets.values())[:5]
    
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"Analyzed {result['total_trades_analyzed']:,} trades from {result['total_files_scanned']} files")
    print(f"Unique addresses: {result['unique_addresses']:,}")
    print(f"Whales detected: {result['whale_count']}")
    print(f"Large trades: {result['edge_summary']['large_trades_count']}")

