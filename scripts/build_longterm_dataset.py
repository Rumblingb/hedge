#!/usr/bin/env python3
"""
Build ALL-2MARKETS-NQ-ES-15m-longterm-normalized.csv 
Merges ES 1-min (2000-2019) + NQ 1-min (2022-2025) into a single normalized 15m file
for walkforward training on decades of data.
"""
import pandas as pd
import numpy as np
from pathlib import Path

DATA = Path("/Users/brain/hedge/data/free")

def load_and_resample(path: str, symbol: str, tf_minutes: int = 15) -> pd.DataFrame:
    """Load 1-min CSV, resample to tf_minutes bars."""
    print(f"\n  Loading {path}...")
    df = pd.read_csv(path, parse_dates=["ts"])
    print(f"    Raw: {len(df)} rows, {df.ts.min().date()} → {df.ts.max().date()}")
    
    # Handle different column sets
    cols = ["ts", "open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in cols):
        print(f"    WARNING: Missing columns. Have: {list(df.columns)}")
        # Try partial match
        available = [c for c in cols if c in df.columns]
        df = df[available]
    
    df["symbol"] = symbol
    df = df.set_index("ts")
    
    # Resample to tf_minutes
    rule = f"{tf_minutes}min"
    resampled = df.groupby("symbol").resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    
    resampled = resampled.reset_index()
    resampled = resampled[["ts", "symbol", "open", "high", "low", "close", "volume"]]
    print(f"    Resampled ({tf_minutes}m): {len(resampled)} rows")
    return resampled

def normalize_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize prices to percentage of first close per symbol."""
    df = df.copy()
    first_close = df.groupby("symbol")["close"].transform("first")
    for col in ["open", "high", "low", "close"]:
        df[col] = (df[col] / first_close) * 100
    return df

def main():
    print("=" * 60)
    print("BUILDING LONG-TERM MULTI-DECADE DATASET")
    print("=" * 60)
    
    # Load ES 1-min (2000-2019, 2.5M rows)
    es = load_and_resample(DATA / "ES-1m-20yr.csv", "ES", 15)
    
    # Load NQ 1-min (2022-2025, 1M rows)
    nq = load_and_resample(DATA / "NQ-1m-3yr.csv", "NQ", 15)
    
    # Merge
    merged = pd.concat([es, nq], ignore_index=True)
    merged = merged.sort_values(["ts", "symbol"]).reset_index(drop=True)
    
    print(f"\n  Merged: {len(merged)} rows")
    print(f"  Period: {merged.ts.min().date()} → {merged.ts.max().date()}")
    print(f"  Symbols: {merged.symbol.unique()}")
    
    # Save raw
    raw_path = DATA / "ALL-2MARKETS-NQ-ES-15m-longterm.csv"
    merged.to_csv(raw_path, index=False)
    print(f"\nRaw saved: {raw_path.name} ({merged.memory_usage(deep=True).sum() / 1e6:.1f}MB)")
    
    # Normalize
    normalized = normalize_prices(merged)
    
    # Also save in normalized format (for pipeline compatibility)
    norm_path = DATA / "ALL-2MARKETS-NQ-ES-15m-longterm-normalized.csv"
    normalized.to_csv(norm_path, index=False)
    print(f"Normalized saved: {norm_path.name}")
    
    # Print coverage stats
    for sym in ["ES", "NQ"]:
        sub = normalized[normalized.symbol == sym]
        years = (sub.ts.max() - sub.ts.min()).days / 365
        print(f"\n  {sym}: {len(sub)} bars, {sub.ts.min().date()} → {sub.ts.max().date()} ({years:.1f} years)")
    
    print("\n" + "=" * 60)
    print("NEXT: Run factory with:")
    print(f"  csvPath=data/free/ALL-2MARKETS-NQ-ES-15m-longterm-normalized.csv")
    print("=" * 60)

if __name__ == "__main__":
    main()
