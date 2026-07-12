#!/usr/bin/env python3
"""Analyze all CSV files in /Users/brain/hedge/data/ - structure, date ranges, coverage."""

import os
import csv
import gzip
import sys
from pathlib import Path
from collections import defaultdict

BASE_DIRS = [
    "/Users/brain/hedge/data/free",
    "/Users/brain/hedge/data/research",
]

def get_file_size_mb(path):
    return os.path.getsize(path) / (1024 * 1024)

def analyze_csv(path):
    """Read header, count rows, get date range from first/last rows."""
    info = {
        'path': path,
        'filename': os.path.basename(path),
        'relpath': os.path.relpath(path, '/Users/brain/hedge/data'),
        'size_mb': round(get_file_size_mb(path), 2),
        'rows': 0,
        'columns': [],
        'col_count': 0,
        'date_min': None,
        'date_max': None,
        'date_col': None,
        'ticker_col': None,
        'tickers': set(),
        'error': None,
    }
    
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            # Read header
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                info['error'] = 'Empty file'
                return info
            
            info['columns'] = header
            info['col_count'] = len(header)
            
            # Find date column
            date_keywords = ['date', 'time', 'timestamp', 'datetime', 'day', 'close_time']
            for col in header:
                cl = col.lower().strip()
                if any(kw in cl for kw in date_keywords):
                    info['date_col'] = col
                    break
            
            # Find ticker/symbol column
            ticker_keywords = ['ticker', 'symbol', 'instrument', 'market', 'asset']
            for col in header:
                cl = col.lower().strip()
                if any(kw in cl for kw in ticker_keywords):
                    info['ticker_col'] = col
                    break
            
            # Try to read first few and last few rows
            first_rows = []
            last_rows = []
            row_count = 0
            
            for i, row in enumerate(reader):
                row_count += 1
                if i < 5:
                    first_rows.append(row)
                # Periodically sample last rows by keeping buffer
                if len(row) >= len(header):
                    # Simple approach: just store last 5
                    pass
            
            # Re-read to get last rows efficiently
            # Count rows first
            info['rows'] = row_count
            
            # Re-read for first/last row dates
            with open(path, 'r', encoding='utf-8', errors='replace') as f2:
                all_lines = f2.readlines()
            
            info['rows'] = len(all_lines) - 1  # minus header
            
            if info['rows'] > 0:
                # First data row
                first_row = all_lines[1].strip().split(',')
                
                # Try to get dates from first/last
                if info['date_col'] and info['date_col'] in header:
                    idx = header.index(info['date_col'])
                    # First row date
                    if idx < len(first_row):
                        info['date_min'] = first_row[idx].strip('" ')
                    
                    # Last non-empty data row
                    for line in reversed(all_lines[2:]):
                        parts = line.strip().split(',')
                        if idx < len(parts) and parts[idx].strip('" '):
                            info['date_max'] = parts[idx].strip('" ')
                            break
                
                # Get tickers if applicable
                if info['ticker_col'] and info['ticker_col'] in header:
                    tidx = header.index(info['ticker_col'])
                    tickers = set()
                    for line in all_lines[1:]:
                        parts = line.strip().split(',')
                        if tidx < len(parts):
                            t = parts[tidx].strip('" ')
                            if t:
                                tickers.add(t)
                    info['tickers'] = tickers
                
                # Try to infer ticker from filename
                fname = os.path.basename(path).upper()
                known_tickers = ['NQ', 'ES', 'GC', 'CL', 'SI', 'NG', '6E', 'ZN', 'RTY', 'YM',
                                'GF', 'BTC', 'ETH', 'SP', 'VIX', 'SPX', 'GOLD', 'ALL']
                for t in known_tickers:
                    if fname.startswith(t + '-') or fname.startswith(t + '_'):
                        info['tickers'].add(t)
                        break
            
    except Exception as e:
        info['error'] = str(e)
    
    return info

