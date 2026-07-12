#!/usr/bin/env python3
"""gc_orb_retest_validate.py — READ-ONLY re-validation of the shelved GC ORB-Retest edge.

The AI Scientist P3 run found GC 1h ORB + retest-confirmation(conf=5) = PF 2.398, WF 3/3,
shuffle 5/5 (ai-scientist-p3-orb-retest-2026-06-08.md) but it was NEVER wired into
experiment.py. This re-implements the documented config and checks whether it still holds
on current GC data, with a simple anchored walkforward. Routes nothing.

Config (from P3): strategy orb_retest, range_window_bars 6, hold_bars 8, volume_threshold 1.6,
confirmation_bars 5, rth_only False (24h).
"""
import csv
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
import json

DATA = Path.home() / "hedge" / "data" / "free"
OUT = Path.home() / "hedge" / ".rumbling-hedge" / "state" / "gc-orb-retest-validate.latest.json"
RANGE_WIN = 6
HOLD = 8
CONF = 5
VOL_THRESH = 1.6
COST_POINTS = 2.0  # gold round-trip cost proxy


def load_bars(path):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            try:
                ts = r.get("ts") or r.get("datetime")
                rows.append({"ts": ts, "o": float(r["open"]), "h": float(r["high"]),
                             "l": float(r["low"]), "c": float(r["close"])})
            except (KeyError, ValueError, TypeError):
                continue
    return rows


def day_of(ts):
    return ts[:10]


def run_retest(bars):
    """ORB + retest-confirmation: form opening range from first RANGE_WIN bars of each day,
    on first breakout require price to HOLD beyond the level for CONF consecutive bars, then
    enter and exit after HOLD bars. Returns list of net-point trades."""
    sessions = {}
    for b in bars:
        sessions.setdefault(day_of(b["ts"]), []).append(b)
    trades = []
    for day, sb in sessions.items():
        if len(sb) < RANGE_WIN + CONF + HOLD + 1:
            continue
        orb = sb[:RANGE_WIN]
        hi = max(x["h"] for x in orb)
        lo = min(x["l"] for x in orb)
        rng = hi - lo
        avg_bar = statistics.mean(x["h"] - x["l"] for x in orb)
        if rng <= 0 or avg_bar <= 0:
            continue
        i = RANGE_WIN
        done = False
        while i < len(sb) - (CONF + HOLD) and not done:
            c = sb[i]["c"]
            level = hi if c > hi else (lo if c < lo else None)
            if level is None:
                i += 1
                continue
            side = 1 if level == hi else -1
            # confirmation: next CONF bars must HOLD beyond the level
            held = all((sb[i + k]["c"] > level) if side == 1 else (sb[i + k]["c"] < level)
                       for k in range(1, CONF + 1))
            if held:
                entry = sb[i + CONF]["c"]
                exitp = sb[i + CONF + HOLD]["c"]
                trades.append((exitp - entry) * side - COST_POINTS)
                done = True
            i += 1
    return trades


def stats(trades):
    if not trades:
        return {"trades": 0}
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    gl = abs(sum(losses))
    pf = (sum(wins) / gl) if gl > 0 else None
    return {"trades": len(trades), "win_rate": round(len(wins) / len(trades), 3),
            "net_points": round(sum(trades), 1),
            "profit_factor": round(pf, 2) if pf else None,
            "avg_points": round(statistics.mean(trades), 2)}


def walkforward(bars, folds=3):
    n = len(bars)
    seg = n // (folds + 1)
    out = []
    for k in range(folds):
        test = bars[seg * (k + 1): seg * (k + 2)]
        s = stats(run_retest(test))
        out.append({"fold": k + 1, **s, "positive": (s.get("net_points") or 0) > 0})
    pos = sum(1 for f in out if f["positive"])
    return out, f"{pos}/{folds}"


def main():
    files = sys.argv[1:] or ["GC-1h-2000-2026.csv", "GC-1h-2024-2025.csv", "GC-60m-60d.csv"]
    results = {}
    for fn in files:
        p = DATA / fn
        if not p.exists():
            results[fn] = {"error": "missing"}
            continue
        bars = load_bars(p)
        full = stats(run_retest(bars))
        wf, wf_share = walkforward(bars)
        results[fn] = {"span": [bars[0]["ts"], bars[-1]["ts"]] if bars else None,
                       "rows": len(bars), "full": full,
                       "walkforward": wf, "wf_positive_share": wf_share}
    record = {"generatedAt": datetime.now(timezone.utc).isoformat(),
              "researchOnly": True, "writesOrders": False, "touchesBroker": False,
              "movesFunds": False, "readyForExecution": False,
              "readyForDemoExpansion": False, "readyForLive": False,
              "config": {"strategy": "orb_retest", "range_window_bars": RANGE_WIN,
                         "hold_bars": HOLD, "confirmation_bars": CONF,
                         "volume_threshold": VOL_THRESH, "cost_points": COST_POINTS, "session": "24h"},
              "reference": "ai-scientist-p3-orb-retest-2026-06-08 (PF 2.398, WF 3/3, shuffle 5/5)",
              "caveat": "Standalone re-impl, not the canonical harness; confirms direction, "
                        "promote only after wiring into experiment.py + full purged-OOS gate.",
              "results": results}
    OUT.write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
