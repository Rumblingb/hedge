#!/usr/bin/env python3
"""entry_exit_mtf_test.py — READ-ONLY multi-timeframe execution test.

Founder design: signal on the HIGHER timeframe (breakout of the opening range), then use the
SHORTER timeframe (1m) for PRECISE ENTRY and PRECISE EXIT:
  - ENTRY: first 1m COUNTER candle after breakout (long->red, short->green) = pullback fill.
  - EXIT : 1m bracket — exit the instant a 1m bar hits target/stop (don't wait for the HTF bar
           to close), target/stop sized off the opening range.

Sweeps signal timeframes 5/15/30/45/60m. Compares, per TF:
  BASELINE  = breakout-close entry + HTF time-exit
  ENTRY-ONLY= 1m-pullback entry    + HTF time-exit
  FULL      = 1m-pullback entry    + 1m bracket exit
Relative comparison (same signals) -> trustworthy. Routes nothing.
"""
import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path.home() / "hedge" / "data" / "free"
OUT = Path.home() / "hedge" / ".rumbling-hedge" / "state" / "entry-exit-mtf.latest.json"
ONE_MIN_FILE = sys.argv[1] if len(sys.argv) > 1 else "ES-1m-2020-2024.csv"
SYMBOL = sys.argv[2] if len(sys.argv) > 2 else "ES"

RANGE_MIN = 30
PULLBACK_WINDOW_MIN = 10
HOLD_BARS = 6           # HTF time-exit
TP_MULT = 1.0           # 1m target  = TP_MULT * opening_range
SL_MULT = 0.6           # 1m stop    = SL_MULT * opening_range
MAX_HOLD_MIN = 180      # cap on the 1m bracket trade
COST = 1.5
TIMEFRAMES = (5, 15, 30, 45, 60)


def load_1m(fn, max_rows=900000):
    bars = []
    with open(DATA / fn) as f:
        for i, r in enumerate(csv.DictReader(f)):
            if i >= max_rows:
                break
            try:
                ts = (r.get("ts") or r.get("datetime") or r.get("timestamp ET")
                      or r.get("timestamp") or r.get("time"))
                bars.append({"ts": ts, "o": float(r["open"]), "h": float(r["high"]),
                             "l": float(r["low"]), "c": float(r["close"])})
            except (KeyError, ValueError, TypeError):
                continue
    return bars


def minute_key(ts):
    return ts[:10], int(ts[11:13]) * 60 + int(ts[14:16]) if len(ts) >= 16 else 0


def resample(bars1m, tf):
    out, cur = [], None
    for b in bars1m:
        try:
            d, m = minute_key(b["ts"])
        except (ValueError, TypeError):
            continue
        bucket = (d, m // tf)
        if cur is None or cur["key"] != bucket:
            if cur:
                out.append(cur)
            cur = {"key": bucket, "day": d, "h": b["h"], "l": b["l"], "c": b["c"], "ones": [b]}
        else:
            cur["h"] = max(cur["h"], b["h"]); cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]; cur["ones"].append(b)
    if cur:
        out.append(cur)
    return out


def one_min_exit(ones, entry, side, rng):
    """Scan 1m bars; exit at first target/stop touch; else time-cap at MAX_HOLD_MIN."""
    target = entry + side * TP_MULT * rng
    stop = entry - side * SL_MULT * rng
    for k, o in enumerate(ones):
        if k > MAX_HOLD_MIN:
            return (o["c"] - entry) * side
        if side == 1:
            if o["l"] <= stop:
                return (stop - entry)
            if o["h"] >= target:
                return (target - entry)
        else:
            if o["h"] >= stop:
                return (entry - stop)
            if o["l"] <= target:
                return (entry - target)
    return (ones[-1]["c"] - entry) * side if ones else 0.0


