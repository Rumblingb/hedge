#!/usr/bin/env python3
"""Multi-Timeframe Candlestick Pattern & Correlation Analyzer"""
import pandas as pd
import numpy as np
import json, sys
from pathlib import Path

DATA = Path.home() / "hedge" / "data" / "free"

# Load all available timeframes
tfs = {}
for f in DATA.glob("ALL-*60m*.csv"):
    tfs['60m'] = str(f)
for f in DATA.glob("ALL-*1d*.csv"):
    tfs['1d'] = str(f)

results = {}
for label, path in tfs.items():
    raw = pd.read_csv(path)
    raw['time'] = pd.to_datetime(raw['ts'])
    raw = raw.sort_values(['symbol','time'])
    
    for sym in ['NQ','ES','CL','GC','6E','ZN']:
        s = raw[raw['symbol']==sym].copy()
        if len(s) < 15: continue
        
        s['hour_et'] = (s['time'].dt.hour - 4) % 24
        s['pct'] = s['close'].pct_change() * 100
        s['range_pct'] = (s['high'] - s['low']) / s['close'].shift(1) * 100
        s['body'] = abs(s['close'] - s['open']) / s['open'].shift(1) * 100
        s['upper_wick'] = (s['high'] - s[['close','open']].max(axis=1)) / s['open'].shift(1) * 100
        s['lower_wick'] = (s[['close','open']].min(axis=1) - s['low']) / s['open'].shift(1) * 100
        s['gap'] = (s['open'] - s['close'].shift(1)) / s['close'].shift(1) * 100
        
        # Patterns
        s['doji'] = s['body'] < (s['range_pct'] * 0.1)
        s['hammer'] = (s['lower_wick'] > s['body']*2) & (s['upper_wick'] < s['body']*0.3)
        s['shooting_star'] = (s['upper_wick'] > s['body']*2) & (s['lower_wick'] < s['body']*0.3)
        s['engulfing'] = (s['pct'].shift(1) < -0.2) & (s['pct'] > 0.3) & (s['body'] > s['body'].shift(1)*1.5)
        s['outside_bar'] = s['range_pct'] > s['range_pct'].rolling(10).mean()*2
        s['narrow_bar'] = s['range_pct'] < s['range_pct'].rolling(10).mean()*0.5
        
        # Next-bar return after pattern
        for pat in ['doji','hammer','shooting_star','engulfing','outside_bar','narrow_bar']:
            hits = s[s[pat]]
            if len(hits) > 2:
                avg_next = hits['pct'].shift(-1).mean()
            else:
                avg_next = 0
            s.loc[s[pat], f'{pat}_next'] = avg_next
        
        # Volatility regime correlation
        s['vol_regime'] = 'low'
        s.loc[s['range_pct'] > s['range_pct'].rolling(20).mean(), 'vol_regime'] = 'high'
        
        # Cross-timeframe alignment (if 60m data)
        daily_group = s.groupby(s['time'].dt.date)
        if label == '60m':
            daily_vol = daily_group['range_pct'].mean()
            s['daily_vol'] = s['time'].map(lambda t: daily_vol.get(t.date(), np.nan))
        
        # Correlation: pattern frequency vs. volatility
        hourly_stats = s.groupby('hour_et').agg({
            'range_pct': 'mean',
            'pct': 'mean',
            'doji': 'sum',
            'hammer': 'sum',
            'shooting_star': 'sum',
            'engulfing': 'sum',
            'outside_bar': 'sum',
            'gap': 'mean',
            'pct': ['mean','std']
        })
        
        # Correlation between patterns and next-bar moves
        pattern_effect = {}
        for pat in ['doji','hammer','shooting_star','engulfing','outside_bar','narrow_bar']:
            hits = s[s[pat]]
            if len(hits) > 3:
                next_ret = s.loc[hits.index + 1, 'pct'].dropna()
                pattern_effect[pat] = {
                    'count': int(len(hits)),
                    'freq_pct': round(len(hits)/len(s)*100, 1),
                    'avg_next_return': round(float(next_ret.mean()), 3),
                    'win_rate': round(float((next_ret > 0).mean()), 3),
                    'std_next': round(float(next_ret.std()), 3)
                }
        
        results[f'{sym}_{label}'] = {
            'bars': len(s),
            'date_range': f"{s['time'].min()} to {s['time'].max()}",
            'avg_range': round(float(s['range_pct'].mean()), 3),
            'patterns': {p: pattern_effect[p] for p in pattern_effect},
            'hours_peak_vol': {int(k): round(float(v['range_pct']['mean']), 3) 
                              for k, v in hourly_stats.iterrows() 
                              if v[('range_pct','mean')] > hourly_stats[('range_pct','mean')].quantile(0.75)},
            'avg_gap': round(float(s['gap'].mean()), 3),
            'gap_freq': round(float((s['gap'].abs() > 0.3).mean() * 100), 1),
        }

print(json.dumps(results, indent=2))
