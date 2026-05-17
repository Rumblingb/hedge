#!/usr/bin/env python3
"""SL Hunting / Previous Day Low Reversal Strategy for NQ.
Tests: previous day low/high reversals, stop-run patterns, and session-specific edge."""
import csv, sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

BASE = "/Users/brain/hedge/data/free"

@dataclass
class Bar:
    ts: str; symbol: str; open: float; high: float; low: float; close: float; volume: int
    @property
    def dt(self): return datetime.fromisoformat(self.ts.replace('Z','+00:00'))

def load(path: str, symbol: str = "NQ") -> List[Bar]:
    bars = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row['symbol'].strip().upper() == symbol:
                bars.append(Bar(ts=row['ts'], symbol=row['symbol'],
                    open=float(row['open']), high=float(row['high']),
                    low=float(row['low']), close=float(row['close']), volume=int(row['volume'])))
    return bars

def atr(bars, idx, period=14):
    if idx < period: return 0.0
    return sum(bars[j].high - bars[j].low for j in range(idx-period, idx)) / period

# ============================================
# PREV DAY HIGH/LOW DETECTION
# ============================================
def build_daily_levels(bars: List[Bar]) -> dict:
    """Build daily high/low/close for each trading day"""
    daily = {}
    day_bars = {}
    for b in bars:
        d = b.dt.date()
        if d not in day_bars:
            day_bars[d] = []
        day_bars[d].append(b)
    
    prev_high = prev_low = prev_close = None
    prev_date = None
    levels = {}
    
    for date in sorted(day_bars.keys()):
        db = day_bars[date]
        if prev_date:  # has previous day data
            levels[date] = {
                'prev_high': prev_high,
                'prev_low': prev_low,
                'prev_close': prev_close,
                'prev_range': prev_high - prev_low if prev_high and prev_low else 0,
            }
        prev_high = max(b.high for b in db)
        prev_low = min(b.low for b in db)
        prev_close = db[-1].close
        prev_date = date
    return levels

# ============================================
# STRATEGY 1: Previous Day Low Reversal
# ============================================
def sl_hunting_reversal(bars: List[Bar], exit_offset: int = 8, atr_mult: float = 1.5):
    """
    When price approaches previous day's low and reverses, go long.
    Entry conditions:
    1. Price touches or breaks below previous day low
    2. Closes back above prev day low (reversal)
    3. Volume confirmation on the reversal bar
    
    Exit: exit_offset bars later (capture mean reversion back to prev day high/close)
    """
    daily = build_daily_levels(bars)
    trades = []
    n = len(bars)
    
    # Map bar index to date
    bar_dates = {}
    for i, b in enumerate(bars):
        d = b.dt.date()
        if d not in bar_dates:
            bar_dates[d] = []
        bar_dates[d].append(i)
    
    for i in range(2, n - exit_offset):
        d = bars[i].dt.date()
        if d not in daily: continue
        levels = daily[d]
        prev_low = levels['prev_low']
        prev_high = levels['prev_high']
        prev_close = levels['prev_close']
        if None in (prev_low, prev_high, prev_close): continue
        
        atr_v = atr(bars, i, 14)
        if atr_v <= 0: continue
        
        # Check if first 30min of NY session (most common for SL hunts)
        h, m = bars[i].dt.hour, bars[i].dt.minute
        mins = h * 60 + m
        is_ny = 9*60+30 <= mins <= 16*60
        
        bar = bars[i]
        exit_b = bars[i + exit_offset]
        
        # Condition: price touched below prev day low then reversed
        if bar.low < prev_low and bar.close > prev_low:
            # Long: SL hunt failed, reversal confirmed
            vol_check = bar.volume > 1000  # basic volume filter for 5m/15m bars
            if vol_check:
                r = (exit_b.close - bar.close) / atr_v
                trades.append(('long', r, 'sl-hunt-long', is_ny))
        
        # Condition: price touched above prev day high then reversed down
        if bar.high > prev_high and bar.close < prev_high:
            vol_check = bar.volume > 1000
            if vol_check:
                r = (bar.close - exit_b.close) / atr_v
                trades.append(('short', r, 'sl-hunt-short', is_ny))
    
    return trades

# ============================================
# STRATEGY 2: Range breakout with volume + previous day levels
# ============================================
def daily_range_breakout(bars: List[Bar]):
    """
    Breakout of previous day's range with volume confirmation.
    If price breaks above prev high with volume -> long continuation
    If price breaks below prev low with volume -> short continuation
    Exit at 8 bars.
    """
    daily = build_daily_levels(bars)
    trades = []
    n = len(bars)
    
    for i in range(2, n - 8):
        d = bars[i].dt.date()
        if d not in daily: continue
        levels = daily[d]
        prev_high = levels['prev_high']
        prev_low = levels['prev_low']
        if None in (prev_high, prev_low): continue
        
        atr_v = atr(bars, i, 14)
        if atr_v <= 0: continue
        
        bar = bars[i]
        exit_b = bars[i + 8]
        
        avg_vol = sum(b.volume for b in bars[max(0,i-10):i]) / min(10, i)
        if avg_vol <= 0: continue
        
        # Breakout above prev high with volume
        if bar.close > prev_high and bar.volume > avg_vol * 1.3:
            r = (exit_b.close - bar.close) / atr_v
            trades.append(('long', r, 'range-breakout-long'))
        # Breakdown below prev low with volume
        elif bar.close < prev_low and bar.volume > avg_vol * 1.3:
            r = (bar.close - exit_b.close) / atr_v
            trades.append(('short', r, 'range-breakout-short'))
    
    return trades

