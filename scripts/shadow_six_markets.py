#!/usr/bin/env python3
"""shadow_six_markets.py — forward ORB-3m shadow engine for the 6-market fund.

For every instrument whose stage is "shadow" in config/instrument-lanes.json, this
generates the SAME structurally-confirmed ORB-3m signal used live on NQ, logs it to
a per-instrument forward journal, and SCORES previously-logged signals against newer
bars (bracket: stop_atr 1.0 / tp_rr 2.0, max-hold timeout). The accruing forward PF
per instrument is the promotion evidence (shadow -> demo) — built with ZERO execution.

READ-ONLY / NO EXECUTION: never places, signs, or routes any order. It only reads
the read-only bar archive and writes shadow journals. This is the fund's risk-free
evidence base; demo/live routing lives in the guarded lane bridges, gated separately.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

VENV = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV) and VENV.exists():
    import os; os.execv(str(VENV), [str(VENV)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
REGISTRY = ROOT / "config/instrument-lanes.json"
ARCHIVE = ROOT / ".rumbling-hedge/research/topstep-readonly-bars"
SHADOW_DIR = ROOT / ".rumbling-hedge/state/shadow"

RANGE_BARS = 6
VOL_THRESH = 1.6
STOP_ATR = 1.0
TP_RR = 2.0
MAX_HOLD_BARS = 40  # 3m bars (~2h) safety timeout for scoring an open shadow


def load_registry():
    return json.loads(REGISTRY.read_text())


def load_bars(symbol):
    import pandas as pd
    csv = ARCHIVE / f"{symbol}-1m-topstep-readonly.csv"
    if not csv.exists():
        return None
    df = pd.read_csv(csv)
    if "ts" not in df.columns:
        return None
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    if "symbol" in df.columns:
        df = df[df["symbol"] == symbol].copy()
    if df.empty:
        return None
    df = df.sort_values("ts").set_index("ts")
    r = df.resample("3min", label="right", closed="right").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum" if "volume" in df.columns else "first",
    }).dropna().reset_index()
    et = r["ts"].dt.tz_convert("America/New_York")
    r["minutes_from_open"] = et.dt.hour * 60 + et.dt.minute - (9 * 60 + 30)
    r["date"] = et.dt.date
    return r


def atr(df, period=14):
    import pandas as pd
    tr = pd.concat([abs(df["high"] - df["low"]),
                    abs(df["high"] - df["close"].shift(1)),
                    abs(df["low"] - df["close"].shift(1))], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=7).mean()


def orb3m_signal(df, day):
    tb = df[df["date"] == day].copy()
    if tb.empty:
        return None
    opening = tb[tb["minutes_from_open"] < RANGE_BARS * 3]
    after = tb[tb["minutes_from_open"] >= RANGE_BARS * 3]
    if opening.empty or after.empty:
        return None
    rh, rl = opening["high"].max(), opening["low"].min()
    a = atr(df)
    av = float(a.iloc[-1]) if not a.empty and a.iloc[-1] == a.iloc[-1] else (rh - rl)
    recent = after.tail(3)
    vfloor = float(opening["volume"].rolling(5, min_periods=3).mean().iloc[-1]) * VOL_THRESH
    if recent["high"].max() > rh:
        eb = recent[recent["high"] > rh].iloc[0]
        if eb["volume"] >= vfloor:
            entry = rh; sl = entry - av * STOP_ATR; tp = entry + (entry - sl) * TP_RR
            return {"side": "long", "entry": float(entry), "stop": float(sl), "target": float(tp),
                    "entry_ts": str(eb["ts"]), "price_now": float(recent.iloc[-1]["close"])}
    if recent["low"].min() < rl:
        eb = recent[recent["low"] < rl].iloc[0]
        if eb["volume"] >= vfloor:
            entry = rl; sl = entry + av * STOP_ATR; tp = entry - (sl - entry) * TP_RR
            return {"side": "short", "entry": float(entry), "stop": float(sl), "target": float(tp),
                    "entry_ts": str(eb["ts"]), "price_now": float(recent.iloc[-1]["close"])}
    return None


def score_open(records, df):
    """Resolve unscored shadow signals against bars after their entry_ts."""
    changed = 0
    for r in records:
        if r.get("resolved"):
            continue
        entry_ts = r.get("entry_ts")
        fwd = df[df["ts"].astype(str) > str(entry_ts)].head(MAX_HOLD_BARS)
        if fwd.empty or len(fwd) < 2:
            continue
        side, entry, sl, tp = r["side"], r["entry"], r["stop"], r["target"]
        outcome, exit_px = None, None
        for _, b in fwd.iterrows():
            if side == "long":
                if b["low"] <= sl: outcome, exit_px = "SL", sl; break
                if b["high"] >= tp: outcome, exit_px = "TP", tp; break
            else:
                if b["high"] >= sl: outcome, exit_px = "SL", sl; break
                if b["low"] <= tp: outcome, exit_px = "TP", tp; break
        if outcome is None:
            if len(fwd) >= MAX_HOLD_BARS:
                outcome, exit_px = "TIMEOUT", float(fwd.iloc[-1]["close"])
            else:
                continue  # not enough forward bars yet — leave open
        net = (exit_px - entry) if side == "long" else (entry - exit_px)
        r.update({"resolved": True, "outcome": outcome, "exit_px": float(exit_px),
                  "net_points": round(float(net), 4)})
        changed += 1
    return changed


def summarize(records):
    res = [r for r in records if r.get("resolved")]
    n = len(res)
    if not n:
        return {"signals": len(records), "resolved": 0}
    wins = [r for r in res if r["net_points"] > 0]
    gross_w = sum(r["net_points"] for r in wins)
    gross_l = -sum(r["net_points"] for r in res if r["net_points"] <= 0)
    pf = round(gross_w / gross_l, 3) if gross_l > 0 else None
    return {"signals": len(records), "resolved": n, "open": len(records) - n,
            "win_rate": round(len(wins) / n, 3), "net_points": round(sum(r["net_points"] for r in res), 2),
            "profit_factor": pf}


def run():
    SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    reg = load_registry()
    today = datetime.now(timezone.utc).astimezone().date()
    out = {"ts": datetime.now(timezone.utc).isoformat(), "instruments": {}}
    for inst in reg["instruments"]:
        if inst.get("stage") != "shadow":
            continue
        sym = inst["symbol"]
        jpath = SHADOW_DIR / f"{sym}-orb3m-shadow.jsonl"
        records = [json.loads(l) for l in jpath.read_text().splitlines()] if jpath.exists() else []
        df = load_bars(sym)
        if df is None:
            out["instruments"][sym] = {"status": "no-archive-yet"}
            continue
        # 1. Generate today's signal (dedupe by entry_ts).
        sig = orb3m_signal(df, today)
        added = 0
        if sig:
            if not any(r.get("entry_ts") == sig["entry_ts"] for r in records):
                rec = {"ts": datetime.now(timezone.utc).isoformat(), "symbol": sym,
                       "route": "shadow", "resolved": False, **sig}
                records.append(rec); added = 1
        # 2. Score previously-open signals against newer bars.
        scored = score_open(records, df)
        # 3. Persist + summarize.
        jpath.write_text("\n".join(json.dumps(r) for r in records) + ("\n" if records else ""))
        s = summarize(records); s["new_signal"] = added; s["newly_scored"] = scored
        out["instruments"][sym] = s
    (ROOT / ".rumbling-hedge/state/shadow-six-markets.latest.json").write_text(json.dumps(out, indent=2))
    for sym, s in out["instruments"].items():
        print(f"  {sym}: {s}")
    return out


if __name__ == "__main__":
    run()
