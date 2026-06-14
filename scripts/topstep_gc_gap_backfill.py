#!/usr/bin/env python3
"""Read-only GC 1m history backfill from TopstepX /api/History/retrieveBars.

Pulls 1m bars across the contract roll (M26 -> Q26), stitches by daily volume
dominance, and writes the research CSV schema: ts,symbol,open,high,low,close,volume.

Read-only market data only - never places, modifies, or cancels orders.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, os.path.expanduser("~/.hermes/scripts"))
from topstep_auth_cache import get_token  # noqa: E402

API_BASE = "https://api.topstepx.com"
OUT_DEFAULT = Path.home() / "hedge/data/free/GC-1m-gap-2026.csv"


def retrieve_bars(token, contract_id, start, end):
    r = requests.post(
        f"{API_BASE}/api/History/retrieveBars",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "contractId": contract_id,
            "live": False,
            "startTime": start.isoformat().replace("+00:00", "Z"),
            "endTime": end.isoformat().replace("+00:00", "Z"),
            "unit": 2,
            "unitNumber": 1,
            "limit": 20000,
            "includePartialBar": False,
        },
        timeout=90,
    )
    r.raise_for_status()
    bars = r.json().get("bars")
    return bars if isinstance(bars, list) else []


def pull_contract(token, contract_id, start, end):
    out = {}
    cur = start
    while cur < end:
        chunk_end = min(cur + timedelta(days=5), end)
        bars = retrieve_bars(token, contract_id, cur, chunk_end)
        for b in bars:
            out[b["t"]] = b
        cur = chunk_end
        time.sleep(0.3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-04-13")
    ap.add_argument("--end", default=None, help="UTC date, exclusive; default now")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = (
        datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
        if args.end
        else datetime.now(timezone.utc)
    )

    token = get_token()
    contracts = ["CON.F.US.GCE.M26", "CON.F.US.GCE.Q26"]
    per_contract = {cid: pull_contract(token, cid, start, end) for cid in contracts}
    for cid, bars in per_contract.items():
        print(f"{cid}: {len(bars)} bars", file=sys.stderr)

    # Stitch: for each UTC trade date, keep the contract with higher total volume.
    day_vol = defaultdict(lambda: defaultdict(float))
    for cid, bars in per_contract.items():
        for ts, b in bars.items():
            day_vol[ts[:10]][cid] += float(b.get("v") or 0)

    rows = {}
    for cid, bars in per_contract.items():
        for ts, b in bars.items():
            day = ts[:10]
            winner = max(day_vol[day], key=lambda c: day_vol[day][c])
            if cid == winner:
                rows[ts] = b

    roll_days = sorted(
        d for d, v in day_vol.items() if len(v) > 1 and max(v, key=v.get) != contracts[0]
    )
    print(f"roll to Q26 from: {roll_days[0] if roll_days else 'n/a'}", file=sys.stderr)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        f.write("ts,symbol,open,high,low,close,volume\n")
        for ts in sorted(rows):
            b = rows[ts]
            t = ts.replace("+00:00", "Z")
            if not t.endswith("Z"):
                t += "Z"
            f.write(f"{t},GC,{b['o']},{b['h']},{b['l']},{b['c']},{int(b.get('v') or 0)}\n")
    print(f"wrote {len(rows)} bars -> {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
