#!/usr/bin/env python3
"""gc_orb_validate.py — READ-ONLY blessing-style validation of ORB on GOLD (GC).

Applies the BLESSED ORB config (range 6 bars, hold 6, stop 1.0 ATR, tp 2.0 RR — the
nq-orb-3m-vt16 geometry) to GC 5m/60d bars (closest cadence with real depth), with a
5-fold anchored walkforward + a shuffle test. Answers: is the robust ORB edge real on
the one DECORRELATED instrument we have data for (GC, corr +0.11 to NQ)? Routes nothing.

Promotion contract (blessed-edges): PF>=1.5, positive-fold-share>=0.6, n>=30, +net, shuffle-robust.
"""
import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

DATA = Path.home() / "hedge" / "data" / "free"
OUT = Path.home() / "hedge" / ".rumbling-hedge" / "state" / "gc-orb-validate.latest.json"
RANGE_BARS = 6
HOLD_BARS = 6
STOP_ATR = 1.0
TP_RR = 2.0
COST_POINTS = 1.5
ATR_PERIOD = 14


def load(fn):
    rows = []
    with open(DATA / fn) as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"ts": r.get("ts") or r.get("datetime"),
                             "h": float(r["high"]), "l": float(r["low"]), "c": float(r["close"])})
            except (KeyError, ValueError, TypeError):
                continue
    return rows


def atr(bars, i):
    if i < ATR_PERIOD:
        return None
    trs = []
    for k in range(i - ATR_PERIOD + 1, i + 1):
        trs.append(max(bars[k]["h"] - bars[k]["l"],
                       abs(bars[k]["h"] - bars[k - 1]["c"]),
                       abs(bars[k]["l"] - bars[k - 1]["c"])))
    return statistics.mean(trs)


def run(bars):
    """Per-session ORB with ATR brackets + time cap. Returns net-point trades."""
    sessions = {}
    for idx, b in enumerate(bars):
        sessions.setdefault(b["ts"][:10], []).append(idx)
    trades = []
    for day, idxs in sessions.items():
        if len(idxs) < RANGE_BARS + HOLD_BARS + 2:
            continue
        orb = [bars[j] for j in idxs[:RANGE_BARS]]
        hi = max(x["h"] for x in orb)
        lo = min(x["l"] for x in orb)
        if hi - lo <= 0:
            continue
        for pos in range(RANGE_BARS, len(idxs) - 1):
            j = idxs[pos]
            a = atr(bars, j)
            if a is None or a <= 0:
                continue
            c = bars[j]["c"]
            side = 1 if c > hi else (-1 if c < lo else 0)
            if side == 0:
                continue
            entry = c
            stop = entry - side * STOP_ATR * a
            target = entry + side * TP_RR * STOP_ATR * a
            # walk forward up to HOLD_BARS bars; bracket first, else time-exit
            outcome = None
            for h in range(1, HOLD_BARS + 1):
                if pos + h >= len(idxs):
                    break
                bar = bars[idxs[pos + h]]
                if side == 1:
                    if bar["l"] <= stop:
                        outcome = stop - entry; break
                    if bar["h"] >= target:
                        outcome = target - entry; break
                else:
                    if bar["h"] >= stop:
                        outcome = stop - entry; break
                    if bar["l"] <= target:
                        outcome = target - entry; break
            if outcome is None:
                end = bars[idxs[min(pos + HOLD_BARS, len(idxs) - 1)]]
                outcome = (end["c"] - entry) * side
            else:
                outcome = outcome * side if outcome and side == -1 else outcome
                outcome = abs(target - entry) if (outcome > 0) else -abs(entry - stop)
            trades.append(outcome - COST_POINTS)
            break  # one trade per session
    return trades


def stats(trades):
    if not trades:
        return {"trades": 0}
    w = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    gl = abs(sum(losses))
    pf = (sum(w) / gl) if gl > 0 else None
    return {"trades": len(trades), "win_rate": round(len(w) / len(trades), 3),
            "net_points": round(sum(trades), 1),
            "profit_factor": round(pf, 2) if pf else None}


def walkforward(bars, folds=5):
    seg = len(bars) // (folds + 1)
    out, pos = [], 0
    for k in range(folds):
        s = stats(run(bars[seg * (k + 1): seg * (k + 2)]))
        positive = (s.get("net_points") or 0) > 0
        pos += 1 if positive else 0
        out.append({"fold": k + 1, **s, "positive": positive})
    return out, round(pos / folds, 2)


def shuffle_test(bars, seeds=5):
    """Crude robustness: rotate session order by seed offset; edge should persist."""
    sess = {}
    for i, b in enumerate(bars):
        sess.setdefault(b["ts"][:10], []).append(b)
    days = list(sess.keys())
    results = []
    for sd in range(seeds):
        rot = days[sd * 3 % len(days):] + days[:sd * 3 % len(days)]
        flat = [b for d in rot for b in sess[d]]
        s = stats(run(flat))
        results.append((s.get("net_points") or 0) > 0)
    return f"{sum(results)}/{seeds}"


def main():
    fn = "GC-5m-60d.csv"
    bars = load(fn)
    full = stats(run(bars))
    wf, share = walkforward(bars)
    shuf = shuffle_test(bars)
    passes = (full.get("profit_factor") or 0) >= 1.5 and share >= 0.6 and \
             full.get("trades", 0) >= 30 and (full.get("net_points") or 0) > 0
    record = {"generatedAt": datetime.now(timezone.utc).isoformat(), "researchOnly": True,
              "writesOrders": False, "touchesBroker": False, "movesFunds": False,
              "readyForExecution": False, "readyForDemoExpansion": False, "readyForLive": False,
              "instrument": "GC", "file": fn, "cadence": "5m",
              "span": [bars[0]["ts"], bars[-1]["ts"]] if bars else None,
              "config": {"range_bars": RANGE_BARS, "hold_bars": HOLD_BARS, "stop_atr": STOP_ATR,
                         "tp_rr": TP_RR, "cost_points": COST_POINTS},
              "full": full, "walkforward": wf, "positive_fold_share": share, "shuffle": shuf,
              "promotion_contract": "PF>=1.5, fold-share>=0.6, n>=30, +net, shuffle-robust",
              "verdict": "MEETS-CONTRACT (5m proxy) -> deepen data + full gate" if passes
                         else "below contract on 5m/60d -> not promotable as-is",
              "caveat": "5m proxy for the 3m blessed edge; 60d depth. Confirms direction only; "
                        "blessing-grade needs deeper GC 3m bars through experiment.py."}
    OUT.write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    r = main()
    print(f"\n=== GC ORB VALIDATION ({r['file']}, {r['cadence']}) ===")
    print(f"span {r['span'][0][:10]}..{r['span'][1][:10]}")
    print(f"FULL: {json.dumps(r['full'])}")
    print(f"walkforward fold-share {r['positive_fold_share']} | shuffle {r['shuffle']}")
    for f in r["walkforward"]:
        print(f"  fold{f['fold']}: n={f.get('trades')} PF={f.get('profit_factor')} net={f.get('net_points')} {'+' if f['positive'] else 'NEG'}")
    print(f"VERDICT: {r['verdict']}")