def main():
    all_files = []
    for base in BASE_DIRS:
        if os.path.exists(base):
            for root, dirs, files in os.walk(base):
                for f in files:
                    if f.endswith('.csv') or f.endswith('.csv.gz'):
                        all_files.append(os.path.join(root, f))
    
    all_files.sort()
    
    print(f"Total CSV files found: {len(all_files)}")
    print("=" * 120)
    
    results = []
    for path in all_files:
        info = analyze_csv(path)
        results.append(info)
        
        tickers_str = ', '.join(sorted(info['tickers'])) if info['tickers'] else '-'
        date_range = f"{info['date_min']} to {info['date_max']}" if info['date_min'] else 'N/A'
        err = f" ERROR: {info['error']}" if info['error'] else ""
        
        print(f"{info['filename']:55s} | {info['rows']:>8d} rows | {info['col_count']:2d} cols | {info['size_mb']:>8.1f} MB | {tickers_str:20s} | {date_range}{err}")
    
    print("\n" + "=" * 120)
    
    # Group by instrument
    print("\n\n=== INSTRUMENT SUMMARY (merge opportunities) ===\n")
    
    # Build instrument -> files mapping
    instrument_files = defaultdict(list)
    
    # Map file to instrument
    for info in results:
        if info['error']:
            continue
        fname = info['filename'].upper()
        
        instruments = set()
        
        # From tickers column
        if info['tickers']:
            for t in info['tickers']:
                instruments.add(t)
        
        # From filename pattern
        known = ['NQ', 'ES', 'GC', 'CL', 'SI', 'NG', '6E', 'ZN', 'RTY', 'YM', 'GF', 'VIX', 'SPX', 'BTC', 'ETH', 'GOLD']
        for t in known:
            if fname.startswith(t + '-') or fname.startswith(t + '_') or fname == t + '.CSV':
                instruments.add(t)
        
        if 'ALL' in fname or 'ALL' in instruments:
            # It's a multi-market file - list each market
            pass  # handled separately
        
        for inst in instruments:
            if inst == 'ALL':
                continue
            instrument_files[inst].append(info)
    
    # Print per-instrument summary
    for inst in sorted(instrument_files.keys()):
        files = instrument_files[inst]
        print(f"\n--- {inst} --- ({len(files)} files)")
        
        # Group by timeframe
        by_timeframe = defaultdict(list)
        for f in files:
            # Extract timeframe from filename
            fn = f['filename'].upper()
            tf = 'unknown'
            if '-1M-' in fn or '-1m-' in fn.lower() or fn.lower().endswith('-1m.csv'):
                tf = '1min'
            elif '-5M-' in fn or '-5m-' in fn.lower():
                tf = '5min'
            elif '-15M-' in fn or '-15m-' in fn.lower():
                tf = '15min'
            elif '-30M-' in fn or '-30m-' in fn.lower():
                tf = '30min'
            elif '-60M-' in fn or '-1H-' in fn or '-60m-' in fn.lower() or '-1h-' in fn.lower():
                tf = '60min'
            elif '-4H-' in fn or '-4h-' in fn.lower():
                tf = '4h'
            elif '-1D-' in fn or '-DAILY-' in fn or fn.lower().endswith('-1d.csv') or 'daily' in fn.lower():
                tf = 'daily'
            elif '-1W-' in fn or '-WEEKLY-' in fn or 'weekly' in fn.lower():
                tf = 'weekly'
            elif 'TICK' in fn:
                tf = 'tick'
            elif '-240M-' in fn or '-240m-' in fn.lower():
                tf = '240min'
            else:
                # Check filename more carefully
                if '1min' in fn.lower():
                    tf = '1min'
                elif '1d' in fn.lower() or 'daily' in fn.lower():
                    tf = 'daily'
                elif '1h' in fn.lower():
                    tf = '60min'
            
            date_r = f"{f['date_min']} -> {f['date_max']}" if f['date_min'] else 'no dates'
            by_timeframe[tf].append(f"  {f['filename']:50s} [{f['rows']:>8d} rows, {date_r}{' ERROR' if f['error'] else ''}]")
        
        for tf in ['tick', '1min', '5min', '15min', '30min', '60min', '240min', '4h', 'daily', 'weekly', 'unknown']:
            if tf in by_timeframe:
                print(f"  [{tf}]")
                for l in by_timeframe[tf]:
                    print(l)
    
    # Special multi-market files
    print("\n\n=== MULTI-MARKET / CROSS-ASSET FILES ===\n")
    for info in results:
        if info['error']:
            continue
        fn = info['filename'].upper()
        if 'ALL' in fn or '30YR' in fn or 'CROSS' in fn or '24TICKERS' in fn or '6MARKETS' in fn or '2MARKETS' in fn:
            print(f"{info['filename']:55s} | {info['rows']:>8d} rows | {info['col_count']:2d} cols | {info['size_mb']:>8.1f} MB")
            print(f"  Columns: {', '.join(info['columns'][:10])}{'...' if len(info['columns']) > 10 else ''}")
            print(f"  Date range: {info['date_min']} to {info['date_max']}")
            if info['tickers']:
                print(f"  Tickers: {', '.join(sorted(info['tickers']))}")
            print()
    
    # Special note files
    print("\n=== KEY LONG-HISTORY FILES ===\n")
    for info in results:
        if info['error']:
            continue
        rows_ok = info['rows'] > 10000 if info['rows'] else False
        hist_ok = 'daily' in info['filename'].lower() or '1975' in info['filename'] or '1983' in info['filename'] or '2000' in info['filename'] or '1995' in info['filename'] or '20yr' in info['filename']
        if rows_ok or hist_ok:
            print(f"{info['filename']:55s} | {info['rows']:>8d} rows | {info['col_count']:2d} cols | {info['size_mb']:>8.1f} MB")
            print(f"  Date range: {info['date_min']} to {info['date_max']}")
            print(f"  Columns: {', '.join(info['columns'][:15])}{'...' if len(info['columns']) > 15 else ''}")
            print()

if __name__ == '__main__':
    main()