def backtest(tf_bars, tf):
    by_day = defaultdict(list)
    for tb in tf_bars:
        by_day[tb["day"]].append(tb)
    rb = max(1, RANGE_MIN // tf)
    base, entry_only, full = [], [], []
    for day, dbars in by_day.items():
        if len(dbars) < rb + HOLD_BARS + 1:
            continue
        orb = dbars[:rb]
        hi, lo = max(x["h"] for x in orb), min(x["l"] for x in orb)
        rng = hi - lo
        if rng <= 0:
            continue
        for pos in range(rb, len(dbars) - HOLD_BARS):
            tb = dbars[pos]
            side = 1 if tb["c"] > hi else (-1 if tb["c"] < lo else 0)
            if side == 0:
                continue
            # 1m stream from breakout bar to end of session
            stream = [o for q in range(pos, len(dbars)) for o in dbars[q]["ones"]]
            # entry B: first counter candle within window
            counter, seen = None, 0
            for ci, o in enumerate(stream):
                if (side == 1 and o["c"] < o["o"]) or (side == -1 and o["c"] > o["o"]):
                    counter, cidx = o["c"], ci
                    break
                seen += 1
                if seen > PULLBACK_WINDOW_MIN:
                    break
            htf_exit = dbars[pos + HOLD_BARS]["c"]
            entryA = tb["c"]
            base.append((htf_exit - entryA) * side - COST)
            if counter is None:
                continue
            entry_only.append((htf_exit - counter) * side - COST)
            full.append(one_min_exit(stream[cidx + 1:], counter, side, rng) - COST)
            break
    return base, entry_only, full


def stats(t):
    if not t:
        return {"trades": 0}
    w = [x for x in t if x > 0]
    gl = abs(sum(x for x in t if x <= 0))
    pf = (sum(w) / gl) if gl > 0 else None
    return {"n": len(t), "wr": round(len(w) / len(t), 3), "net": round(sum(t), 1),
            "avg": round(statistics.mean(t), 2), "pf": round(pf, 2) if pf else None}


def main():
    bars1m = load_1m(ONE_MIN_FILE)
    results = {}
    for tf in TIMEFRAMES:
        b, e, f = backtest(resample(bars1m, tf), tf)
        results[f"{tf}m"] = {"baseline_close+htf_exit": stats(b),
                             "pullback_entry+htf_exit": stats(e),
                             "pullback_entry+1m_bracket_exit": stats(f)}
    rec = {"generatedAt": datetime.now(timezone.utc).isoformat(), "researchOnly": True,
           "writesOrders": False, "touchesBroker": False, "movesFunds": False,
           "readyForExecution": False, "readyForDemoExpansion": False, "readyForLive": False,
           "instrument": SYMBOL, "source": ONE_MIN_FILE,
           "span": [bars1m[0]["ts"], bars1m[-1]["ts"]] if bars1m else None,
           "design": "HTF breakout signal; 1m counter-candle entry; 1m bracket exit (TP %.1f / SL %.1f x opening range)" % (TP_MULT, SL_MULT),
           "params": {"range_min": RANGE_MIN, "pullback_window_min": PULLBACK_WINDOW_MIN,
                      "htf_hold_bars": HOLD_BARS, "tp_mult": TP_MULT, "sl_mult": SL_MULT,
                      "max_hold_min": MAX_HOLD_MIN, "cost": COST},
           "results": results,
           "caveat": "Relative comparison (trustworthy); absolute is a research proxy, not blessed. "
                     "1m exit assumes bar-touch fills; model slippage/limit realism before promotion."}
    OUT.write_text(json.dumps(rec, indent=2) + "\n")
    return rec


if __name__ == "__main__":
    r = main()
    print(f"\n=== MTF ENTRY+EXIT ({r['instrument']}, {r['span'][0][:10]}..{r['span'][1][:10]}) ===")
    print("HTF | baseline(close+htf)      | pullback-entry(+htf)      | FULL pullback+1m-bracket")
    for tf, x in r["results"].items():
        b, e, f = x["baseline_close+htf_exit"], x["pullback_entry+htf_exit"], x["pullback_entry+1m_bracket_exit"]
        fmt = lambda s: f"PF{s.get('pf')} net{s.get('net')} wr{s.get('wr')} n{s.get('n')}"
        print(f"{tf:>3} | {fmt(b):<24} | {fmt(e):<24} | {fmt(f)}")
