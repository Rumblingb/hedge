#!/usr/bin/env python3
"""
Becker PM Data Bridge — Wires prediction market data from HDD into the hedge pipeline.

Data location: /Volumes/Seagate Expansion Drive/rumbling-hedge-cold/prediction-market-analysis/
- kalshi/markets/: 10 parquet files (markets_0_10000 through markets_90000_100000)
- kalshi/trades/: trades_0_10000.parquet
- polymarket/markets/: 18+ parquet files (markets_20000_30000 through markets_370000_380000)
- polymarket/trades/: trades directory

Usage:
  python3 scripts/becker_bridge.py --search "US presidential"
  python3 scripts/becker_bridge.py --source polymarket --limit 10
  python3 scripts/becker_bridge.py --stats
"""

import argparse
import json
import os
import sys
from pathlib import Path

DATA_ROOT = Path("/Volumes/Seagate Expansion Drive/rumbling-hedge-cold/prediction-market-analysis")

try:
    import pandas as pd
    import pyarrow  # noqa: F401 — ensures parquet engine is available
except ImportError:
    print("ERROR: pandas and pyarrow required. Run: pip install pandas pyarrow")
    sys.exit(1)


def load_kalshi_markets(limit: int = None) -> pd.DataFrame:
    """Load Kalshi markets data from all parquet chunks."""
    pattern = str(DATA_ROOT / "kalshi/markets/markets_*.parquet")
    chunks = sorted(DATA_ROOT.glob("kalshi/markets/markets_*.parquet"))
    if not chunks:
        print(f"No Kalshi parquet files found at {DATA_ROOT / 'kalshi/markets/'}")
        return pd.DataFrame()

    dfs = [pd.read_parquet(c) for c in chunks]
    df = pd.concat(dfs, ignore_index=True)
    if limit:
        df = df.head(limit)
    return df


def load_polymarket_markets(limit: int = None) -> pd.DataFrame:
    """Load Polymarket markets data from all parquet chunks."""
    chunks = sorted(DATA_ROOT.glob("polymarket/markets/markets_*.parquet"))
    if not chunks:
        print(f"No Polymarket parquet files found at {DATA_ROOT / 'polymarket/markets/'}")
        return pd.DataFrame()

    dfs = [pd.read_parquet(c) for c in chunks]
    df = pd.concat(dfs, ignore_index=True)
    if limit:
        df = df.head(limit)
    return df


def search_markets(query: str, source: str = "all", limit: int = 20) -> list:
    """Search across all markets by keyword."""
    results = []

    if source in ("all", "kalshi"):
        kalshi = load_kalshi_markets()
        if not kalshi.empty:
            title_col = [c for c in kalshi.columns if 'title' in c.lower() or 'question' in c.lower() or 'name' in c.lower()]
            if title_col:
                mask = kalshi[title_col[0]].str.contains(query, case=False, na=False)
                matches = kalshi[mask].head(limit // 2)
                for _, row in matches.iterrows():
                    results.append({
                        "source": "kalshi",
                        "title": str(row.get(title_col[0], ""))[:200],
                        "id": str(row.get("ticker", row.get("id", ""))),
                        "status": str(row.get("status", "")),
                    })

    if source in ("all", "polymarket"):
        poly = load_polymarket_markets()
        if not poly.empty:
            title_col = [c for c in poly.columns if 'title' in c.lower() or 'question' in c.lower() or 'name' in c.lower()]
            if title_col:
                mask = poly[title_col[0]].str.contains(query, case=False, na=False)
                matches = poly[mask].head(limit // 2)
                for _, row in matches.iterrows():
                    results.append({
                        "source": "polymarket",
                        "title": str(row.get(title_col[0], ""))[:200],
                        "id": str(row.get("condition_id", row.get("id", ""))),
                        "status": str(row.get("status", "")),
                    })

    return results


def show_stats():
    """Show data statistics."""
    stats = {}

    kalshi = load_kalshi_markets()
    stats["kalshi_markets"] = len(kalshi)

    poly = load_polymarket_markets()
    stats["polymarket_markets"] = len(poly)

    # Check trades
    kalshi_trades = list(DATA_ROOT.glob("kalshi/trades/*.parquet"))
    poly_trades = list(DATA_ROOT.glob("polymarket/trades/*.parquet"))
    stats["kalshi_trade_files"] = len(kalshi_trades)
    stats["polymarket_trade_files"] = len(poly_trades)

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Becker PM Data Bridge")
    parser.add_argument("--search", type=str, help="Search markets by keyword")
    parser.add_argument("--source", type=str, default="all", choices=["all", "kalshi", "polymarket"])
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    parser.add_argument("--stats", action="store_true", help="Show data statistics")
    args = parser.parse_args()

    if args.stats:
        print(json.dumps(show_stats(), indent=2))
    elif args.search:
        results = search_markets(args.search, args.source, args.limit)
        print(json.dumps(results, indent=2))
        print(f"\nFound {len(results)} results")
    else:
        # Default: show stats
        print(json.dumps(show_stats(), indent=2))
