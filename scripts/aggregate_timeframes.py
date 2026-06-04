#!/usr/bin/env python3
"""Aggregate multi-timeframe data for all 6 markets."""
import pandas as pd
import numpy as np
from pathlib import Path

DATA = Path("/Users/brain/hedge/data/free")
OUT = Path("/Users/brain/hedge/data/free")
SYMBOLS = ["NQ", "ES", "GC", "CL", "6E", "ZN"]

def load_1m():
    """Load best available 1m data for each symbol and merge."""
    pieces = []
    for sym in SYMBOLS:
        # Try normalized 21d first, then 30d raw, then 5d
        candidates = [
            DATA / f"{sym}-1m-21d-normalized.csv",
            DATA / f"{sym}-1m-30d.csv",
            DATA / f"{sym}-1m-5d.csv",
        ]
        for path in candidates:
            if path.exists():
                df = pd.read_csv(path, parse_dates=["ts"])
                df["symbol"] = sym
                pieces.append(df)
                print(f"  {sym}: {path.name} ({len(df)} rows, {df.ts.min().date()} → {df.ts.max().date()})")
                break
        else:
            print(f"  {sym}: NO DATA")
    
    if not pieces:
        print("No 1m data found!")
        return None
    
    merged = pd.concat(pieces, ignore_index=True)
    merged = merged.sort_values(["ts", "symbol"]).reset_index(drop=True)
    out_path = OUT / "ALL-6MARKETS-1m-aggregated.csv"
    merged.to_csv(out_path, index=False)
    print(f"\n✅ Created {out_path.name}: {len(merged)} rows, {merged.ts.min().date()} → {merged.ts.max().date()}")
    print(f"   Symbols: {merged.symbol.nunique()}, Unique timestamps: {merged.ts.nunique()}")
    return merged

def load_daily():
    """Create daily data from existing 15m or 1m data."""
    # Check existing daily files first
    daily_sources = [
        DATA / "ALL-2MARKETS-NQ-ES-1d-5y.csv",
        DATA / "ALL-2MARKETS-NQ-ES-1d-1y-normalized.csv",
    ]
    
    # Load 15m data and resample to daily
    fifteen_m = DATA / "ALL-6MARKETS-15m-60d-normalized.csv"
    if fifteen_m.exists():
        df = pd.read_csv(fifteen_m, parse_dates=["ts"])
        daily = df.resample("D", on="ts").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "symbol": "first",
        }).dropna().reset_index()
        # Re-sort by symbol then ts
        daily = daily.sort_values(["symbol", "ts"]).reset_index(drop=True)
        out_path = OUT / "ALL-6MARKETS-1d-60d.csv"
        daily.to_csv(out_path, index=False)
        print(f"\n✅ Created {out_path.name} (from 15m resample): {len(daily)} rows")
        print(f"   {daily.ts.min().date()} → {daily.ts.max().date()}")
    
    # Also check if we can load existing NQ+ES daily and extend
    for src in daily_sources:
        if src.exists():
            df = pd.read_csv(src, parse_dates=["ts"])
            print(f"  Existing daily: {src.name} ({len(df)} rows, symbols: {df.symbol.unique()})")

if __name__ == "__main__":
    print("=== 1-minute aggregation ===")
    load_1m()
    print("\n=== Daily aggregation ===")
    load_daily()
