#!/usr/bin/env python3
"""Comprehensive data quality audit for all trading datasets."""
import pandas as pd
import numpy as np
from pathlib import Path

DATA = Path("/Users/brain/hedge/data/free")
ISSUES = []

def check(name, df, required_cols=None):
    """Run all quality checks on a DataFrame."""
    issues = []
    print(f"\n{'='*60}")
    print(f"📊 {name}")
    print(f"{'='*60}")
    
    if df is None or len(df) == 0:
        issues.append(("CRITICAL", "Empty DataFrame"))
        return issues
    
    print(f"  Rows: {len(df):,}")
    print(f"  Columns: {list(df.columns)}")
    
    # 1. Missing values
    nulls = df.isnull().sum()
    null_cols = nulls[nulls > 0]
    if len(null_cols) > 0:
        for col, count in null_cols.items():
            pct = count / len(df) * 100
            sev = "CRITICAL" if pct > 10 else ("WARNING" if pct > 1 else "INFO")
            msg = f"{col}: {count} nulls ({pct:.1f}%)"
            issues.append((sev, msg))
            print(f"    [{sev}] {msg}")
    else:
        print(f"  ✅ No missing values")
    
    # 2. Check for timestamp column
    ts_col = None
    for c in ['ts', 'datetime', 'date', 'TimeStamp', 'Date']:
        if c in df.columns:
            ts_col = c
            break
    
    if ts_col:
        # Parse timestamps (handle mixed formats)
        try:
            dates = pd.to_datetime(df[ts_col], errors='coerce')
            bad_dates = dates.isnull().sum()
            if bad_dates > 0:
                issues.append(("CRITICAL", f"{bad_dates} unparseable timestamps"))
                print(f"    [CRITICAL] {bad_dates} unparseable timestamps")
            else:
                print(f"  ✅ Timestamps parseable ({df[ts_col].dtype})")
                print(f"  📅 Range: {dates.min()} → {dates.max()}")
                print(f"  ⏱ Span: {(dates.max() - dates.min()).days} days")
                
                # Check for duplicates
                dups = dates.duplicated().sum()
                if dups > 0:
                    # Check if duplicate timestamps are expected (e.g., multi-symbol)
                    if 'symbol' in df.columns:
                        dup_after_symbol = df.duplicated(subset=[ts_col, 'symbol']).sum()
                        if dup_after_symbol > 0:
                            issues.append(("WARNING", f"{dup_after_symbol} duplicate (ts, symbol) pairs"))
                            print(f"    [WARNING] {dup_after_symbol} duplicate (ts, symbol) pairs")
                        else:
                            print(f"  ✅ Multi-symbol duplicates OK")
                    else:
                        issues.append(("WARNING", f"{dups} duplicate timestamps"))
                        print(f"    [WARNING] {dups} duplicate timestamps")
                else:
                    print(f"  ✅ No duplicate timestamps")
                
                # Check for gaps
                if 'symbol' in df.columns:
                    for sym in df['symbol'].unique():
                        sub = df[df['symbol'] == sym].sort_values(ts_col)
                        sub_dates = pd.to_datetime(sub[ts_col])
                        gaps = sub_dates.diff().dt.total_seconds()
                        # For intraday data, expect gaps < 2x bar interval
                        if len(sub) > 1:
                            median_gap = gaps.median()
                            large_gaps = (gaps > median_gap * 3).sum()
                            if large_gaps > len(sub) * 0.05:
                                issues.append(("WARNING", f"{sym}: {large_gaps} large gaps ({large_gaps/len(sub)*100:.1f}%)"))
                                print(f"    [WARNING] {sym}: {large_gaps} large gaps (gap > 3× median)")
                else:
                    dates_sorted = dates.sort_values()
                    gaps = dates_sorted.diff().dt.total_seconds()
                    if len(dates_sorted) > 1:
                        median_gap = gaps.median()
                        large_gaps = (gaps > median_gap * 3).sum()
                        if large_gaps > 0:
                            issues.append(("INFO", f"{large_gaps} gaps > 3× median interval"))
        except Exception as e:
            issues.append(("WARNING", f"Timestamp parsing issue: {e}"))
    else:
        issues.append(("WARNING", "No timestamp column found"))
        print(f"    [WARNING] No timestamp column found")
    
    # 3. Price column checks
    for price_col in ['open', 'high', 'low', 'close', 'Open', 'Close', 'High', 'Low']:
        if price_col in df.columns:
            vals = df[price_col]
            if vals.isnull().any():
                issues.append(("CRITICAL", f"{price_col}: has nulls"))
            if (vals <= 0).any():
                issues.append(("CRITICAL", f"{price_col}: has zero/negative values ({(vals<=0).sum()} rows)"))
                print(f"    [CRITICAL] {price_col}: {(vals<=0).sum()} zero/negative values")
            # Check for outliers (>5 std from mean)
            mean, std = vals.mean(), vals.std()
            outliers = ((vals - mean).abs() > 5 * std).sum()
            if outliers > 0:
                issues.append(("INFO", f"{price_col}: {outliers} outliers (>5σ)"))
    
    # 4. Volume checks
    for vol_col in ['volume', 'Volume']:
        if vol_col in df.columns:
            zero_vol = (df[vol_col] == 0).sum()
            neg_vol = (df[vol_col] < 0).sum()
            if zero_vol > len(df) * 0.5:
                issues.append(("WARNING", f"{zero_vol}/{len(df)} rows have volume=0 ({zero_vol/len(df)*100:.0f}%)"))
                print(f"    [WARNING] Volume: {zero_vol}/{len(df)} rows have 0 volume")
            if neg_vol > 0:
                issues.append(("CRITICAL", f"{neg_vol} rows with negative volume"))
                print(f"    [CRITICAL] {neg_vol} rows with negative volume")
    
    # 5. Data integrity
    if all(c in df.columns for c in ['high', 'low', 'open', 'close']):
        high_lt_low = (df['high'] < df['low']).sum()
        open_outside = ((df['open'] < df['low']) | (df['open'] > df['high'])).sum()
        close_outside = ((df['close'] < df['low']) | (df['close'] > df['high'])).sum()
        if high_lt_low > 0:
            issues.append(("WARNING", f"{high_lt_low} rows where high < low"))
            print(f"    [WARNING] {high_lt_low} high<low violations")
        if open_outside > 0:
            issues.append(("WARNING", f"{open_outside} rows where open outside high-low range"))
        if close_outside > 0:
            issues.append(("WARNING", f"{close_outside} rows where close outside high-low range"))
        else:
            print(f"  ✅ OHLC integrity: all high≥low, open/close within range")
    
    # 6. Symbol coverage
    if 'symbol' in df.columns:
        syms = df['symbol'].unique()
        print(f"  🏷 Symbols: {sorted(syms)}")
        for sym in sorted(syms):
            sub = df[df['symbol'] == sym]
            print(f"     {sym}: {len(sub):,} rows")
            if ts_col:
                sym_dates = pd.to_datetime(sub[ts_col])
                print(f"       {sym_dates.min().date()} → {sym_dates.max().date()}")
    
    issues.append(("INFO", f"Total rows: {len(df):,}"))
    return issues

