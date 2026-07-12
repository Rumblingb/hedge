#!/usr/bin/env python3
"""refresh_data.py — Pull fresh market data from Yahoo Finance (free, no API key).

Replaces broken Databento/Polygon pipeline with free Yahoo Finance data.
Runs: python3 refresh_data.py

Outputs to /Users/brain/hedge/data/free/:
  NQ-1d-5y-fresh.csv           — 5 years daily NQ
  ES-1d-5y-fresh.csv           — 5 years daily ES  
  NQ-15m-60d-fresh.csv         — 60 days 15m NQ
  ES-15m-60d-fresh.csv         — 60 days 15m ES
  ALL-2MARKETS-NQ-ES-1d-5y-fresh.csv  — Combined daily
  ALL-2MARKETS-NQ-ES-15m-60d-fresh.csv — Combined 15m
"""

import urllib.request, json, csv, os, sys
from datetime import datetime, timedelta

OUT_DIR = "/Users/brain/hedge/data/free"
os.makedirs(OUT_DIR, exist_ok=True)

def get_yahoo(ticker, days, interval, label):
    """Pull data from Yahoo Finance chart API (free, no auth)."""
    end = int(datetime.now().timestamp())
    start = int((datetime.now() - timedelta(days=days)).timestamp())
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start}&period2={end}&interval={interval}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quotes = result['indicators']['quote'][0]
        rows = []
        for i in range(len(timestamps)):
            ts = datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            o = quotes['open'][i]
            h = quotes['high'][i]
            lo = quotes['low'][i]
            c = quotes['close'][i]
            v = int(quotes['volume'][i]) if quotes['volume'][i] else 0
            if o and h and lo and c:
                rows.append({'ts': ts, 'symbol': label, 'open': float(o), 'high': float(h),
                             'low': float(lo), 'close': float(c), 'volume': v})
        path = os.path.join(OUT_DIR, f'{label}-{days}d-{interval}-fresh.csv')
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['ts','symbol','open','high','low','close','volume'])
            w.writeheader()
            w.writerows(rows)
        print(f'✅ {label} {interval}: {len(rows)} rows → {os.path.basename(path)}')
        return rows
    except Exception as e:
        print(f'❌ {label} {interval}: {e}')
        return []

def combine(name, *datasets):
    """Combine multiple symbol datasets into one file, sorted by timestamp."""
    combined = []
    for rows in datasets:
        combined.extend(rows)
    combined.sort(key=lambda r: r['ts'])
    path = os.path.join(OUT_DIR, name)
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['ts','symbol','open','high','low','close','volume'])
        w.writeheader()
        w.writerows(combined)
    print(f'✅ Combined: {len(combined)} rows → {name}')

if __name__ == '__main__':
    # Pull daily 5y
    nq_daily = get_yahoo('NQ=F', 1825, '1d', 'NQ')
    es_daily = get_yahoo('ES=F', 1825, '1d', 'ES')
    if nq_daily and es_daily:
        combine('ALL-2MARKETS-NQ-ES-1d-5y-fresh.csv', nq_daily, es_daily)

    # Pull 15m 60d
    nq_15m = get_yahoo('NQ=F', 60, '15m', 'NQ')
    es_15m = get_yahoo('ES=F', 60, '15m', 'ES')
    if nq_15m and es_15m:
        combine('ALL-2MARKETS-NQ-ES-15m-60d-fresh.csv', nq_15m, es_15m)

    print("\n🎯 Data refresh complete!")
    print("Files ready for: backtests, factory, walkforward, prop-firm simulation")
