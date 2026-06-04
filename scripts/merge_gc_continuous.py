#!/usr/bin/env python3
"""Merge GC/GOLD daily datasets into a single continuous series from 1975 to 2026.

Strategy:
1. Base: GC-daily-1975-2025.csv (TradingView, OHLCV only, 1975-2025 Oct)
2. Extend: GOLD-daily-2000-2026.csv (Yahoo, has MA/Volatility indicators, 2000-2026 Feb)
3. Overlap 2000-2025: cross-validate prices, use GC for OHLCV, enrich with GOLD's indicators
4. Output: single clean CSV with OHLCV + MA_7, MA_30, MA_90, MA_365, Volatility_30d
"""

import csv
from datetime import datetime

BASE = "/Users/brain/hedge/data/free/GC-daily-1975-2025.csv"
EXTEND = "/Users/brain/hedge/data/free/GOLD-daily-2000-2026.csv"
OUT = "/Users/brain/hedge/data/free/GC-daily-continuous-1975-2026.csv"

# --- Load Base (GC-daily) ---
print("Loading base GC daily...")
base_rows = {}
with open(BASE) as f:
    reader = csv.DictReader(f)
    for row in reader:
        # datetime format: "1975-01-01 23:00:00" (EOD timestamp)
        ts = row['datetime'].strip()
        # Parse to date only
        dt = ts[:10]
        base_rows[dt] = {
            'date': dt,
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume'],
            'source': 'GC-daily'
        }
print(f"  Loaded {len(base_rows)} days from 1975")

# --- Load Extension (GOLD-daily) ---
print("Loading extension GOLD daily...")
ext_rows = {}
with open(EXTEND) as f:
    reader = csv.DictReader(f)
    for row in reader:
        dt = row['Date'].strip()
        if dt:
            ext_rows[dt] = {
                'date': dt,
                'open': row['Open'],
                'high': row['High'],
                'low': row['Low'],
                'close': row['Close'],
                'volume': row['Volume'],
                'ma_7': row.get('MA_7', ''),
                'ma_30': row.get('MA_30', ''),
                'ma_90': row.get('MA_90', ''),
                'ma_365': row.get('MA_365', ''),
                'volatility_30d': row.get('Volatility_30d', ''),
                'source': 'GOLD-daily'
            }
print(f"  Loaded {len(ext_rows)} days from 2000")

# --- Cross-validate overlap ---
print("Cross-validating overlap (Oct 2000 - Oct 2025)...")
overlap_dates = sorted(set(base_rows.keys()) & set(ext_rows.keys()))
print(f"  {len(overlap_dates)} overlapping trading days")

# Check price alignment on a sample
price_diffs = []
for dt in overlap_dates[:100]:
    b = base_rows[dt]
    e = ext_rows[dt]
    if b['close'] and e['close']:
        cb = float(b['close'])
        ce = float(e['close'])
        if cb > 0:
            pct_diff = abs(cb - ce) / cb * 100
            price_diffs.append(pct_diff)

if price_diffs:
    avg_diff = sum(price_diffs) / len(price_diffs)
    max_diff = max(price_diffs)
    print(f"  Avg price diff in overlap: {avg_diff:.2f}%")
    print(f"  Max price diff in overlap: {max_diff:.2f}%")

    if avg_diff < 5.0:
        print("  ✅ Prices aligned within tolerance (<5%)")
    else:
        print("  ⚠️ Large price differences — using base GC as primary OHLCV source")

# --- Build continuous series ---
print("\nBuilding continuous series...")
output_rows = []
output_cols = ['date', 'open', 'high', 'low', 'close', 'volume', 
               'ma_7', 'ma_30', 'ma_90', 'ma_365', 'volatility_30d', 'source']

# 1. Pre-2000: base only
for dt in sorted(d for d in base_rows if d < '2000-08-30'):
    r = base_rows[dt]
    output_rows.append({
        'date': r['date'],
        'open': r['open'], 'high': r['high'], 'low': r['low'], 'close': r['close'],
        'volume': r['volume'],
        'ma_7': '', 'ma_30': '', 'ma_90': '', 'ma_365': '', 'volatility_30d': '',
        'source': 'GC-daily (TradingView)'
    })

