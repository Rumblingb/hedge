#!/usr/bin/env python3
"""Iteration-4 pre-judgment run: replays research_session_orb.py logic (the
actual live London/Asia ORB definitions: 15min opening range anchored to
session UTC open, 18-bar time exit, 1.5pt cost, max 1 trade/day) against a
given CSV, for a given session, writing a final_info.json-style artifact to
out_dir. Read-only research script; does not touch any live state/config.
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
                    if hit_sl:
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
            "net_pts": round(float(p.sum()), 1), "avg_pts": round(float(p.mean()), 2),
            "avg_win": round(float(p[p > 0].mean()), 2) if (p > 0).any() else None,
            "avg_loss": round(float(p[p < 0].mean()), 2) if (p < 0).any() else None,
            "max_drawdown_points": round(float(min(0.0, np.minimum.accumulate(np.cumsum(p) - np.maximum.accumulate(np.cumsum(p))).min())), 1),
            }


def main():
    csv_path, session, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    df = load(csv_path)
    results = []
    for mode, label in (("time", "time_exit_18bars"), ("bracket", "sl1.0atr_rr2.0")):
        trades = backtest(df, session, exit_mode=mode)
        cut = int(len(trades) * 0.7)
        res = {"session": session, "exit": label, "all": stats(trades),
               "train": stats(trades[:cut]), "oos": stats(trades[cut:]),
               "n_trades_total": len(trades),
               "date_range": [trades[0]["day"], trades[-1]["day"]] if trades else None}
        results.append(res)
        print(f"{session:8s} {label:18s} all={res['all']}")
    out = Path(out_dir) / "final_info.json"
    out.write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                "research_only": True, "cost_pts": COST_PTS,
                                "range_minutes": 15, "hold_bars": 18,
                                "max_trades_per_day": 1,
                                "csv": str(csv_path), "results": results}, indent=2))
    print("artifact written:", out)


if __name__ == "__main__":
    main()
