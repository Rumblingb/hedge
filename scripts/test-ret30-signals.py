#!/usr/bin/env python3
"""Quick ret-30-momentum signal test — does the new strategy fire?"""
import csv
from datetime import datetime

DATA = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv"

def is_active_session(ts):
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    h, m = dt.hour, dt.minute
    total = h * 60 + m
    return ((12*60+30) <= total <= (15*60+30)) or ((17*60) <= total <= (19*60+30))

def atr14(highs, lows, closes, i):
    trs = []
    for j in range(max(1, i-14), i):
        tr = max(highs[j] - lows[j], abs(highs[j] - closes[j-1]), abs(lows[j] - closes[j-1]))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0

with open(DATA) as f:
    rows = list(csv.DictReader(f))

by_sym = {}
for r in rows:
    by_sym.setdefault(r["symbol"], []).append(r)

print("=== ret-30-momentum Signal Test ===\n")

for sym in ["ES", "NQ"]:
    bars = by_sym[sym]
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    ts_list = [b["ts"] for b in bars]
    vols = [float(b.get("volume", 0) or 0) for b in bars]

    signals = []
    for i in range(30, len(closes)):
        if not is_active_session(ts_list[i]):
            continue
        
        ret_30 = closes[i] - closes[i-30]
        atr = atr14(highs, lows, closes, i)
        if atr <= 0 or abs(ret_30) < 0.5 * atr:
            continue
        
        avg_vol = sum(vols[i-30:i]) / 30
        if vols[i] < 1.2 * avg_vol:
            continue
        
        side = "long" if ret_30 > 0 else "short"
        signals.append({"ts": ts_list[i], "side": side, "ret_30_pct": round(ret_30 / closes[i] * 100, 2), "atr": round(atr, 2)})

    longs = sum(1 for s in signals if s["side"] == "long")
    shorts = sum(1 for s in signals if s["side"] == "short")
    
    print(f"{sym}: {len(signals)} signals ({longs}L/{shorts}S, {len(signals)/5:.1f}/day)")
    if signals:
        for s in signals[:3]:
            print(f"  {s['ts'][11:19]} | {s['side']:5s} | ret_30={s['ret_30_pct']:>6.2f}% | atr={s['atr']}")
    print()