# 2. Overlap 2000-2025: use base GC for OHLCV + enrich with GOLD indicators
all_dates_2000_2025 = sorted(set(
    [d for d in base_rows if d >= '2000-08-30'] + 
    [d for d in ext_rows if d <= '2025-10-14']
))

# Track what's in GOLD but NOT in GC (fill from GOLD)
extending_dates = 0
for dt in all_dates_2000_2025:
    b = base_rows.get(dt)
    e = ext_rows.get(dt)
    
    if b and e:
        # Overlap — use GC OHLCV, enrich with GOLD indicators
        output_rows.append({
            'date': dt,
            'open': b['open'], 'high': b['high'], 'low': b['low'], 'close': b['close'],
            'volume': b['volume'],
            'ma_7': e['ma_7'], 'ma_30': e['ma_30'], 'ma_90': e['ma_90'], 
            'ma_365': e['ma_365'], 'volatility_30d': e['volatility_30d'],
            'source': 'merged (GC+TradingView + GOLD+Yahoo indicators)'
        })
    elif e:
        # GOLD-only days (extends beyond GC-daily)
        extending_dates += 1
        output_rows.append({
            'date': dt,
            'open': e['open'], 'high': e['high'], 'low': e['low'], 'close': e['close'],
            'volume': e['volume'],
            'ma_7': e['ma_7'], 'ma_30': e['ma_30'], 'ma_90': e['ma_90'],
            'ma_365': e['ma_365'], 'volatility_30d': e['volatility_30d'],
            'source': 'GOLD-daily (Yahoo Finance)'
        })
    elif b:
        # GC-only day (in overlap range but no GOLD — rare)
        output_rows.append({
            'date': dt,
            'open': b['open'], 'high': b['high'], 'low': b['low'], 'close': b['close'],
            'volume': b['volume'],
            'ma_7': '', 'ma_30': '', 'ma_90': '', 'ma_365': '', 'volatility_30d': '',
            'source': 'GC-daily (TradingView)'
        })

# 3. Post-Oct 2025: GOLD only
for dt in sorted(d for d in ext_rows if d > '2025-10-14'):
    e = ext_rows[dt]
    extending_dates += 1
    output_rows.append({
        'date': dt,
        'open': e['open'], 'high': e['high'], 'low': e['low'], 'close': e['close'],
        'volume': e['volume'],
        'ma_7': e['ma_7'], 'ma_30': e['ma_30'], 'ma_90': e['ma_90'],
        'ma_365': e['ma_365'], 'volatility_30d': e['volatility_30d'],
        'source': 'GOLD-daily (Yahoo Finance)'
    })

print(f"  Total rows: {len(output_rows)}")
print(f"  Extending dates (GOLD only): {extending_dates}")

# --- Write output ---
print("Writing continuous file...")
with open(OUT, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=output_cols)
    writer.writeheader()
    writer.writerows(output_rows)

import os
size_mb = os.path.getsize(OUT) / 1024 / 1024
print(f"\n✅ Written: {OUT}")
print(f"   Size: {size_mb:.1f} MB")
print(f"   Range: {output_rows[0]['date']} → {output_rows[-1]['date']}")
print(f"   Rows: {len(output_rows)}")

# Verify no gaps > 10 days
dates = [r['date'] for r in output_rows]
from datetime import datetime, timedelta
large_gaps = 0
for i in range(1, len(dates)):
    d1 = datetime.strptime(dates[i-1], '%Y-%m-%d')
    d2 = datetime.strptime(dates[i], '%Y-%m-%d')
    gap = (d2 - d1).days
    if gap > 10:
        large_gaps += 1
        if large_gaps <= 3:
            print(f"  ⚠️ Gap: {dates[i-1]} → {dates[i]} ({gap} days)")
print(f"  Gaps > 10 days: {large_gaps}")
