#!/usr/bin/env python3
"""entry_refinement_test.py — READ-ONLY test of the pullback-entry idea on 15m/30m breakouts.

Idea (founder): on a breakout, don't chase the breakout close — drop to 1m and enter on the
first COUNTER candle (long -> first RED 1m candle; short -> first GREEN 1m candle), i.e. a small
pullback, for a better fill. This is a RELATIVE entry-method comparison (same base signal, same
exit) so the proxy's absolute-edge flaws cancel — the comparison is the trustworthy part.

Resamples ES 1m -> 15m & 30m (one aligned source), detects opening-range breakouts, then compares:
  A) enter at breakout-bar close   vs   B) enter on first 1m counter-candle within K minutes.
Same time-exit. Reports entry improvement, PF, netR, win rate, fill rate. Routes nothing.
"""
import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path.home() / "hedge" / "data" / "free"
OUT = Path.home() / "hedge" / ".rumbling-hedge" / "state" / "entry-refinement.latest.json"
ONE_MIN_FILE = sys.argv[1] if len(sys.argv) > 1 else "ES-1m-2020-2024.csv"
SYMBOL = sys.argv[2] if len(sys.argv) > 2 else "ES"
PULLBACK_WINDOW_MIN = 10     # how long to wait for the counter candle
RANGE_MIN = 30               # opening-range minutes
HOLD_BARS = 6                # time exit in TF bars
COST = 1.5


def load_1m(fn, max_rows=600000):
    bars = []
    with open(DATA / fn) as f:
        rd = csv.DictReader(f)
        for i, r in enumerate(rd):
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
    # normalize 'YYYY-MM-DD HH:MM...' -> (date, minutes-since-midnight)
    d = ts[:10]
    hm = ts[11:16]
    if len(hm) < 5:
        return d, 0
    return d, int(hm[:2]) * 60 + int(hm[3:5])


def resample(bars1m, tf_min):
    """Group 1m bars into tf_min buckets per day; return list of TF bars each carrying its 1m slice."""
    out = []
    cur = None
    for b in bars1m:
        d, m = minute_key(b["ts"])
        bucket = (d, m // tf_min)
        if cur is None or cur["key"] != bucket:
            if cur:
                out.append(cur)
            cur = {"key": bucket, "day": d, "mins": m, "o": b["o"], "h": b["h"], "l": b["l"],
                   "c": b["c"], "ones": [b]}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
            cur["ones"].append(b)
    if cur:
        out.append(cur)
    return out


def backtest(tf_bars, tf_min):
    by_day = defaultdict(list)
    for tb in tf_bars:
        by_day[tb["day"]].append(tb)
    rangebars = max(1, RANGE_MIN // tf_min)
    tradesA, tradesB = [], []
    skippedB = 0
    entry_improve = []
    for day, dbars in by_day.items():
        if len(dbars) < rangebars + HOLD_BARS + 1:
            continue
        orb = dbars[:rangebars]
        hi = max(x["h"] for x in orb)
        lo = min(x["l"] for x in orb)
        if hi - lo <= 0:
            continue
        for pos in range(rangebars, len(dbars) - HOLD_BARS):
            tb = dbars[pos]
            side = 1 if tb["c"] > hi else (-1 if tb["c"] < lo else 0)
            if side == 0:
                continue
            exit_px = dbars[pos + HOLD_BARS]["c"]
            # Method A: enter at breakout bar close
            entryA = tb["c"]
            tradesA.append((exit_px - entryA) * side - COST)
            # Method B: first counter 1m candle within window, across this + next bars' 1m slices
            ones = []
            for q in range(pos, min(pos + 1 + (PULLBACK_WINDOW_MIN // tf_min) + 1, len(dbars))):
                ones.extend(dbars[q]["ones"])
            # only consider 1m bars at/after the breakout bar's start
            counter_px = None
            seen = 0
            for o in ones:
                # for long, counter = red (c<o); for short, counter = green (c>o)
                if (side == 1 and o["c"] < o["o"]) or (side == -1 and o["c"] > o["o"]):
                    counter_px = o["c"]
                    break
                seen += 1
                if seen > PULLBACK_WINDOW_MIN:
                    break
            if counter_px is None:
                skippedB += 1
                continue
            tradesB.append((exit_px - counter_px) * side - COST)
            entry_improve.append((entryA - counter_px) * side)  # >0 means better (cheaper for long)
            break  # one trade per session (method A also one; break after recording both)
    return tradesA, tradesB, skippedB, entry_improve


def stats(t):
    if not t:
        return {"trades": 0}
    w = [x for x in t if x > 0]
    losses = [x for x in t if x <= 0]
    gl = abs(sum(losses))
    pf = (sum(w) / gl) if gl > 0 else None
    return {"trades": len(t), "win_rate": round(len(w) / len(t), 3),
            "net_points": round(sum(t), 1), "avg": round(statistics.mean(t), 2),
            "profit_factor": round(pf, 2) if pf else None}


def main():
    bars1m = load_1m(ONE_MIN_FILE)
    results = {}
    for tf in (3, 15, 30):
        tfbars = resample(bars1m, tf)
        A, B, skip, imp = backtest(tfbars, tf)
        results[f"{tf}m"] = {
            "breakout_close_entry": stats(A),
            "pullback_1m_counter_entry": stats(B),
            "pullback_skipped_no_counter": skip,
            "avg_entry_improvement_pts": round(statistics.mean(imp), 2) if imp else None,
            "pullback_fill_rate": round(len(B) / (len(B) + skip), 2) if (len(B) + skip) else None,
        }
    record = {"generatedAt": datetime.now(timezone.utc).isoformat(), "researchOnly": True,
              "writesOrders": False, "touchesBroker": False, "movesFunds": False,
              "readyForExecution": False, "readyForDemoExpansion": False, "readyForLive": False,
              "instrument": SYMBOL, "source": ONE_MIN_FILE,
              "span": [bars1m[0]["ts"], bars1m[-1]["ts"]] if bars1m else None,
              "idea": "long -> enter on first RED 1m candle; short -> first GREEN; vs breakout-close entry",
              "params": {"range_min": RANGE_MIN, "hold_bars": HOLD_BARS,
                         "pullback_window_min": PULLBACK_WINDOW_MIN, "cost": COST},
              "results": results,
              "caveat": "Relative entry-method comparison (the trustworthy part); absolute edge is a "
                        "time-exit proxy, not the blessed config. Promote via experiment.py gate."}
    OUT.write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    r = main()
    print(f"\n=== ENTRY REFINEMENT (ES, {r['span'][0][:10]}..{r['span'][1][:10]}) ===")
    for tf, x in r["results"].items():
        a, b = x["breakout_close_entry"], x["pullback_1m_counter_entry"]
        print(f"\n[{tf}] breakout-close: n={a.get('trades')} PF={a.get('profit_factor')} net={a.get('net_points')} wr={a.get('win_rate')} avg={a.get('avg')}")
        print(f"     1m-pullback:   n={b.get('trades')} PF={b.get('profit_factor')} net={b.get('net_points')} wr={b.get('win_rate')} avg={b.get('avg')}")
        print(f"     entry improvement: {x['avg_entry_improvement_pts']} pts/trade | fill rate {x['pullback_fill_rate']} | skipped {x['pullback_skipped_no_counter']}")
