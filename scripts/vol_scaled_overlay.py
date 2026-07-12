#!/usr/bin/env python3
"""vol_scaled_overlay.py — READ-ONLY test of the queue-rank-1 idea: does sizing the ORB
edge by VOL REGIME beat flat sizing? (Lintner CTA / Investing-in-Volatility / 0.25-Kelly
all converge here.) This is a SIZING overlay on the existing edge — entries/stops unchanged.

Generates NQ ORB trades on NQ-5m-60d, tags each by the opening-range vol percentile, then
compares equity outcomes under: flat 1x vs vol-scaled (lean into high-vol, trim low-vol).
A risk-reducing overlay, not a new signal. Routes nothing.
"""
import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

DATA = Path.home() / "hedge" / "data" / "free"
OUT = Path.home() / "hedge" / ".rumbling-hedge" / "state" / "vol-scaled-overlay.latest.json"
RANGE_BARS, HOLD_BARS, COST = 6, 6, 1.5


def load(fn):
    rows = []
    with open(DATA / fn) as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"ts": r.get("ts") or r.get("datetime"), "h": float(r["high"]),
                             "l": float(r["low"]), "c": float(r["close"])})
            except (KeyError, ValueError, TypeError):
                continue
    return rows


def orb_trades_with_vol(bars):
    """One ORB trade per session (time-exit), tagged with opening-range size as a vol proxy."""
    sessions = {}
    for i, b in enumerate(bars):
        sessions.setdefault(b["ts"][:10], []).append(i)
    out = []
    for day, idxs in sessions.items():
        if len(idxs) < RANGE_BARS + HOLD_BARS + 1:
            continue
        orb = [bars[j] for j in idxs[:RANGE_BARS]]
        hi, lo = max(x["h"] for x in orb), min(x["l"] for x in orb)
        rng = hi - lo
        if rng <= 0:
            continue
        for pos in range(RANGE_BARS, len(idxs) - HOLD_BARS):
            j = idxs[pos]
            c = bars[j]["c"]
            side = 1 if c > hi else (-1 if c < lo else 0)
            if side == 0:
                continue
            exitp = bars[idxs[pos + HOLD_BARS]]["c"]
            net = (exitp - c) * side - COST
            out.append({"day": day, "net": net, "orb_range": rng})
            break
    return out


def vol_percentiles(trades):
    rngs = sorted(t["orb_range"] for t in trades)
    n = len(rngs)
    for t in trades:
        rank = sum(1 for r in rngs if r <= t["orb_range"]) / n
        t["vol_pct"] = rank
    return trades


def equity_stats(net_series):
    if not net_series:
        return {"trades": 0}
    total = sum(net_series)
    mean = statistics.mean(net_series)
    sd = statistics.pstdev(net_series) or 1e-9
    # equity curve max drawdown (in points)
    eq, peak, mdd = 0, 0, 0
    for x in net_series:
        eq += x
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    return {"trades": len(net_series), "net_points": round(total, 1),
            "sharpe_per_trade": round(mean / sd, 3), "max_dd_points": round(mdd, 1),
            "return_over_dd": round(total / mdd, 2) if mdd > 0 else None}


def main():
    bars = load("NQ-5m-60d.csv")
    trades = vol_percentiles(orb_trades_with_vol(bars))
    flat = [t["net"] for t in trades]

    def scaled(t):
        # lean into high-vol (ORB follows through), trim low-vol chop. Bounded 0.5x..1.5x.
        if t["vol_pct"] >= 0.66:
            return 1.5
        if t["vol_pct"] <= 0.33:
            return 0.5
        return 1.0
    vol_scaled = [t["net"] * scaled(t) for t in trades]
    # normalize average exposure so comparison is risk-fair (same mean size)
    avg_mult = statistics.mean(scaled(t) for t in trades)
    vol_scaled_norm = [t["net"] * scaled(t) / avg_mult for t in trades]

    flat_s = equity_stats(flat)
    scaled_s = equity_stats(vol_scaled)
    norm_s = equity_stats(vol_scaled_norm)
    improves = (scaled_s.get("sharpe_per_trade") or -9) > (flat_s.get("sharpe_per_trade") or -9)

    # bucket edge by vol regime to show WHERE the edge lives
    buckets = {"low<=.33": [], "mid": [], "high>=.66": []}
    for t in trades:
        key = "low<=.33" if t["vol_pct"] <= 0.33 else ("high>=.66" if t["vol_pct"] >= 0.66 else "mid")
        buckets[key].append(t["net"])
    bucket_stats = {k: {"n": len(v), "net": round(sum(v), 1),
                        "avg": round(statistics.mean(v), 2) if v else None} for k, v in buckets.items()}

    record = {"generatedAt": datetime.now(timezone.utc).isoformat(), "researchOnly": True,
              "writesOrders": False, "touchesBroker": False, "movesFunds": False,
              "readyForExecution": False, "readyForDemoExpansion": False, "readyForLive": False,
              "instrument": "NQ", "file": "NQ-5m-60d.csv",
              "overlay": "size 1.5x when opening-range vol pct>=0.66, 0.5x when <=0.33, else 1x",
              "flat_1x": flat_s, "vol_scaled_raw": scaled_s, "vol_scaled_risk_normalized": norm_s,
              "edge_by_vol_regime": bucket_stats,
              "verdict": ("vol-scaling IMPROVES risk-adjusted return (Sharpe up) -> overlay worth further research gating"
                          if improves else "vol-scaling does not improve Sharpe on this window -> hold"),
              "caveat": "5m/60d proxy + crude opening-range vol tag; confirms direction. Wire only after "
                        "experiment.py gate + config-parity. Risk-reducing overlay, not a new entry signal."}
    OUT.write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    r = main()
    print("\n=== VOL-SCALED SIZING OVERLAY (NQ ORB, 5m/60d) ===")
    print(f"flat 1x:            {json.dumps(r['flat_1x'])}")
    print(f"vol-scaled (raw):   {json.dumps(r['vol_scaled_raw'])}")
    print(f"vol-scaled (norm):  {json.dumps(r['vol_scaled_risk_normalized'])}")
    print(f"edge by vol regime: {json.dumps(r['edge_by_vol_regime'])}")
    print(f"VERDICT: {r['verdict']}")
