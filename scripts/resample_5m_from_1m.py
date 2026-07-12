#!/usr/bin/env python3
"""Resample fresh 1m research CSVs into the 5m CSVs the master bridge reads.

Research-data step only (no broker access). Keeps NQ-5m-5d.csv etc. under the
8h freshness gate by deriving them from the hourly-refreshed 1m files.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data" / "free"
SYMBOLS = ["NQ", "ES", "CL", "GC", "6E", "ZN"]


def resample_symbol(sym: str) -> dict:
    src = DATA / f"{sym}-1m-5d.csv"
    dst = DATA / f"{sym}-5m-5d.csv"
    if not src.exists():
        return {"symbol": sym, "status": "skipped", "reason": "no 1m source"}
    df = pd.read_csv(src, parse_dates=["ts"])
    if df.empty:
        return {"symbol": sym, "status": "skipped", "reason": "empty 1m source"}
    df = df.set_index("ts").sort_index()
    bars = df.resample("5min").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open", "high", "low", "close"])
    bars.insert(0, "symbol", sym)
    out = bars.reset_index()
    out["ts"] = out["ts"].dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    out.to_csv(dst, index=False)
    return {"symbol": sym, "status": "ok", "rows": len(out), "last_bar": out["ts"].iloc[-1]}


def main() -> None:
    results = [resample_symbol(sym) for sym in SYMBOLS]
    print(json.dumps({
        "command": "resample-5m-from-1m",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