def load_csv(path, name, **kwargs):
    try:
        if not path.exists():
            return None, [(f"WARNING", f"File not found: {path}")]
        try:
            df = pd.read_csv(path, **kwargs)
        except:
            # Try with different encoding
            df = pd.read_csv(path, encoding='latin1', **kwargs)
        issues = check(name, df)
        return df, issues
    except Exception as e:
        return None, [(f"CRITICAL", f"Cannot load {path}: {e}")]

def main():
    all_issues = {}
    
    # === 1. CORE TRADING DATASETS ===
    print("=" * 60)
    print("PHASE 1: CORE TRADING DATASETS")
    print("=" * 60)
    
    datasets = [
        (DATA / "ALL-6MARKETS-15m-60d-normalized.csv", "6-Market 15m (current training)"),
        (DATA / "ALL-2MARKETS-NQ-ES-15m-longterm-normalized.csv", "NQ+ES 15m Long-term (25yr)"),
        (DATA / "ALL-6MARKETS-1m-aggregated.csv", "6-Market 1m Aggregated"),
        (DATA / "ALL-6MARKETS-1d-60d.csv", "6-Market Daily (from 15m)"),
        (DATA / "ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv", "NQ+ES 1m (OOS used by factory)"),
        (DATA / "ES-1m-2020-2024.csv", "ES 1m 2020-2024 (NEW - HuggingFace)"),
    ]
    
    for path, name in datasets:
        df, issues = load_csv(path, name)
        if df is not None or issues:
            all_issues[name] = issues
    
    # === 2. LONG-HISTORY DATASETS ===
    print("\n" + "=" * 60)
    print("PHASE 2: LONG-HISTORY DATASETS")
    print("=" * 60)
    
    long_sets = [
        (DATA / "ES-1m-20yr.csv", "ES 1min 2000-2019"),
        (DATA / "NQ-1m-3yr.csv", "NQ 1min 2022-2025"),
        (DATA / "GC-daily-1975-2025.csv", "GC Daily 1975-2025"),
        (DATA / "CL-daily-1983-2025.csv", "CL Daily 1983-2025"),
        (DATA / "futures-daily-with-features-24tickers.csv", "Futures Daily 24-ticker (Kaggle)"),
        (DATA / "30yr-cross-asset-market-data.csv", "30yr Cross-Asset"),
        (DATA / "VIX-daily-2004-2020.csv", "VIX Daily 2004-2020"),
        (DATA / "SPX-options-derived-2017-2025.csv", "SPX Options Flow"),
    ]
    
    for path, name in long_sets:
        df, issues = load_csv(path, name)
        if df is not None or issues:
            all_issues[name] = issues
    
    # === 3. SUMMARY ===
    print("\n" + "=" * 60)
    print("DATA QUALITY SUMMARY")
    print("=" * 60)
    
    criticals = []
    warnings = []
    infos = []
    
    for name, issues in all_issues.items():
        for severity, msg in issues:
            entry = f"  [{severity}] {name}: {msg}"
            if severity == "CRITICAL":
                criticals.append(entry)
            elif severity == "WARNING":
                warnings.append(entry)
            else:
                infos.append(entry)
    
    if criticals:
        print("\n🔴 CRITICAL ISSUES:")
        for c in criticals:
            print(c)
    
    if warnings:
        print("\n🟡 WARNINGS:")
        for w in warnings:
            print(w)
    
    if infos:
        print("\nℹ️ INFO:")
        for i in infos:
            print(i)
    
    print(f"\n{'='*60}")
    print(f"Total datasets checked: {len(all_issues)}")
    print(f"Critical: {len(criticals)} | Warnings: {len(warnings)} | Info: {len(infos)}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
