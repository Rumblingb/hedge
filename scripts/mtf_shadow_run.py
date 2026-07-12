#!/usr/bin/env python3
"""mtf_shadow_run.py — READ-ONLY live shadow of the MTF execution edge.

Validated 2026-06-16 (entry_exit_mtf_test): HTF opening-range breakout signal + 1m PRECISE
ENTRY (first counter candle: long->red, short->green) + 1m PRECISE EXIT (bracket TP/SL off the
opening range). Best at 30-60m signal TF. This runs the SAME logic on the most recent local
1m bars and emits a shadow signal showing what it WOULD do — for both exit profiles:
  - combine  : runner / HTF time-exit (capture trend, hit $3k fast)
  - payout   : 1m bracket exit (consistency, low variance)

Reads ONLY local CSV (no broker, no network) — safe during login-yield. Routes nothing.
Writes .rumbling-hedge/state/mtf-shadow-signal.latest.json + appends a jsonl log.
"""
import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

DATA = Path.home() / "hedge" / "data" / "free"
STATE = Path.home() / "hedge" / ".rumbling-hedge" / "state"
OUT = STATE / "mtf-shadow-signal.latest.json"
LOG = Path.home() / "hedge" / ".rumbling-hedge" / "logs" / "mtf-shadow.jsonl"

SIGNAL_TFS = [30, 60]          # sweet-spot signal timeframes
RANGE_MIN = 30                 # opening-range minutes
PULLBACK_WINDOW_MIN = 10
TP_MULT, SL_MULT = 1.0, 0.6    # 1m bracket off opening range
HOLD_BARS = 6                  # HTF runner time-exit

FILES = {"NQ": "NQ-1m-5d.csv", "ES": "ES-1m-5d.csv"}


def load_1m(fn):
    bars = []
    p = DATA / fn
    if not p.exists():
        return bars
    with open(p) as f:
        for r in csv.DictReader(f):
            try:
                ts = (r.get("ts") or r.get("datetime") or r.get("timestamp ET")
                      or r.get("timestamp") or r.get("time"))
                bars.append({"ts": ts, "o": float(r["open"]), "h": float(r["high"]),
                             "l": float(r["low"]), "c": float(r["close"])})
            except (KeyError, ValueError, TypeError):
                continue
    return bars


def mkey(ts):
    return ts[:10], int(ts[11:13]) * 60 + int(ts[14:16])


def resample(bars1m, tf):
    out, cur = [], None
    for b in bars1m:
        try:
            d, m = mkey(b["ts"])
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


def evaluate_latest_session(bars1m, tf):
    """Look at the most recent session: form the opening range, report whether a breakout
    fired, whether a 1m counter-candle entry is available, and the projected bracket levels."""
    tfb = resample(bars1m, tf)
    if not tfb:
        return {"status": "no-bars"}
    last_day = tfb[-1]["day"]
    dbars = [b for b in tfb if b["day"] == last_day]
    rb = max(1, RANGE_MIN // tf)
    if len(dbars) < rb + 1:
        return {"status": "session-forming", "day": last_day, "bars": len(dbars), "need": rb + 1}
    orb = dbars[:rb]
    hi, lo = max(x["h"] for x in orb), min(x["l"] for x in orb)
    rng = hi - lo
    if rng <= 0:
        return {"status": "no-range", "day": last_day}
    # scan post-range bars for a breakout
    for pos in range(rb, len(dbars)):
        tb = dbars[pos]
        side = 1 if tb["c"] > hi else (-1 if tb["c"] < lo else 0)
        if side == 0:
            continue
        # 1m stream from breakout onward
        stream = [o for q in range(pos, len(dbars)) for o in dbars[q]["ones"]]
        counter, seen = None, 0
        for o in stream:
            if (side == 1 and o["c"] < o["o"]) or (side == -1 and o["c"] > o["o"]):
                counter = o["c"]; break
            seen += 1
            if seen > PULLBACK_WINDOW_MIN:
                break
        entry_ref = counter if counter is not None else tb["c"]
        return {
            "status": "BREAKOUT" if counter is not None else "breakout-awaiting-pullback",
            "day": last_day, "tf_min": tf,
            "side": "long" if side == 1 else "short",
            "opening_range": {"high": round(hi, 2), "low": round(lo, 2), "points": round(rng, 2)},
            "breakout_close": round(tb["c"], 2),
            "pullback_entry": round(counter, 2) if counter is not None else None,
            "exit_payout_1m_bracket": {
                "target": round(entry_ref + side * TP_MULT * rng, 2),
                "stop": round(entry_ref - side * SL_MULT * rng, 2)},
            "exit_combine_runner": f"HTF time-exit after {HOLD_BARS} x {tf}m bars",
        }
    return {"status": "no-breakout-yet", "day": last_day, "range_points": round(rng, 2)}


def main():
    now = datetime.now(timezone.utc).isoformat()
    signals = {}
    for sym, fn in FILES.items():
        bars = load_1m(fn)
        if not bars:
            signals[sym] = {"status": "no-data", "file": fn}
            continue
        per_tf = {}
        for tf in SIGNAL_TFS:
            per_tf[f"{tf}m"] = evaluate_latest_session(bars, tf)
        signals[sym] = {"latest_bar": bars[-1]["ts"], "by_timeframe": per_tf}
    record = {
        "generatedAt": now, "mode": "shadow_only", "submitted": False,
        "strategy": "mtf-breakout-1m-execution",
        "design": "HTF opening-range breakout + 1m counter-candle entry + 1m bracket exit (or HTF runner)",
        "note": "SHADOW — no trades. Research candidate (2026-06-16): 30-60m signal + 1m execution study. "
                "Routes nothing; local bars only (broker untouched during login-yield).",
        "signals": signals,
        "researchOnly": True, "writesOrders": False, "touchesBroker": False,
        "movesFunds": False, "readyForExecution": False,
        "readyForDemoExpansion": False, "readyForLive": False,
    }
    STATE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2) + "\n")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps({"ts": now, "signals": signals}) + "\n")
    return record


if __name__ == "__main__":
    r = main()
    print(json.dumps(r["signals"], indent=2))
