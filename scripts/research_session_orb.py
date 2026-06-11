#!/usr/bin/env python3
"""Session-anchored ORB backtest — validates London/Asia ORB as actually executed live.

Mirrors scripts/london_orb_nq_signal.py: opening range = first 15min after session
open (London 07:00 UTC, Asia 23:00 UTC), breakout entries until window close.
Exits: (a) time exit after hold_bars, (b) live geometry 1.0 ATR stop + RR target.
Cost: 1.5 NQ points round trip. Train/OOS = chronological 70/30.

Research-only. Artifact: .rumbling-hedge/state/research-session-orb.latest.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path.home() / "hedge"
COST_PTS = 1.5

SESSIONS = {
    "london": {"open": "07:00", "entry_end": "12:00"},
    "asia": {"open": "23:00", "entry_end": "05:00"},
    "ny": {"open": "13:30", "entry_end": "18:00"},  # 09:30 ET in winter UTC; approximation
}


def load(path):
    df = pd.read_csv(path, parse_dates=["ts"])
    df = df.set_index("ts").sort_index()
    df["atr"] = (df.high - df.low).rolling(14).mean()
    return df


def day_session_bars(df, day, open_t, end_t):
    start = pd.Timestamp(f"{day}T{open_t}:00Z")
    end = pd.Timestamp(f"{day}T{end_t}:00Z")
    if end <= start:
        end += pd.Timedelta(days=1)
    return df.loc[start:end], start


def backtest(df, session, range_min=15, hold_bars=18, exit_mode="time",
             stop_atr=1.0, tp_rr=2.0, max_trades=1):
    cfg = SESSIONS[session]
    trades = []
    for day in sorted(set(df.index.normalize().date)):
        bars, sopen = day_session_bars(df, day, cfg["open"], cfg["entry_end"])
        if len(bars) < range_min + 5:
            continue
        rng = bars.iloc[:range_min]
        hi, lo = rng.high.max(), rng.low.min()
        post = bars.iloc[range_min:]
        n_taken = 0
        i = 0
        idx = post.index
        while i < len(post) and n_taken < max_trades:
            b = post.iloc[i]
            side = 1 if b.high > hi else (-1 if b.low < lo else 0)
            if side == 0:
                i += 1
                continue
            entry = hi if side == 1 else lo
            atr = df.atr.asof(idx[i])
            if pd.isna(atr) or atr <= 0:
                break
            stop = entry - side * stop_atr * atr
            target = entry + side * stop_atr * atr * tp_rr
            pnl = None
            exit_i = min(i + hold_bars, len(post) - 1)
            if exit_mode == "time":
                pnl = side * (post.iloc[exit_i].close - entry) - COST_PTS
            else:
                for j in range(i, len(post)):
                    bj = post.iloc[j]
                    hit_sl = bj.low <= stop if side == 1 else bj.high >= stop
                    hit_tp = bj.high >= target if side == 1 else bj.low <= target
                    if hit_sl:  # conservative: stop checked first
                        pnl = side * (stop - entry) - COST_PTS
                        exit_i = j
                        break
                    if hit_tp:
                        pnl = side * (target - entry) - COST_PTS
                        exit_i = j
                        break
                if pnl is None:
                    pnl = side * (post.iloc[-1].close - entry) - COST_PTS
                    exit_i = len(post) - 1
            trades.append({"day": str(day), "side": side, "entry": float(entry),
                           "pnl": float(pnl)})
            n_taken += 1
            i = exit_i + 1
    return trades


def stats(trades):
    if not trades:
        return {"n": 0}
    p = np.array([t["pnl"] for t in trades])
    w, l = p[p > 0].sum(), -p[p < 0].sum()
    return {"n": len(p), "pf": round(float(w / l), 3) if l > 0 else None,
            "win_rate": round(float((p > 0).mean()), 3),
            "net_pts": round(float(p.sum()), 1), "avg_pts": round(float(p.mean()), 2)}


def main():
    df = load(ROOT / "data/free/NQ-1m-3yr.csv")
    results = []
    for session in ("london", "asia", "ny"):
        for mode, label in (("time", "time_exit_18bars"), ("bracket", "sl1.0atr_rr2.0")):
            trades = backtest(df, session, exit_mode=mode)
            cut = int(len(trades) * 0.7)
            res = {"session": session, "exit": label, "all": stats(trades),
                   "train": stats(trades[:cut]), "oos": stats(trades[cut:])}
            results.append(res)
            print(f"{session:8s} {label:18s} all={res['all']} oos={res['oos']}")
    out = ROOT / ".rumbling-hedge/state/research-session-orb.latest.json"
    out.write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                               "research_only": True, "cost_pts": COST_PTS,
                               "range_minutes": 15, "results": results}, indent=2))
    print("artifact written:", out)


if __name__ == "__main__":
    main()