# ============================================
# STRATEGY 3: Intraday Session Momentum (NY open drive)
# ============================================
def session_momentum(bars: List[Bar]):
    """First 60min of NY session: trade the initial drive direction"""
    trades = []
    n = len(bars)
    
    daily = {}
    for b in bars:
        d = b.dt.date()
        if d not in daily:
            daily[d] = []
        daily[d].append(b)
    
    for date, day_bars in sorted(daily.items()):
        ny_bars = [b for b in day_bars if 9*60+30 <= b.dt.hour*60+b.dt.minute <= 11*60]
        if len(ny_bars) < 6: continue  # need enough 5m bars
        
        # Opening range: first 30min
        open_high = max(b.high for b in ny_bars[:6])
        open_low = min(b.low for b in ny_bars[:6])
        
        # Check which direction breaks first after opening range
        for i in range(6, len(ny_bars) - 8):
            atr_v = atr(day_bars, day_bars.index(ny_bars[i]), 14)
            if atr_v <= 0: continue
            
            b = ny_bars[i]
            # Check for breakout of opening range
            if b.close > open_high:
                exit_b = ny_bars[min(i+8, len(ny_bars)-1)]
                r = (exit_b.close - b.close) / atr_v
                trades.append(('long', r, 'open-drive-long'))
                break  # first direction wins
            elif b.close < open_low:
                exit_b = ny_bars[min(i+8, len(ny_bars)-1)]
                r = (b.close - exit_b.close) / atr_v
                trades.append(('short', r, 'open-drive-short'))
                break
    
    return trades

def report(trades, label, session_filter=None):
    if not trades: return f"{label}: 0 trades"
    if session_filter:
        trades = [t for t in trades if t[3] == session_filter] if len(trades[0]) > 3 else trades
    if not trades: return f"{label}: 0 trades"
    
    r_vals = [t[1] for t in trades]
    n = len(r_vals)
    r_total = sum(r_vals)
    wins = sum(1 for t in r_vals if t > 0)
    wr = wins / n * 100
    types = {}
    for t in trades:
        label_t = t[2] if len(t) > 2 else "unknown"
        types[label_t] = types.get(label_t, 0) + 1
    return f"{label}: {n}t, {wins}/{n-wins} W/L ({wr:.1f}%), R {r_total:+.2f}, avg {r_total/n:+.3f}, breakdown: {types}"

print("=" * 80)
print("SL HUNTING / PREV DAY LEVEL STRATEGIES")
print("=" * 80)

for tf_name, csv_path, bars_count in [
    ("5m", f"{BASE}/nq-5m.csv", 5652),
    ("15m", f"{BASE}/nq-15m.csv", 1894),
    ("30m", f"{BASE}/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv", 947),
]:
    print(f"\n--- {tf_name} ---")
    if tf_name in ("30m",):
        bars = load(csv_path, "NQ")
    else:
        bars = load(csv_path, "NQ")
    print(f"Loaded {len(bars)} NQ bars")
    
    # SL Hunting reversal
    sl_trades = sl_hunting_reversal(bars)
    print(f"  {report(sl_trades, 'SL-hunting-reversal')}")
    
    # Filter by NY session for SL hunts
    ny_sl = [t for t in sl_trades if t[3]]
    non_ny_sl = [t for t in sl_trades if not t[3]]
    if ny_sl:
        print(f"    NY only: {report(ny_sl, '')}")
    if non_ny_sl:
        print(f"    Non-NY: {report(non_ny_sl, '')}")
    
    # Daily range breakout
    dr_trades = daily_range_breakout(bars)
    print(f"  {report(dr_trades, 'daily-range-breakout')}")
    
    # Session momentum (only makes sense on 5m)
    if tf_name == "5m":
        sm_trades = session_momentum(bars)
        print(f"  {report(sm_trades, 'session-momentum')}")

# Composite: what if we combine SL hunting + daily range breakout
print(f"\n{'='*80}")
print("COMPOSITE ANALYSIS")
print(f"{'='*80}")
bars15 = load(f"{BASE}/nq-15m.csv", "NQ")
sl_15 = sl_hunting_reversal(bars15)
dr_15 = daily_range_breakout(bars15)

all_15 = [(t[1], t[2]) for t in sl_15] + [(t[1], t[2]) for t in dr_15]
if all_15:
    r_total = sum(t[0] for t in all_15)
    n = len(all_15)
    wins = sum(1 for t in all_15 if t[0] > 0)
    print(f"Composite (SL+Hunt+RangeBreakout) 15m: {n}t, {wins}/{n-wins} W/L ({wins/n*100:.1f}%), R {r_total:+.2f}")
