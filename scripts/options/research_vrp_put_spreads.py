#!/usr/bin/env python3
"""SPX put credit spread VRP research — first real options-lane backtest.

Data: SPX daily option chains 2010-2023 (kaggle-seagate), VIX daily.
Strategy: weekly entry, sell ~30-delta put / buy ~15-delta put at target DTE,
hold to expiry, settle vs UNDERLYING_LAST on expiry date.
Fills: conservative — short leg at BID, long leg at ASK.
Sweeps: DTE x short-delta x VIX-regime tercile. Train/OOS split 2010-2018 / 2019-2023.

Research-only. Writes artifact to .rumbling-hedge/state/options/vrp-put-spreads.latest.json
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path.home() / "hedge"
CHAIN = ROOT / "data/kaggle-seagate/shubhamcodez__s-and-p-500-daily-options-data-2010-2023/combined_options_data.csv"
VIX = ROOT / "data/kaggle-seagate/vix-cboe-index/vix-daily_csv.csv"
OUT = ROOT / ".rumbling-hedge/state/options"

COLS = ["QUOTE_DATE", "EXPIRE_DATE", "DTE", "STRIKE", "UNDERLYING_LAST",
        "P_DELTA", "P_BID", "P_ASK"]


def load():
    df = pd.read_csv(CHAIN, usecols=COLS)
    for c in ("QUOTE_DATE", "EXPIRE_DATE"):
        df[c] = pd.to_datetime(df[c], format="%d-%m-%Y", errors="coerce")
    df = df.dropna(subset=["QUOTE_DATE", "EXPIRE_DATE", "P_DELTA", "P_BID", "P_ASK"])
    df = df[(df.P_BID > 0) & (df.P_ASK >= df.P_BID)]
    vix = pd.read_csv(VIX, parse_dates=["Date"]).set_index("Date")["VIX Close"]
    # settlement price per expiry date = underlying last on that quote date
    settle = df.groupby("QUOTE_DATE")["UNDERLYING_LAST"].first()
    return df, vix, settle


def backtest(df, vix, settle, dte_target, short_delta, long_delta, entry_weekday=4):
    trades = []
    entries = df[df.QUOTE_DATE.dt.weekday == entry_weekday]
    for qd, day in entries.groupby("QUOTE_DATE"):
        cand = day[(day.DTE >= dte_target - 7) & (day.DTE <= dte_target + 7)]
        if cand.empty:
            continue
        exp = cand.loc[(cand.DTE - dte_target).abs().idxmin(), "EXPIRE_DATE"]
        chain = cand[cand.EXPIRE_DATE == exp]
        s = chain.loc[(chain.P_DELTA + short_delta).abs().idxmin()]
        l = chain.loc[(chain.P_DELTA + long_delta).abs().idxmin()]
        if s.STRIKE <= l.STRIKE:
            continue
        credit = s.P_BID - l.P_ASK
        width = s.STRIKE - l.STRIKE
        if credit <= 0 or width <= 0 or exp not in settle.index:
            continue
        st = settle.loc[exp]
        pnl = credit - max(0.0, s.STRIKE - st) + max(0.0, l.STRIKE - st)
        pnl = max(pnl, credit - width)  # defined risk floor
        v = vix.asof(qd) if qd >= vix.index[0] else np.nan
        trades.append({"entry": str(qd.date()), "expiry": str(exp.date()),
                       "short_k": float(s.STRIKE), "long_k": float(l.STRIKE),
                       "credit": round(float(credit), 2), "width": float(width),
                       "max_loss": round(float(width - credit), 2),
                       "pnl": round(float(pnl), 2), "vix": round(float(v), 2) if pd.notna(v) else None})
    return trades


def stats(trades):
    if not trades:
        return {"n": 0}
    pnl = np.array([t["pnl"] for t in trades])
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    rr = np.mean([t["credit"] / t["max_loss"] for t in trades if t["max_loss"] > 0])
    return {"n": len(trades), "pf": round(float(wins / losses), 3) if losses > 0 else None,
            "win_rate": round(float((pnl > 0).mean()), 3),
            "net": round(float(pnl.sum()), 1), "avg_pnl": round(float(pnl.mean()), 2),
            "worst": round(float(pnl.min()), 1), "avg_credit_to_maxloss": round(float(rr), 3)}


def main():
    df, vix, settle = load()
    print(f"chains {df.QUOTE_DATE.min().date()}..{df.QUOTE_DATE.max().date()} rows={len(df)}")
    split = pd.Timestamp("2012-07-01")
    vix_terciles = vix.quantile([1 / 3, 2 / 3]).values
    results = []
    for dte in (14, 30, 45):
        for sd, ld in ((0.30, 0.15), (0.20, 0.10)):
            trades = backtest(df, vix, settle, dte, sd, ld)
            train = [t for t in trades if pd.Timestamp(t["entry"]) < split]
            oos = [t for t in trades if pd.Timestamp(t["entry"]) >= split]
            regimes = {}
            for name, lo, hi in (("vix_low", 0, vix_terciles[0]),
                                 ("vix_mid", vix_terciles[0], vix_terciles[1]),
                                 ("vix_high", vix_terciles[1], 999)):
                seg = [t for t in trades if t["vix"] and lo <= t["vix"] < hi]
                regimes[name] = stats(seg)
            results.append({"dte": dte, "short_delta": sd, "long_delta": ld,
                            "all": stats(trades), "train": stats(train),
                            "oos_2012H2plus": stats(oos), "by_vix_regime": regimes})
            r = results[-1]
            print(f"dte={dte} d={sd}/{ld} all={r['all']} oos={r["oos_2012H2plus"]}")
    OUT.mkdir(parents=True, exist_ok=True)
    artifact = {"ts": datetime.now(timezone.utc).isoformat(), "research_only": True,
                "strategy": "spx_put_credit_spread_vrp", "fills": "short@bid,long@ask",
                "settlement": "underlying_last_on_expiry_quote_date",
                "vix_terciles": [round(float(x), 2) for x in vix_terciles],
                "results": results}
    (OUT / "vrp-put-spreads.latest.json").write_text(json.dumps(artifact, indent=2))
    print("artifact written")


if __name__ == "__main__":
    main()
