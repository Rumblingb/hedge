#!/usr/bin/env python3
"""Backtest TP strategies on today's 1m NQ data"""
import sys, json, urllib.request
from datetime import datetime, timezone

# Fetch data
url = "https://query1.finance.yahoo.com/v8/finance/chart/MNQ=F?interval=1m&range=1d"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
d = json.loads(urllib.request.urlopen(req).read())
r = d['chart']['result'][0]

ts, q = r['timestamp'], r['indicators']['quote'][0]

prices = []
et_offset = -4
for i in range(len(ts)):
    t = datetime.fromtimestamp(ts[i], timezone.utc)
    h, m = t.hour + et_offset, t.minute
    if (h == 9 and m >= 30) or h > 9:
        if q['close'][i] is not None and q['close'][i] > 0:
            prices.append({
                't': f'{h}:{m:02d}',
                'p': q['close'][i],
                'h': q['high'][i],
                'l': q['low'][i]
            })

print(f"Session 1m bars: {len(prices)}")
if len(prices) < 10:
    print("Not enough data")
    sys.exit(1)

entry = 29267
peak = max(p['p'] for p in prices)
end = prices[-1]['p']

print(f"\n=== RAW DATA ===")
print(f"Entry: {entry} | Peak: {peak:.0f} (+{peak-entry:.0f}pts) | End: {end:.0f} (+{end-entry:.0f}pts)")
print(f"Peak P&L: ${(peak-entry)*6:.0f} | End P&L: ${(end-entry)*6:.0f}")
print(f"TP 29,517: {'HIT at ' + [p['t'] for p in prices if p['p'] >= 29517][0] if any(p['p'] >= 29517 for p in prices) else 'MISSED (by ' + str(int(29517 - peak)) + 'pts)'}")
print(f"TP 29,575: {'HIT' if any(p['p'] >= 29575 for p in prices) else 'MISSED (by ' + str(int(29575 - peak)) + 'pts)'}")

# Strategy: Scale 50%@+50, 30%@+100, trail 20% from +100 with 30pt trail
print(f"\n=== STRATEGY A: Scale 50/30/20 + Trail ===")
total_contracts = 3

s50 = next((p for p in prices if p['p'] >= entry + 50), None)
s50_profit = 50 * 6 * (total_contracts * 0.5) * 3 if s50 else 0
print(f"50% exit @ {entry+50}: {'YES at ' + s50['t'] if s50 else 'NO'} = ${s50_profit:.0f}")

s100 = next((p for p in prices if p['p'] >= entry + 100), None)
s100_profit = 100 * 6 * (total_contracts * 0.3) * 3 if s100 else 0
print(f"30% exit @ {entry+100}: {'YES at ' + s100['t'] if s100 else 'NO'} = ${s100_profit:.0f}")

# Trail remaining 20% with 30pt from +100
trail_entry = entry
trail_activated = False
trail_stop = 0
max_seen = entry
for p in prices:
    if p['p'] > max_seen:
        max_seen = p['p']
        if max_seen >= entry + 100:
            trail_activated = True
            trail_stop = max_seen - 30
    if trail_activated and p['p'] < trail_stop:
        trail_exit_price = p['p']
        break
else:
    trail_exit_price = prices[-1]['p']

trail_profit = ((trail_exit_price - entry) * 6 * (total_contracts * 0.2) * 3) if trail_activated else 0
print(f"20% trail @ +100pt lock, 30pt stop: {'EXIT at ' + f'{trail_exit_price:.0f}' if trail_activated else 'NEVER EXITED'} = ${trail_profit:.0f}")

total_a = s50_profit + s100_profit + trail_profit
print(f"**Total Strategy A: ${total_a:.0f}**")

# Strategy B: Simple 80pt TP (catches most quick moves)
print(f"\n=== STRATEGY B: Fixed TP @ +80pts ===")
tp80 = next((p for p in prices if p['p'] >= entry + 80), None)
if tp80:
    print(f"HIT at {tp80['t']} = ${80*6*total_contracts:.0f}")
else:
    print(f"MISSED")

# Strategy C: Trail only - lock at +30, 10pt trail
print(f"\n=== STRATEGY C: Trail - lock @ +30, 10pt trail ===")
locked = None
trail_exit = None
for p in prices:
    if locked is None and p['p'] >= entry + 30:
        locked = entry + 30
    if locked:
        trail = p['p'] - 10
        if trail > locked:
            locked = trail
    if locked is not None and p['p'] < locked:
        trail_exit = p['p']
        print(f"Locked at +30@{locked:.0f} | Trail exit @ {trail_exit:.0f} ({(trail_exit-entry)*6*total_contracts:.0f})")
        break

# Strategy D: 3 equal contracts at +50, +100, +150
print(f"\n=== STRATEGY D: 3 equal TP @ +50, +100, +150 ===")
tp50 = any(p['p'] >= entry+50 for p in prices)
tp100 = any(p['p'] >= entry+100 for p in prices)
tp150 = any(p['p'] >= entry+150 for p in prices)
total_d = 0
if tp50: total_d += 50*6
if tp100: total_d += 100*6
if tp150: total_d += 150*6
print(f"TP +50: {'HIT' if tp50 else 'NO'} | +100: {'HIT' if tp100 else 'NO'} | +150: {'HIT' if tp150 else 'NO'}")
print(f"**Total Strategy D: ${total_d*total_contracts:.0f}**")

# Strategy E: 50pt TP + trail remaining with 20pt lock from +50
print(f"\n=== STRATEGY E: 50% @ +50, 50% trail (20pt lock from +50) ===")
locked_e = None
trail_exit_e = entry
for p in prices:
    if locked_e is None and p['p'] >= entry + 50:
        locked_e = entry + 50
    if locked_e:
        trail = p['p'] - 20
        if trail > locked_e:
            locked_e = trail
    if locked_e is not None and p['p'] < locked_e:
        trail_exit_e = p['p']
        break
half50 = 50*6*0.5*total_contracts
half_trail = (trail_exit_e - entry)*6*0.5*total_contracts
print(f"50% @ +50: ${half50:.0f} | 50% trail: ${half_trail:.0f}")
print(f"**Total Strategy E: ${half50+half_trail:.0f}**")
