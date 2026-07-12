#!/usr/bin/env python3
"""Quant analysis: FFT regime detection + cross-asset correlation for NQ"""

import json, subprocess, sys, os, math
import numpy as np
from scipy import fft
from collections import defaultdict

def run(cmd: str) -> str:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    return r.stdout or r.stderr

# 1. Fetch NQ 5m data from Yahoo
print("=== FETCHING NQ 5M DATA ===")
cmd = """cd /Users/brain/hedge && source ~/Library/Application\ Support/AgentPay/bill/bill.env && npx tsx -e "
(async () => {
  const q = await (await fetch('https://query1.finance.yahoo.com/v8/finance/chart/NQ=F?range=5d&interval=5m')).json();
  console.log(JSON.stringify(q.chart?.result?.[0] ?? {error: 'no data'}));
})();
" 2>/dev/null"""

data_raw = run(cmd)
try:
    data = json.loads(data_raw)
    timestamps = data.get('timestamp', [])
    quotes = data.get('indicators', {}).get('quote', [{}])[0]
    closes = quotes.get('close', [])
    highs = quotes.get('high', [])
    lows = quotes.get('low', [])
    volumes = quotes.get('volume', [])
    print(f"Loaded {len(closes)} bars")
except:
    print(f"Parse error: {data_raw[:200]}")
    sys.exit(1)

if len(closes) < 50:
    print(f"Too few bars: {len(closes)}")
    sys.exit(1)

# Filter valid closes
valid = [(c, h, l, v, t) for c, h, l, v, t in zip(closes, highs, lows, volumes, timestamps) if c and h and l and v]
closes = [c for c,_,_,_,_ in valid]
highs = [h for _,h,_,_,_ in valid]
lows = [l for _,_,l,_,_ in valid]
volumes = [v for _,_,_,v,_ in valid]
timestamps = [t for _,_,_,_,t in valid]
print(f"Valid bars: {len(closes)}")

# 2. FFT-based regime detection (on DETRENDED data for short-term regime)
print("\n=== FFT REGIME DETECTION (Detrended) ===")
arr = np.array(closes, dtype=np.float64)
# Use returns (first difference of log) for detrending
log_returns = np.diff(np.log(arr))
n = len(log_returns)
freq = fft.rfft(log_returns - np.mean(log_returns))
power = np.abs(freq) ** 2
freqs = fft.rfftfreq(n, d=1.0)

# Bands: 0-0.05 = trend cycles (20+ bars), 0.05-0.15 = medium (7-20 bars), 0.15+ = noise (<7 bars)
trend_band = int(n * 0.05 * 2)
medium_band = int(n * 0.15 * 2)
low_freq_energy = np.sum(power[:trend_band])
mid_freq_energy = np.sum(power[trend_band:medium_band])
high_freq_energy = np.sum(power[medium_band:])
total = low_freq_energy + mid_freq_energy + high_freq_energy
ratio = low_freq_energy / total if total > 0 else 0.5
mid_ratio = mid_freq_energy / total if total > 0 else 0.3

print(f"Trend energy (20+ bars): {low_freq_energy:.2f}")
print(f"Medium energy (7-20 bars): {mid_freq_energy:.2f}")  
print(f"High freq/noise (<7 bars): {high_freq_energy:.2f}")
print(f"Trend/Range ratio: {ratio:.4f}  (<0.3=range, 0.3-0.6=mixed, >0.6=trending)")

regime = "RANGE" if ratio < 0.3 else ("TRENDING" if ratio > 0.6 else "MIXED")
print(f"Regime: {regime}")

# 3. Volume profile analysis
print("\n=== VOLUME PROFILE ===")
hourly_vol = defaultdict(float)
hourly_count = defaultdict(int)
for v, t in zip(volumes, timestamps):
    from datetime import datetime
    dt = datetime.fromtimestamp(t)
    h = dt.hour
    hourly_vol[h] += v
    hourly_count[h] += 1

print("Hourly volume profile (ET):")
for h in sorted(hourly_vol.keys()):
    avg = hourly_vol[h] / max(hourly_count[h], 1)
    bar = "#" * int(avg / max(hourly_vol.values()) * 30)
    print(f"  {h:02d}:00 - {avg:>8.0f} {bar}")

# 4. Volatility analysis
print("\n=== VOLATILITY ANALYSIS ===")
returns = [(closes[i] - closes[i-1]) / closes[i-1] * 100 for i in range(1, len(closes))]
avg_ret = np.mean(returns)
std_ret = np.std(returns)
max_up = max(returns) if returns else 0
max_down = min(returns) if returns else 0
print(f"Avg return per bar: {avg_ret:+.4f}%")
print(f"Std dev: {std_ret:.4f}%")
print(f"Max up: {max_up:+.4f}%")
print(f"Max down: {max_down:+.4f}%")

# 5. ATR-based range analysis
print("\n=== RANGE ANALYSIS ===")
true_ranges = []
for i in range(1, len(highs)):
    hl = highs[i] - lows[i]
    hc = abs(highs[i] - closes[i-1])
    lc = abs(lows[i] - closes[i-1])
    true_ranges.append(max(hl, hc, lc))
atr = np.mean(true_ranges[-20:]) if len(true_ranges) >= 20 else np.mean(true_ranges)
avg_range = np.mean([h - l for h, l in zip(highs, lows)])
print(f"ATR(20): {atr:.2f}")
print(f"Avg bar range: {avg_range:.2f}")
print(f"Range/Close ratio: {avg_range / np.mean(closes) * 100:.4f}%")

# 6. Strategy recommendation based on regime
print("\n=== STRATEGY RECOMMENDATION ===")
if regime == "RANGE":
    print("→ Mean-reversion: VWAP bands, contraband, ICHIMOKU")
    print("→ Avoid ORB breakout (false breakouts common)")
    print("→ Tight SL: 1.5x ATR")
elif regime == "TRENDING":
    print("→ ORB breakout with FFT confirmation")
    print("→ ICT ORG Gap Fill")
    print("→ Wider SL: 2.5x ATR, let winners run")
else:
    print("→ Mixed regime: wait for clear signal")
    print("→ Session-aware ORB with higher threshold")

# 7. Key levels
print("\n=== KEY LEVELS ===")
current = closes[-1] if closes else 0
r1 = current + atr * 2
s1 = current - atr * 2
print(f"Current: {current:.2f}")
print(f"R1 (+2ATR): {r1:.2f}")
print(f"S1 (-2ATR): {s1:.2f}")

print("\n=== COMPLETE ===")
