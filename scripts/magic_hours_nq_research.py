#!/usr/bin/env python3
"""Research-only NQ 'Magic Hours' hourly midpoint reversion probe.

Hypothesis (web research 2026): premarket hourly ranges (esp 06:00–08:00 ET)
mean-revert to the hour midpoint after a breakout of that hour's high/low.

One variable: which ET hour (6, 7, or 8). All other rules fixed.
Never writes orders / never touches broker.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_DATA = ROOT / "data/free/NQ-2022-2025-5m.csv"
ET = ZoneInfo("America/New_York")
COST_POINTS = 1.5  # round-trip research haircut


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # normalize columns
    cols = {c.lower(): c for c in df.columns}
    ts_col = None
    for cand in ("timestamp", "datetime", "date", "time", "ts"):
        if cand in cols:
            ts_col = cols[cand]
            break
    if ts_col is None:
        raise SystemExit(f"No timestamp column in {path}: {list(df.columns)[:10]}")
    df["ts"] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts")
    for need in ("open", "high", "low", "close"):
        if need not in {c.lower() for c in df.columns}:
            raise SystemExit(f"Missing {need} in {path}")
    rename = {}
    for c in df.columns:
        if c.lower() in ("open", "high", "low", "close", "volume"):
            rename[c] = c.lower()
    df = df.rename(columns=rename)
    df["et"] = df["ts"].dt.tz_convert(ET)
    df["date_et"] = df["et"].dt.date
    df["hour_et"] = df["et"].dt.hour
    df["minute_et"] = df["et"].dt.minute
    return df


def evaluate_hour(df: pd.DataFrame, hour: int, hold_hours: int = 3) -> dict:
    """Fade breakout of hour H range; target = midpoint of that hour."""
    trades: list[dict] = []
    for day, day_df in df.groupby("date_et"):
        hour_bars = day_df[(day_df["hour_et"] == hour) & (day_df["minute_et"] < 60)]
        if len(hour_bars) < 4:
            continue
        h_hi = float(hour_bars["high"].max())
        h_lo = float(hour_bars["low"].min())
        mid = (h_hi + h_lo) / 2.0
        rng = h_hi - h_lo
        if rng < 10.0:  # skip flat/holiday sessions (published Magic Hours filter)
            continue
        # after hour ends: look for first break then reversion to mid within hold_hours
        after = day_df[day_df["et"] >= hour_bars["et"].iloc[-1]]
        after = after[after["et"] <= hour_bars["et"].iloc[-1] + pd.Timedelta(hours=hold_hours)]
        if after.empty:
            continue
        broke_up = False
        broke_dn = False
        entry = None
        side = None
        for _, row in after.iterrows():
            if not broke_up and float(row["high"]) > h_hi:
                broke_up = True
                entry = float(row["close"])
                side = -1  # fade up breakout → short toward mid
                entry_ts = row["ts"]
                break
            if not broke_dn and float(row["low"]) < h_lo:
                broke_dn = True
                entry = float(row["close"])
                side = 1  # fade down breakout → long toward mid
                entry_ts = row["ts"]
                break
        if entry is None or side is None:
            continue
        # exit: hit mid or end of window
        exit_px = float(after.iloc[-1]["close"])
        exit_ts = after.iloc[-1]["ts"]
        hit = False
        for _, row in after[after["ts"] >= entry_ts].iterrows():
            if side > 0 and float(row["high"]) >= mid:
                exit_px = mid
                exit_ts = row["ts"]
                hit = True
                break
            if side < 0 and float(row["low"]) <= mid:
                exit_px = mid
                exit_ts = row["ts"]
                hit = True
                break
        gross = side * (exit_px - entry)
        net = gross - COST_POINTS
        trades.append(
            {
                "date": str(day),
                "hour": hour,
                "side": "long" if side > 0 else "short",
                "entry": entry,
                "exit": exit_px,
                "mid": mid,
                "range": rng,
                "hit_mid": hit,
                "gross_points": round(gross, 4),
                "net_points": round(net, 4),
            }
        )

    if not trades:
        return {"hour": hour, "trades": 0, "hitRate": None, "netPoints": 0, "pf": None, "status": "no-trades"}

    n = len(trades)
    hits = sum(1 for t in trades if t["hit_mid"])
    nets = [t["net_points"] for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else None
    # chronological OOS: last 30%
    cut = int(n * 0.7)
    oos = nets[cut:]
    oos_hits = [t for t in trades[cut:] if t["hit_mid"]]
    return {
        "hour": hour,
        "trades": n,
        "hitRate": round(hits / n, 4),
        "netPoints": round(sum(nets), 4),
        "avgNet": round(sum(nets) / n, 4),
        "pf": None if pf is None else round(pf, 4),
        "oosTrades": len(oos),
        "oosHitRate": round(len(oos_hits) / len(oos), 4) if oos else None,
        "oosNetPoints": round(sum(oos), 4) if oos else None,
        "status": "ok",
        "researchOnly": True,
        "readyForExecution": False,
        "readyForPaper": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--hours", default="6,7,8", help="ET hours to test (one-variable sweep)")
    ap.add_argument("--hold-hours", type=int, default=3)
    ap.add_argument("--out", type=Path, default=STATE / "magic-hours-nq-research.latest.json")
    args = ap.parse_args()

    if not args.data.exists():
        # fallback 15m won't work well; try 5m alternate
        alt = ROOT / "data/free/NQ-2022-2025-5m.csv"
        if not alt.exists():
            raise SystemExit(f"Missing data {args.data}")
        args.data = alt

    df = load_bars(args.data)
    hours = [int(x) for x in args.hours.split(",") if x.strip()]
    results = [evaluate_hour(df, h, hold_hours=args.hold_hours) for h in hours]
    best = max(
        (r for r in results if r.get("oosTrades")),
        key=lambda r: (r.get("oosNetPoints") or -1e9, r.get("oosHitRate") or 0),
        default=None,
    )
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "command": "magic-hours-nq-research",
        "hypothesis": "Premarket ET hourly range breakouts mean-revert to hour midpoint (Magic Hours).",
        "oneVariable": "ET hour (6 vs 7 vs 8)",
        "data": str(args.data),
        "costPoints": COST_POINTS,
        "holdHours": args.hold_hours,
        "results": results,
        "bestHour": best,
        "decision": "research-only-magic-hours-probe",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "readyForPaper": False,
        "promotionGate": "Needs purged walkforward + session gates + live-readiness before any demo discussion",
        "sourceRefs": [
            "https://tradingstats.net/magic-hours-trading-strategy-nq/",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"out": str(args.out), "bestHour": best, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
